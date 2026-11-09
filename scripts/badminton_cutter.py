#!/usr/bin/env python3
"""
Badminton Match Auto-Cutter & Highlight Extractor CLI

Comprehensive, broadcast-standard pipeline for badminton match footage:
- Acoustic transient hit detection with high-frequency energy profiling
- Multi-court acoustic decoupling (filtering adjacent court bleed & sneaker squeaks)
- Visual dead-ball motion drop truncation (zero walking, zero dead-ball pauses)
- Physical flight time & cadence multimodal shot verification (1:1 real strokes)
- Broadcast-grade ASS HUD overlay (millisecond match timer + tactical shot badges + finish banner)
- 0.4x slow-motion instant replays and WeChat sticker GIF exports
- Lossless stream copy cutting (-c copy) for rapid turnaround
"""

import os
import sys
import argparse
from bisect import bisect_left, bisect_right
import hashlib
import json
import math
import subprocess
import wave
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np

# Optional OpenCV for visual dead-ball and motion analysis
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from modes_handler import (
    generate_condensed_reel,
    run_media_export,
    VIDEO_EXTENSIONS,
    PLAYER_QUADRANTS,
)

__version__ = "1.8.10"


def resolve_ffmpeg_bin():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)
    configured = os.environ.get("BADMINTON_FFMPEG")
    if configured:
        return configured
    candidates = [
        os.path.join(root_dir, "bin", "ffmpeg.exe"),
        os.path.join(base_dir, "bin", "ffmpeg.exe"),
        os.path.join(root_dir, "ffmpeg.exe"),
        os.path.join(root_dir, "bin", "ffmpeg"),
    ]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.insert(0, os.path.join(exe_dir, "bin", "ffmpeg.exe"))
        candidates.insert(1, os.path.join(exe_dir, "ffmpeg.exe"))
        candidates.insert(2, os.path.join(exe_dir, "bin", "ffmpeg"))
    for c in candidates:
        if os.path.exists(c):
            return c
    which_ff = shutil.which("ffmpeg")
    return which_ff if which_ff else "ffmpeg"


def resolve_font_path():
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "Arial"


DEFAULT_FFMPEG = resolve_ffmpeg_bin()
FONT = resolve_font_path()


def source_fingerprint(video_path):
    path = os.path.normcase(os.path.realpath(video_path))
    stat = os.stat(path)
    return path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def audio_cache_path(video_path, ffmpeg_bin=DEFAULT_FFMPEG):
    identity = (*source_fingerprint(video_path), ffmpeg_bin, "mono-16k-pcm-v1")
    key = hashlib.sha256(json.dumps(identity).encode("utf-8")).hexdigest()
    return os.path.join(tempfile.gettempdir(), "badminton_audio_cache_v2", f"{key}.wav")


def extract_audio_wav(video_path, wav_path, ffmpeg_bin=DEFAULT_FFMPEG):
    if os.path.isfile(wav_path) and os.path.getsize(wav_path) > 44:
        return wav_path
    run_media_export(
        ffmpeg_bin, ["-i", video_path, "-map", "0:a:0", "-vn", "-ar", "16000",
                     "-ac", "1", "-c:a", "pcm_s16le"], wav_path
    )
    return wav_path


def get_video_duration(vpath, ffmpeg_bin=DEFAULT_FFMPEG):
    cmd = [ffmpeg_bin, "-hide_banner", "-nostdin", "-i", vpath]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:", 1)[1].split(",", 1)[0].strip().split(":")
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 0.0


def detect_hits(wav_path, th_val=5.0e6, ratio_th=3.0, soft_th=4.2e6, soft_ratio=20.0):
    """Find candidate strikes from high-frequency acoustic transients."""
    with wave.open(wav_path, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    win = int(sr * 0.010)
    hop = int(sr * 0.005)
    if not hop or len(raw) // 2 <= win + 40 * hop:
        return []

    # Reuse the difference buffer for squares and the cumulative sum.
    diff = np.diff(np.frombuffer(raw, dtype=np.int16).astype(np.float32))
    del raw
    np.square(diff, out=diff)
    np.cumsum(diff, out=diff)
    starts = np.arange(0, diff.size + 1 - win, hop)
    hf_energy = diff[starts + win - 1]
    hf_energy[1:] -= diff[starts[1:] - 1]
    hf_energy /= win
    del diff

    # Only compute the background mean for local maxima that pass an energy threshold.
    center = hf_energy[20:-20]
    candidates = np.flatnonzero(
        (center > hf_energy[19:-21]) & (center >= hf_energy[21:-19])
        & (center >= min(th_val, soft_th))
    ) + 20

    peaks = []
    last_t = -1.0
    for idx in candidates:
        t = int(idx) * hop / sr
        if t - last_t <= 0.35:
            continue
        val = hf_energy[idx]
        bg = np.mean(hf_energy[max(0, idx - 40):idx - 10])
        ratio = val / (bg + 1e-5)
        if (val >= th_val and ratio >= ratio_th) or (val >= soft_th and ratio >= soft_ratio):
            peaks.append((t, val))
            last_t = t
    return peaks


def compute_perspective_court_motion(d):
    """
    Perspective Trapezoid Court Mask & 3-Zone Boundary Corridor Analysis:
    In wide-angle baseline camera views across multi-court gyms, the active court
    forms a perspective trapezoid:
      - Far half-court & net zone: Y in [0.40 H, 0.58 H], X in [0.38 W, 0.57 W]
        (strictly between the two net posts, masking out adjacent left/right courts)
      - Near half-court zone: Y in [0.58 H, 0.86 H], X in [0.26 W, 0.72 W]
    Returns: (our_m, far_m, near_m, top_d, b_max)
    """
    sh, sw = d.shape
    top_d = float(np.mean(d[:int(sh * 0.18), :]))
    far_roi = d[int(sh * 0.40):int(sh * 0.58), int(sw * 0.38):int(sw * 0.57)]
    near_roi = d[int(sh * 0.58):int(sh * 0.86), int(sw * 0.26):int(sw * 0.72)]
    far_m = float(np.mean(far_roi))
    near_m = float(np.mean(near_roi))
    our_m = 0.45 * far_m + 0.55 * near_m
    b_l = float(np.mean(d[:, :int(sw * 0.14)]))
    b_r = float(np.mean(d[:, int(sw * 0.86):]))
    b_b = float(np.mean(d[int(sh * 0.84):, :]))
    b_max = max(b_l, b_r, b_b)
    return our_m, far_m, near_m, top_d, b_max


_MOTION_CACHE = {}


def sample_instant_motion(cap, fps, t_sec, vpath=None, ffmpeg_bin=DEFAULT_FFMPEG):
    """
    Measures instantaneous optical motion diff at timestamp t_sec
    using downscaled 640x360 grayscale frames and the Perspective Trapezoid mask.
    Features an in-memory sub-second resolution cache to eliminate duplicate seeks.
    Supports both OpenCV VideoCapture and pure FFmpeg pipe fallback when cv2 is unavailable.
    """
    if t_sec < 0:
        return None
    v_id = vpath if vpath else (id(cap) if cap is not None else "default")
    cache_key = (v_id, round(t_sec, 2))
    if cache_key in _MOTION_CACHE:
        return _MOTION_CACHE[cache_key]

    if cap is not None and fps > 0 and HAS_CV2:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t_sec * fps)))
        ret1, f1 = cap.read()
        for _ in range(3):
            cap.grab()
        ret2, f2 = cap.read()
        if ret1 and ret2:
            g1 = cv2.cvtColor(cv2.resize(f1, (640, 360)), cv2.COLOR_BGR2GRAY)
            g2 = cv2.cvtColor(cv2.resize(f2, (640, 360)), cv2.COLOR_BGR2GRAY)
            res = compute_perspective_court_motion(cv2.absdiff(g1, g2))
            _MOTION_CACHE[cache_key] = res
            return res

    if vpath and os.path.exists(vpath):
        cmd = [
            ffmpeg_bin,
            "-ss", f"{max(0.0, t_sec):.2f}",
            "-i", vpath,
            "-t", "0.2",
            "-vf", "fps=10,scale=640:360",
            "-f", "rawvideo",
            "-pix_fmt", "gray",
            "-"
        ]
        res_proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if len(res_proc.stdout) >= 640 * 360 * 2:
            buf = np.frombuffer(res_proc.stdout, dtype=np.uint8)
            f1 = buf[:640 * 360].reshape((360, 640)).astype(np.float32)
            f2 = buf[640 * 360:640 * 360 * 2].reshape((360, 640)).astype(np.float32)
            diff = np.abs(f2 - f1)
            res = compute_perspective_court_motion(diff)
            _MOTION_CACHE[cache_key] = res
            return res

    return None


def fast_camera_match_window(cap, fps, dur):
    """
    Detects when the camera settles on a stationary mount at the beginning of recording,
    and when it is handled/stopped at the end.
    Excludes all handheld startup/shutdown handling noise.
    """
    if cap is None or fps <= 0:
        return 0.0, dur

    prev = None
    stable_start = 0.0
    consec = 0
    for s in range(0, min(45, int(dur)), 2):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
        ret, frame = cap.read()
        if not ret: break
        gray = cv2.cvtColor(cv2.resize(frame, (640, 360)), cv2.COLOR_BGR2GRAY)
        if prev is not None:
            top_d = float(np.mean(cv2.absdiff(gray, prev)[:60, :]))
            if top_d < 3.5:
                consec += 1
                if consec >= 2:
                    stable_start = max(0.0, s - 3)
                    break
            else:
                consec = 0
                stable_start = 0.0
        prev = gray

    unstable_end = dur
    for s in range(max(0, int(dur) - 2), max(0, int(dur) - 30), -3):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
        ret, f1 = cap.read()
        if not ret: continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((s + 0.2) * fps))
        ret, f2 = cap.read()
        if not ret: continue
        g1 = cv2.cvtColor(cv2.resize(f1, (640, 360)), cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(cv2.resize(f2, (640, 360)), cv2.COLOR_BGR2GRAY)
        top_d = float(np.mean(cv2.absdiff(g1, g2)[:60, :]))
        if top_d < 3.5:
            unstable_end = s + 1.0
            break
        else:
            unstable_end = s - 1.0

    return stable_start, unstable_end


def check_clip_is_real_play(cap, fps, s_cut, e_cut, min_dur=5.0, r_peaks=None, stable_start=0.0, unstable_end=99999.0, vpath=None, min_hits=5, ffmpeg_bin=DEFAULT_FFMPEG):
    """
    True Badminton Play & Personnel Exit/Switch Verification (v1.4.9):
    - If hit_count < min_hits: reject immediately (short dead-ball tap clusters or adjacent court noise).
    - Optical serve & opening cadence verification:
      If the opening strokes are suspiciously rapid (g0 < 0.55s and g1 < 0.55s, impossible for legal serve flight)
      and optical motion at the opening hit indicates dormant/non-serving players, reject immediately.
    - Samples 5 points across the clip to verify bilateral court engagement and camera stability:
      1. Handheld mount/unmount camera shake (top_d > 9.0 and avg_our < 6.0) -> reject.
      2. Completely empty/dormant court (avg_our < 4.8 or max_our < 7.5) -> reject.
      3. Far court dormant / non-bilateral play (avg_far < 5.5 and max_far < 8.5) -> reject.
      4. Near court dormant / non-bilateral play (max_near < 8.5 or avg_near < 5.5) -> reject.
         In badminton doubles, players on our half-court MUST move dynamically (lunge, split-step, swing).
         Eliminates intermissions where adjacent courts play while our players are standing/walking.
      5. Adjacent/background court dominant motion (b_avg >= 13.0 and b_avg > 1.15 * avg_our,
         or avg_near < 6.2 with avg_far >= 16.0) -> reject.
    """
    dur = e_cut - s_cut
    if dur < min_dur:
        return False
    hit_count = len(r_peaks) if r_peaks else 0
    if hit_count < min_hits:
        return False
    if cap is None and not (vpath and os.path.exists(vpath)):
        return True
    if not HAS_CV2 and not (vpath and os.path.exists(vpath)):
        return True

    ffmpeg_opts = {"ffmpeg_bin": ffmpeg_bin} if ffmpeg_bin != DEFAULT_FFMPEG else {}

    # 1. Opening serve & cadence verification (eliminates adjacent court rallies bleed during intermissions)
    if r_peaks and len(r_peaks) >= 3:
        g0 = r_peaks[1][0] - r_peaks[0][0]
        g1 = r_peaks[2][0] - r_peaks[1][0]
        if g0 < 0.55 and g1 < 0.55:
            m_open = sample_instant_motion(cap, fps, r_peaks[0][0], vpath=vpath, **ffmpeg_opts)
            if m_open is not None and (m_open[1] < 3.0 or m_open[0] < 5.0):
                return False

    # 2. Multilateral court engagement & camera stability check
    pts = np.linspace(s_cut + 0.15 * dur, e_cut - 0.15 * dur, 5)
    motions = [sample_instant_motion(cap, fps, pt, vpath=vpath, **ffmpeg_opts) for pt in pts]
    motions = [m for m in motions if m is not None]
    if not motions:
        return True

    avg_our = float(np.mean([m[0] for m in motions]))
    max_our = float(max([m[0] for m in motions]))
    avg_far = float(np.mean([m[1] for m in motions]))
    max_far = float(max([m[1] for m in motions]))
    avg_near = float(np.mean([m[2] for m in motions]))
    max_near = float(max([m[2] for m in motions]))
    top_d_max = float(max([m[3] for m in motions]))
    b_avg = float(np.mean([m[4] for m in motions]))
    b_max_all = float(max([m[4] for m in motions]))

    # Handheld mount/unmount camera shake
    if top_d_max > 9.0 and avg_our < 6.0:
        return False
    # Completely empty/dormant court
    if avg_our < 4.8 or max_our < 7.5:
        return False
    # Casual walking / non-play intermission stroll:
    # In genuine badminton doubles, at least one explosive stroke/lunge/dive occurs (max_our >= 13.5 or max_near >= 12.0).
    # Rejects dead-ball walking intervals where adjacent court smashes produce false acoustic clusters.
    if max_our < 13.5 and max_near < 12.0:
        return False
    # Far court dormant (players standing around waiting, drinking water, changing balls)
    if avg_far < 5.5 and max_far < 8.5:
        return False
    # Near court dormant: In badminton doubles, near court players MUST exhibit active footwork!
    # If near court maximum motion never reached active footwork threshold, near players never hit a ball.
    if max_near < 8.5 or avg_near < 5.5:
        return False
    # Adjacent court dominant motion (Court 7 active while our court is scooping balls)
    if b_avg >= 13.0 and b_avg > 1.15 * avg_our:
        return False
    # Background/Adjacent court dominant motion while near court is sluggish
    if avg_near < 6.2 and (b_avg >= 11.0 or avg_far >= 16.0):
        return False
    # Walk-off / Personnel exit & substitution suppression (散场走动近镜头/过道走动特征 - v1.8.7)
    # When players finish a game/point and walk off towards camera/benches, or cross the camera walkway:
    # In genuine rallies, players start in service ready stances strictly within court lines (opening b_max < 10.0).
    # If the clip has high boundary corridor movement (b_avg >= 14.0 and b_max_all >= 25.0):
    #   - Rejects walkway congestion unless court trapezoid itself exhibits explosive real rally motion (max_our >= 30.0)
    #   - Opening walkway congestion: If opening boundary motion is high (motions[0][4] >= 12.0 or motions[1][4] >= 25.0),
    #     people are already in the camera exit walkway when the clip begins -> reject.
    #   - Extreme corridor dominance: If overall boundary corridor motion is extreme (b_avg >= 17.0),
    #     continuous walkway congestion right past the lens indicates intermission walk-off -> reject.
    if b_avg >= 14.0 and b_max_all >= 25.0:
        if max_our < 30.0:
            if motions[0][4] >= 12.0 or motions[1][4] >= 25.0 or b_avg >= 17.0:
                return False

    # Walk-in / Sideline aisle congestion at clip opening (入场走动/过道闲逛强过滤 - v1.8.10)
    # If boundary motion at clip opening / serve setup is high (b0 >= 15.0 or b1 >= 18.0)
    # while active court motion is non-explosive (our0 < 10.0), players are just entering from benches
    # while adjacent courts smash, not a genuine serve rally!
    m_open = sample_instant_motion(cap, fps, s_cut, vpath=vpath, **ffmpeg_opts)
    m_serve = sample_instant_motion(cap, fps, s_cut + 0.85, vpath=vpath, **ffmpeg_opts)
    if m_open is not None and m_serve is not None:
        if (m_open[4] >= 15.0 or m_serve[4] >= 18.0) and m_open[0] < 10.0 and max_our < 28.0:
            return False
        if m_open[4] >= 14.0 and m_serve[4] >= 14.0 and m_open[0] < 12.0 and max_our < 28.0:
            return False

    return True


def detect_visual_deadball_cutoff(video_path, s_time, e_time, peaks, cap=None, fps=0.0):
    """
    Ground-Truth Visual Dead-Ball Slicer (落地即止强切断机制 - v1.4.6):
    Protects active continuous rallies from premature termination.
    Prunes trailing floor-pickup taps if preceded by a long dead gap (>= 2.00s).
    Guarantees full downward landing trajectory (tracks optical court motion
    until shuttlecock physically touches floor and players decelerate).
    """
    if not peaks or len(peaks) < 3:
        return e_time, peaks

    valid_peaks = list(peaks)
    # Prune trailing floor pickup taps if preceded by gap >= 2.00s and low energy
    while len(valid_peaks) >= 3:
        times = [p[0] for p in valid_peaks]
        if (times[-1] - times[-2]) >= 2.00 and valid_peaks[-1][1] < 8.0e6:
            valid_peaks.pop()
        else:
            break

    last_hit = valid_peaks[-1][0]
    tail_e = valid_peaks[-1][1]
    had_smash_at_end = any(valid_peaks[k][1] >= 4.5e7 for k in range(max(0, len(valid_peaks) - 2), len(valid_peaks)))

    if had_smash_at_end:
        landing_delay = 0.65 if tail_e >= 2.0e7 else 0.85
        real_e_cut = min(e_time, last_hit + landing_delay)
    elif cap is not None and HAS_CV2:
        curr_t = last_hit + 0.85
        max_t = min(e_time, last_hit + 2.85)
        last_active_t = curr_t
        while curr_t <= max_t:
            m = sample_instant_motion(cap, fps, curr_t)
            if m is not None:
                our_m, far_m, near_m, top_d, b_max = m
                if our_m >= 5.2 and (b_max < 16.0 or our_m >= 6.0):
                    last_active_t = curr_t
                else:
                    break
            else:
                break
            curr_t += 0.35
        real_e_cut = min(e_time, last_active_t + 0.35)
    else:
        landing_delay = 1.65
        real_e_cut = min(e_time, last_hit + landing_delay)

    return real_e_cut, valid_peaks


def verify_multimodal_shots(raw_peaks, min_shot_interval=0.50):
    if not raw_peaks:
        return []
    sorted_peaks = sorted(raw_peaks, key=lambda x: x[0])
    verified = []
    i = 0
    while i < len(sorted_peaks):
        cluster = [sorted_peaks[i]]
        j = i + 1
        while j < len(sorted_peaks) and sorted_peaks[j][0] - cluster[0][0] < min_shot_interval:
            cluster.append(sorted_peaks[j])
            j += 1
        best_hit = max(cluster, key=lambda x: x[1])
        if not verified or best_hit[0] - verified[-1][0] >= min_shot_interval:
            verified.append(best_hit)
        i = j
    return verified


def extract_multi_shot_rallies(peaks, v_dur, max_gap=2.85, min_dur=5.0, min_hits=5, cap=None, fps=0.0, vpath=None, ffmpeg_bin=DEFAULT_FFMPEG):
    """
    Rally Ground-Truth Slicer & Zero Dead-Ball Decoupler (v1.4.7):
    1. Initial Clustering with max_gap=2.85s:
       Preserves high baseline-to-baseline clears (flight time up to 2.80s) without premature truncation.
    2. Physical Cadence & Stroke Decoupling:
       - Post-Smash Winner Drop & Point Decoupling: Decouples post-smash dead-ball floor taps
         only when a subsequent Point 2 exists in the cluster (with serve gap >= 2.0s, hits >= 3, and active attack).
         Guarantees that a rally ending with a smash defense, net push, or soft high clear is preserved
         intact without premature cutoff.
       - Inter-Point Break / Pre-Serve Gap: If gap >= 2.10s preceded by weak floor tap or followed by a serve return,
         severs the intermission cleanly before the new serve.
       - Single dead-ball tap without continuation: prunes isolated floor scoops.
       - Motion verification: verifies stillness/freeze at breaks via OpenCV or FFmpeg fallback.
    3. Rally Quality & Floor Tap Rejection:
       - Every valid rally must feature at least one active attacking/clearing stroke (max E >= 1.8e7),
         rejecting pure floor-pickup tap clusters.
       - Prunes leading/trailing dead-ball taps, while protecting genuine opening serves followed by active returns.
    4. Strict Multimodal Ground-Landing Guarantee:
       - s_cut = max(0.0, c[0][0] - 0.75s)  [Opening serve setup & backswing]
       - e_cut: Tracks optical court motion until shuttlecock physically touches floor and players decelerate
         (0.65s~0.85s for post-smash kills; optical motion tracked up to 2.85s for high clears/lobs).
    """
    if not peaks:
        return []

    verified_peaks = peaks

    # 1. Cluster with max_gap = 2.85s (supports deep high clears/lifts)
    clusters = []
    curr = [verified_peaks[0]]
    for p in verified_peaks[1:]:
        if p[0] - curr[-1][0] <= max_gap:
            curr.append(p)
        else:
            clusters.append(curr)
            curr = [p]
    if curr:
        clusters.append(curr)

    # 2. Decouple inter-point walking intermissions, deadball drops, and serves
    decoupled = []
    for c in clusters:
        sub = []
        i = 0
        while i < len(c):
            sub.append(c[i])
            if i + 1 < len(c):
                gap = c[i + 1][0] - c[i][0]
                is_break = False

                # Rule 1: Post-Smash Winner Drop & Point Decoupling (进攻制胜分与下一分接发强切断 - v1.4.8)
                # A smash occurred prior to c[i] (e.g. c[i-1] or c[i-2] was smash E >= 4.5e7,
                # so c[i] is the defensive block or ground landing).
                # We decouple at c[i] ONLY if the continuation leading into the next serve is verified DEAD-BALL FLOOR TAPS:
                # 1. Finds the next dead gap (>= 2.00s) leading into a new serve within a realistic intermission window (<= 8 hits).
                # 2. If all intermediate gaps between c[i] and the dead gap are tight rapid badminton cadence (<= 1.15s),
                #    or if an attacking stroke (E >= 1.8e7) exists, bilateral net/drive play is ACTIVELY CONTINUING!
                #    (Protects rapid net touches, flat drives, drops, and pushes from being cleaved).
                # 3. If there is NO attack AND intermediate gaps contain walking steps (any gap > 1.15s),
                #    proves players are low-motion walking and tapping floor scoops, so we decouple cleanly at c[i].
                had_prior_smash = any(c[k][1] >= 4.5e7 for k in range(max(0, i - 2), i))
                if had_prior_smash and gap >= 0.70 and (i + 1 < len(c) - 1):
                    dead_gap_idx = None
                    for k in range(i, min(len(c) - 1, i + 8)):
                        if c[k + 1][0] - c[k][0] >= 2.00:
                            # A true inter-point break leads into a new serve (serve return gap between 0.55s and 2.50s)
                            # Deep high clears in mid-rally have rapid counter-attacks (gap < 0.55s), not a new serve!
                            is_serve = True
                            if k + 2 < len(c):
                                g_after = c[k + 2][0] - c[k + 1][0]
                                if g_after < 0.55 or g_after > 2.50:
                                    is_serve = False
                            if is_serve:
                                dead_gap_idx = k
                                break

                    if dead_gap_idx is not None and dead_gap_idx > i:
                        inter_energies = [c[m][1] for m in range(i + 1, dead_gap_idx + 1)]
                        has_attack = any(e >= 1.8e7 for e in inter_energies)
                        inter_gaps = [c[m + 1][0] - c[m][0] for m in range(i, dead_gap_idx)]
                        is_rapid_net_play = len(inter_gaps) >= 2 and all(g <= 1.15 for g in inter_gaps)

                        if not has_attack and not is_rapid_net_play:
                            is_break = True

                # Rule 2: Inter-point break / pre-serve gap
                elif gap >= 2.10:
                    # Decouple if gap >= 2.10s occurs on exactly 2 hits followed by tight net tap (< 0.65s)
                    # (eliminates floor scoop + flip before an adjacent court rally)
                    if len(sub) == 2 and i + 2 < len(c) and (c[i + 2][0] - c[i + 1][0] < 0.65):
                        is_break = True
                    elif c[i][1] < 7.0e6 or (i + 2 < len(c) and 0.60 <= c[i + 2][0] - c[i + 1][0] <= 2.20 and c[i + 1][1] < 1.5e7):
                        is_break = True
                    elif cap is not None or vpath is not None:
                        m = sample_instant_motion(cap, fps, c[i][0] + 0.5 * gap, vpath=vpath)
                        if m is not None:
                            our_m, far_m, near_m, top_d, b_max = m
                            if our_m < 3.2 or (b_max >= 15.0 and b_max >= 2.0 * our_m):
                                is_break = True

                # Rule 3: Single dead-ball tap without continuation
                elif gap >= 1.60:
                    has_continuation = False
                    if i + 2 < len(c):
                        g_next = c[i + 2][0] - c[i + 1][0]
                        if 0.35 <= g_next <= 2.85:
                            has_continuation = True
                    else:
                        has_continuation = True

                    if not has_continuation:
                        if c[i + 1][1] < 1.5e7:
                            is_break = True
                    elif gap >= 2.00 and (cap is not None or vpath is not None):
                        m = sample_instant_motion(cap, fps, c[i][0] + 0.5 * gap, vpath=vpath)
                        if m is not None:
                            our_m, far_m, near_m, top_d, b_max = m
                            if our_m < 3.2 or (b_max >= 15.0 and b_max >= 2.0 * our_m):
                                is_break = True

                if is_break:
                    decoupled.append(sub)
                    sub = []
            i += 1
        if sub:
            decoupled.append(sub)

    # 3. Rally validation & pruning
    rallies = []
    for c in decoupled:
        # Prune trailing floor pickup taps if preceded by gap >= 2.00s and low energy
        while len(c) >= min_hits and (c[-1][0] - c[-2][0]) >= 2.00 and c[-1][1] < 8.0e6:
            c = c[:-1]

        # Prune leading dead-ball pickup taps if gap >= 1.70s
        # BUT protect genuine opening serve: if gap <= 2.20s and c[1] is an active return or followed by active rally
        while len(c) >= min_hits and (c[1][0] - c[0][0]) >= 1.70 and c[0][1] < 8.0e6:
            gap_lead = c[1][0] - c[0][0]
            is_serve_return = (gap_lead <= 2.20 and (c[1][1] >= 1.2e7 or (len(c) >= 3 and 0.35 <= c[2][0] - c[1][0] <= 2.0)))
            if is_serve_return:
                break
            c = c[1:]

        if len(c) < min_hits:
            continue

        # Every genuine badminton rally must contain at least one real stroke (max E >= 1.8e7)
        max_energy = max(p[1] for p in c)
        if max_energy < 1.8e7:
            continue

        # Rule 4: Pre-Serve Stationary Boundary & True Serve Anchoring (发球静止定界与真发球锚定 - v1.8.5)
        # Under BWF Rule 9.1, server and receiver must remain stationary in service boxes before serve.
        # If a cluster begins with footsteps, ball-picking walking noise, or adjacent-court hits:
        # 1. Inspect whether c[0] was preceded by stationary stillness (our_m <= 7.5 and near_m <= 7.0).
        # 2. If c[0] was walking noise, scan forward to locate the authentic opening serve:
        #    a stroke c[k] preceded by a stationary trough and immediately followed by active rally surge.
        # Prunes all preceding dead-ball walking hits, eliminating leading ball-picking dead time completely.
        has_video_source = (cap is not None) or (vpath is not None)
        if has_video_source and len(c) >= min_hits + 1:
            m_0 = sample_instant_motion(cap, fps, c[0][0] - 0.85, vpath=vpath, ffmpeg_bin=ffmpeg_bin)
            # Under BWF Rule 9.1, server and receiver must remain stationary in service boxes,
            # and boundary corridors must be clear of pedestrian traffic (b_max <= 8.5).
            is_c0_still = (m_0 is not None and m_0[0] <= 7.5 and m_0[2] <= 7.0 and m_0[4] <= 8.5)

            if not is_c0_still:
                best_serve_k = 0
                max_search_k = min(len(c) - min_hits, 16)
                for k in range(1, max_search_k + 1):
                    t_k = c[k][0]
                    # Realistic serve flight time to return stroke: at least 0.60s (net crossing) and at most 2.60s (high lob return)
                    if k + 1 < len(c):
                        g_ret = c[k + 1][0] - t_k
                        if g_ret < 0.60 or g_ret > 2.60:
                            continue
                    m_pre1 = sample_instant_motion(cap, fps, t_k - 0.85, vpath=vpath, ffmpeg_bin=ffmpeg_bin)
                    m_pre2 = sample_instant_motion(cap, fps, t_k - 1.50, vpath=vpath, ffmpeg_bin=ffmpeg_bin)
                    was_still = any(m is not None and m[0] <= 7.5 and m[2] <= 7.0 and m[4] <= 8.5 for m in [m_pre1, m_pre2])
                    if was_still:
                        m_post = sample_instant_motion(cap, fps, t_k + 0.65, vpath=vpath, ffmpeg_bin=ffmpeg_bin)
                        if m_post and (m_post[0] >= 12.0 or m_post[2] >= 9.0) and m_post[4] < 12.0:
                            best_serve_k = k
                            break
                if best_serve_k > 0:
                    c = c[best_serve_k:]

        s_cut = max(0.0, c[0][0] - 0.75)
        last_hit = c[-1][0]
        tail_energy = c[-1][1]
        had_smash_at_end = any(c[k][1] >= 4.5e7 for k in range(max(0, len(c) - 2), len(c)))

        if had_smash_at_end:
            landing_buf = 0.65 if tail_energy >= 2.0e7 else 0.85
            e_cut = min(v_dur, last_hit + landing_buf)
        elif cap is not None and HAS_CV2:
            curr_t = last_hit + 0.85
            max_t = min(v_dur, last_hit + 2.85)
            last_active_t = curr_t
            while curr_t <= max_t:
                m = sample_instant_motion(cap, fps, curr_t)
                if m is not None:
                    our_m, far_m, near_m, top_d, b_max = m
                    if our_m >= 5.2 and (b_max < 16.0 or our_m >= 6.0):
                        last_active_t = curr_t
                    else:
                        break
                else:
                    break
                curr_t += 0.35
            e_cut = min(v_dur, last_active_t + 0.35)
        else:
            landing_buf = 1.65
            e_cut = min(v_dur, last_hit + landing_buf)

        dur = e_cut - s_cut
        if dur >= min_dur and len(c) >= min_hits:
            rallies.append({
                "first_hit": c[0][0],
                "last_hit": c[-1][0],
                "hits": len(c),
                "clip_dur": dur,
                "s_cut": s_cut,
                "e_cut": e_cut,
                "peaks": c
            })
    return rallies


def extract_true_serve_kills(cap, fps, vpath, peaks, rallies, stable_start, unstable_end, v_dur):
    """
    Multimodal Visual Serve-Kill Verification Protocol (v1.3.6 Ground-Landing Guaranteed):
    1. Mandatory Acoustic Isolation:
       - Server hits bird (t_serve) within 0.45s ~ 1.70s before receiver's kill impact (t_k).
       - Zero acoustic strikes within [t_k + 0.25, t_k + 3.20] (proves rally did NOT continue).
       - Pre-serve ready stance silence: zero strikes between [t_serve - 2.80, t_serve - 0.50].
       - Kill impact energy >= 7.5e6.
    2. Parallelized 4-Stage Visual Verification across 8 workers:
       - Stage 1 (Kill Impact): 14.0 <= our_m <= 26.0, far_m >= 10.0 or near_m >= 8.0, b_max <= 9.0
       - Stage 2 (Pre-Serve Ready Stance): min(pre1, pre2) <= 7.8, near_m <= 9.5, b_max <= 7.0
       - Stage 3 (Explosive Surge): surge = kill / (min_pre + 1e-4) >= 2.0
       - Stage 4 (Dead-Ball Decay & Full Landing Trajectory): post (at t_k + 1.2s) <= 12.5
    3. Complete Landing Guarantee:
       - s_cut = max(0.0, t_serve - 0.65)
       - e_cut = min(v_dur, t_k + 1.25)  (Allows shuttlecock to plunge down, hit floor/net, and bounce)
    """
    if cap is None or fps <= 0 or not peaks:
        return []

    # The acoustic detector emits ordered peaks. Look up only neighboring events.
    times = [p[0] for p in peaks]
    cand_items = []
    for t_k, energy in peaks:
        if energy < 7.5e6:
            continue
        serve_idx = bisect_right(times, -0.45, key=lambda t: t - t_k) - 1
        if serve_idx < 0 or t_k - times[serve_idx] > 1.70:
            continue
        t_serve = times[serve_idx]
        subsequent = bisect_left(times, 0.25, key=lambda t: t - t_k)
        if subsequent < len(times) and times[subsequent] - t_k <= 3.20:
            continue
        pre_noise = bisect_left(times, -2.80, key=lambda t: t - t_serve)
        if pre_noise < len(times) and t_serve - times[pre_noise] >= 0.50:
            continue
        cand_items.append((t_serve, t_k))

    if not cand_items:
        return []

    def _verify_worker(sub_items):
        if not sub_items:
            return []
        w_cap = cv2.VideoCapture(vpath)
        w_fps = w_cap.get(cv2.CAP_PROP_FPS)
        found = []
        for t_serve, t_k in sub_items:
            km = sample_instant_motion(w_cap, w_fps, t_k - 0.08)
            if not km or km[3] > 3.8 or km[4] > 9.0 or not (14.0 <= km[0] <= 26.0) or (km[1] < 10.0 and km[2] < 8.0):
                continue
            pre1 = sample_instant_motion(w_cap, w_fps, t_serve - 1.2)
            pre2 = sample_instant_motion(w_cap, w_fps, t_serve - 0.6)
            post = sample_instant_motion(w_cap, w_fps, t_k + 1.2)
            if not (pre1 and pre2 and post):
                continue
            if pre1[4] > 7.0 or pre2[4] > 6.5 or pre1[2] > 9.5 or pre2[2] > 9.5:
                continue
            min_pre = min(pre1[0], pre2[0])
            if min_pre > 7.5:
                pre0 = sample_instant_motion(w_cap, w_fps, t_serve - 2.0)
                if pre0 and pre0[4] <= 7.0 and pre0[2] <= 9.5:
                    min_pre = min(min_pre, pre0[0])
            surge = km[0] / (min_pre + 1e-4)
            if min_pre <= 7.8 and post[0] <= 12.5 and surge >= 2.0:
                s_cut = max(0.0, t_serve - 0.65)
                # CRITICAL: e_cut MUST allow the shuttlecock to plunge down, hit floor/net, bounce,
                # and show players reacting to the dead ball. Never cut at t_k + 0.45s!
                e_cut = min(v_dur, t_k + 1.25)
                found.append({
                    "kill_t": t_k,
                    "serve_t": t_serve,
                    "s_cut": s_cut,
                    "e_cut": e_cut,
                    "dur": e_cut - s_cut,
                    "max_kill": km[0],
                    "surge": surge
                })
        w_cap.release()
        return found

    chunks = [cand_items[i::8] for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_verify_worker, chunks))

    merged_kills = sorted([item for sub in results for item in sub], key=lambda x: x["kill_t"])
    final_kills = []
    for k in merged_kills:
        if not final_kills or k["kill_t"] - final_kills[-1]["kill_t"] > 3.5:
            final_kills.append(k)
    return final_kills


def format_time_zh(t):
    m = int(t // 60)
    s = int(t % 60)
    return f"{m:02d}分{s:02d}秒"


def cut_lossless(ffmpeg_bin, vpath, s_cut, dur, out_path):
    run_media_export(
        ffmpeg_bin, ["-ss", f"{s_cut:.6f}", "-t", f"{dur:.6f}", "-i", vpath, "-c", "copy"],
        out_path,
    )


def cut_exact(ffmpeg_bin, vpath, s_cut, dur, out_path):
    run_media_export(
        ffmpeg_bin, ["-ss", f"{s_cut:.6f}", "-i", vpath, "-t", f"{dur:.6f}",
                     "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                     "-preset", "veryfast", "-crf", "18", "-threads", "2",
                     "-c:a", "aac", "-b:a", "192k"], out_path
    )


def concat_clips(ffmpeg_bin, clip_paths, out_reel_path):
    if clip_paths and not generate_condensed_reel(ffmpeg_bin, clip_paths, out_reel_path):
        raise RuntimeError(f"找不到可用于拼接的片段: {out_reel_path}")


def generate_gif(ffmpeg_bin, video_clip, out_gif, caption):
    vf = (
        f"scale=360:-1,"
        f"drawtext=fontfile='{FONT}':text='{caption}':fontsize=22:fontcolor=yellow:"
        f"box=1:boxcolor=black@0.6:boxborderw=6:x=(w-text_w)/2:y=h-text_h-14,"
        f"split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
    )
    cmd = [ffmpeg_bin, "-y", "-i", video_clip, "-vf", vf, "-r", "12", out_gif]
    run_media_export(ffmpeg_bin, cmd[2:-1], cmd[-1])


def generate_slowmo_replay(ffmpeg_bin, clip_path, out_path, slow_factor=0.4):
    filter_str = (
        f"[0:v]drawtext=fontfile='{FONT}':text='原速实况':fontsize=48:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=10:x=60:y=60[v_norm];"
        f"[0:v]trim=start=0.8:end=2.8,setpts={1.0/slow_factor}*PTS,"
        f"drawtext=fontfile='{FONT}':text='⚡ {slow_factor}X 慢动作回放':fontsize=48:fontcolor=yellow:box=1:boxcolor=black@0.6:boxborderw=10:x=60:y=60[v_slow];"
        f"[0:a]anull[a_norm];"
        f"[0:a]atrim=start=0.8:end=2.8,asetrate=48000*{slow_factor},aresample=48000[a_slow];"
        f"[v_norm][a_norm][v_slow][a_slow]concat=n=2:v=1:a=1[outv][outa]"
    )
    cmd = [
        ffmpeg_bin, "-y",
        "-i", clip_path,
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        out_path
    ]
    run_media_export(ffmpeg_bin, cmd[2:-1], cmd[-1])


def generate_broadcast_hud(ffmpeg_bin, clip_path, verified_shots, out_path, title="实战纯净多拍对决", total_dur=None, ball_down_t=None):
    """Render a timer and an estimated acoustic shot count."""
    if total_dur is None:
        total_dur = get_video_duration(clip_path, ffmpeg_bin)

    if ball_down_t is None and verified_shots:
        ball_down_t = min(total_dur, verified_shots[-1][0] + 0.40)

    total_shots = len(verified_shots)

    def fmt_ass_time(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        cs = int((sec - int(sec)) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    with tempfile.TemporaryDirectory(prefix="badminton-hud-") as staging:
        ass_path = os.path.join(staging, "hud.ass")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title, STHeiti, 34, &H0000FFFF, &H00FFFFFF, &H00000000, &H90000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 5, 0, 7, 60, 60, 50, 1
Style: ShotBadge, STHeiti, 48, &H0000FFFF, &H00FFFFFF, &H00000000, &H90000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 5, 0, 7, 60, 60, 110, 1
Style: Timer, STHeiti, 38, &H00FFFFFF, &H00FFFFFF, &H00000000, &H90000000, 1, 0, 0, 0, 100, 100, 0, 0, 3, 5, 0, 7, 60, 60, 175, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
            f.write(f"Dialogue: 0,{fmt_ass_time(0.0)},{fmt_ass_time(total_dur)},Title,,0,0,0,,🏸 转播级 HUD 打卡 · {title} (估算 {total_shots} 拍)\\n\n")

            first_hit_t = verified_shots[0][0] if verified_shots else 0.8
            f.write(f"Dialogue: 1,{fmt_ass_time(0.0)},{fmt_ass_time(first_hit_t)},ShotBadge,,0,0,0,,[实战击球] 准备发球...\\n\n")

            for i, hit in enumerate(verified_shots):
                s_t = hit[0]
                e_t = verified_shots[i + 1][0] if i + 1 < len(verified_shots) else (ball_down_t if ball_down_t else total_dur)
                badge_text = f"估算第 {i + 1:02d} 拍 / {total_shots} 拍"
                f.write(f"Dialogue: 1,{fmt_ass_time(s_t)},{fmt_ass_time(e_t)},ShotBadge,,0,0,0,,[实战击球] {badge_text}\\n\n")

            if ball_down_t and ball_down_t < total_dur:
                end_banner = f"回合尾段 · 估算 {total_shots} 拍"
                f.write(f"Dialogue: 1,{fmt_ass_time(ball_down_t)},{fmt_ass_time(total_dur)},ShotBadge,,0,0,0,,{end_banner}\\n\n")

            # Running millisecond timer (0.1s increments)
            step = 0.1
            cur = 0.0
            dur_s = int(total_dur)
            dur_ms = int((total_dur - dur_s) * 10)
            while cur < total_dur:
                nxt = min(total_dur, cur + step)
                cur_s = int(cur)
                cur_ms = int((cur - cur_s) * 10)

                cur_shot = 0
                if verified_shots:
                    for i, hit in enumerate(verified_shots):
                        next_t = verified_shots[i + 1][0] if i + 1 < len(verified_shots) else ball_down_t
                        if hit[0] <= cur < next_t:
                            cur_shot = i + 1
                            break
                    if ball_down_t and cur >= ball_down_t:
                        cur_shot = total_shots

                timer_text = f"⏱️ 实时对决: 00:{cur_s:02d}.{cur_ms}  /  00:{dur_s:02d}.{dur_ms}   [当前第 {cur_shot}/{total_shots} 拍]"
                f.write(f"Dialogue: 2,{fmt_ass_time(cur)},{fmt_ass_time(nxt)},Timer,,0,0,0,,{timer_text}\\n\n")
                cur = nxt

        cmd = [
            ffmpeg_bin, "-y",
            "-i", os.path.abspath(clip_path),
            "-vf", "ass=hud.ass",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "copy",
            out_path
        ]
        run_media_export(ffmpeg_bin, cmd[2:-1], cmd[-1], cwd=staging)


def main():
    parser = argparse.ArgumentParser(description="羽毛球比赛视频自动剪辑与回合时间轴")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--input", "-i", required=True, help="比赛视频文件或视频目录")
    parser.add_argument("--output", "-o", required=True, help="输出目录")
    parser.add_argument(
        "--mode", default="all",
        choices=["all", "highlight", "duopai", "serve_kill", "condensed", "vertical", "solo", "showcase"],
        help="默认 all 为多拍和接发秒杀候选，condensed 为多拍纯享",
    )
    parser.add_argument("--player", choices=[*PLAYER_QUADRANTS, "auto"], default="near_left",
                        help="solo 筛选已标注站位，auto 保留所有已标注的回合")
    parser.add_argument("--aspect-ratio", choices=["9:16", "1:1", "16:9"], default="9:16")
    parser.add_argument("--reel", action="store_true", help="额外生成合集")
    parser.add_argument("--gif", action="store_true", help="输出接发秒杀候选 GIF")
    parser.add_argument("--slowmo", action="store_true", help="输出慢动作回放")
    parser.add_argument("--hud", action="store_true", help="输出带估算拍数的 HUD")
    parser.add_argument("--strict-visual", action="store_true", default=True, help="启用视觉验证（默认）")
    parser.add_argument("--split-by-game", dest="split_by_game", action="store_true", default=True)
    parser.add_argument("--no-split-by-game", dest="split_by_game", action="store_false")
    parser.add_argument("--min-hits", type=int, default=5)
    parser.add_argument("--min-duration", type=float, default=5.0)
    parser.add_argument("--lineup-threshold", type=float, default=0.65)
    parser.add_argument("--rest-gap", type=float, default=22.0)
    parser.add_argument("--long-intermission", type=float, default=45.0)
    parser.add_argument("--min-rallies-per-game", type=int, default=8)
    parser.add_argument("--ffmpeg", default=DEFAULT_FFMPEG, help="FFmpeg 路径，亦可设置 BADMINTON_FFMPEG")
    parser.add_argument("--exact", action="store_true", help="帧级精剪，重新编码")
    parser.add_argument("--jobs", type=int, help="导出并发数（流复制默认 8，精剪默认 2）")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--analyze-only", action="store_true", help="仅输出回合时间轴 JSON")
    operation.add_argument("--timeline", help="按现有或人工编辑的时间轴导出，仅接受单个源视频")
    parser.add_argument("--rescan", action="store_true", help="跳过时间轴缓存，重新分析")
    args = parser.parse_args()
    if args.jobs is not None and not 1 <= args.jobs <= 32:
        parser.error("--jobs 必须介于 1 和 32")
    if (args.min_hits < 1 or not math.isfinite(args.min_duration)
            or args.min_duration <= 0 or args.min_rallies_per_game < 1):
        parser.error("拍数和时长必须是有限的正值")
    if not shutil.which(args.ffmpeg):
        parser.error("找不到 FFmpeg，请设置 --ffmpeg 或 BADMINTON_FFMPEG")
    if not HAS_CV2 and not args.timeline:
        parser.error("自动分析需要 OpenCV，请安装 opencv-python-headless")

    source = os.path.abspath(args.input)
    if os.path.isdir(source):
        if args.timeline:
            parser.error("--timeline 需要单个源视频")
        videos = [os.path.join(source, name) for name in sorted(os.listdir(source))
                  if name.lower().endswith(VIDEO_EXTENSIONS) and os.path.isfile(os.path.join(source, name))]
    else:
        videos = [source] if os.path.isfile(source) and source.lower().endswith(VIDEO_EXTENSIONS) else []
    if not videos:
        parser.error("未找到可读的视频文件，支持 MP4、MOV、MKV 和 TS")

    # Imported here so the shared engine can also import the detection helpers.
    from gui_engine import (
        CutterConfig, analyze_video_file, export_batch_timelines, load_timeline_json,
        resolve_match_folder_name, save_timeline_json,
    )
    config = CutterConfig(
        ffmpeg_bin=args.ffmpeg, modes=[args.mode], player=args.player, aspect_ratio=args.aspect_ratio,
        split_by_game=args.split_by_game, reel=args.reel, hud=args.hud, slowmo=args.slowmo, gif=args.gif,
        strict_visual=args.strict_visual, min_hits=args.min_hits, min_duration=args.min_duration,
        lineup_threshold=args.lineup_threshold, rest_gap=args.rest_gap, long_intermission=args.long_intermission,
        min_rallies_per_game=args.min_rallies_per_game, exact=args.exact, jobs=args.jobs,
    )
    started = time.monotonic()
    timelines = []
    errors = []
    for idx, path in enumerate(videos, 1):
        try:
            if args.timeline:
                timeline = load_timeline_json(args.timeline)
                if timeline is None:
                    raise ValueError("时间轴 JSON 不可读")
                if timeline.source_identity and timeline.source_identity != list(source_fingerprint(path)):
                    raise ValueError("时间轴与当前源文件不匹配，请重新分析")
                if not timeline.source_identity:
                    duration = get_video_duration(path, args.ffmpeg)
                    if duration <= 0:
                        raise ValueError("无法读取源视频时长")
                    timeline.duration = duration
                if any(not 0 <= seg.s_cut < seg.e_cut <= timeline.duration for seg in timeline.segments):
                    raise ValueError("时间轴切点超出源视频范围")
                timeline.video_path = path
                timeline.folder_name, timeline.display_name = resolve_match_folder_name(path, idx)
            else:
                timeline = analyze_video_file(path, idx, config, log_cb=print, use_cache=not args.rescan)
            timelines.append(timeline)
            if args.analyze_only:
                dest = os.path.join(args.output, timeline.folder_name, "match_timeline.json")
                save_timeline_json(timeline, dest)
                print(f"时间轴: {os.path.abspath(dest)}")
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(str(exc))
            print(f"处理失败 [{path}]: {exc}", file=sys.stderr)
    if timelines and not args.analyze_only:
        try:
            results = export_batch_timelines(timelines, args.output, config, log_cb=print)
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"导出失败: {exc}", file=sys.stderr)
            return 1
        artifacts = results["artifacts"] + [path for match in results["matches"] for path in match["artifacts"]]
        print(f"成功生成 {len(artifacts)} 个文件，目录: {os.path.abspath(args.output)}")
    print(f"总耗时 {time.monotonic() - started:.2f} 秒")
    return 1 if errors else 0


if __name__ == "__main__":
    # Keep one module instance when GUI engine imports the detection helpers.
    sys.modules.setdefault("badminton_cutter", sys.modules[__name__])
    raise SystemExit(main())
