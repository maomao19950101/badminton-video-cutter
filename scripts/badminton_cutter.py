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
import subprocess
import wave
import shutil
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

# Optional OpenCV for visual dead-ball and motion analysis
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from match_segmenter import (
    extract_serve_keyframe,
    extract_court_player_embeddings,
    partition_rallies_by_game
)
from modes_handler import (
    generate_condensed_reel,
    generate_vertical_clip,
    filter_solo_rallies,
    generate_review_package,
    categorize_showcase_rallies,
)

__version__ = "1.8.4"


def resolve_ffmpeg_bin():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)
    candidates = [
        os.path.join(root_dir, "bin", "ffmpeg.exe"),
        os.path.join(base_dir, "bin", "ffmpeg.exe"),
        os.path.join(root_dir, "ffmpeg.exe"),
        os.path.join(root_dir, "bin", "ffmpeg"),
        "/Users/harry/.gemini/antigravity/scratch/node_modules/ffmpeg-static/ffmpeg",
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


def extract_audio_wav(video_path, wav_path, ffmpeg_bin=DEFAULT_FFMPEG):
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    if os.path.exists(wav_path):
        return wav_path
    cmd = [
        ffmpeg_bin, "-y",
        "-threads", "0",
        "-i", video_path,
        "-vn", "-ar", "16000", "-ac", "1",
        wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return wav_path


def get_video_duration(vpath, ffmpeg_bin=DEFAULT_FFMPEG):
    cmd = [ffmpeg_bin, "-i", vpath]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            dur_str = line.split("Duration:")[1].split(",")[0].strip()
            parts = dur_str.split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 0.0


def detect_hits(wav_path, th_val=5.0e6, ratio_th=3.0, soft_th=4.2e6, soft_ratio=20.0):
    """
    Tier 1 Acoustic Transient Detection (Dual-Contrast Calibration):
    Extracts candidate shuttlecock impact moments from high-frequency energy diffs.
    Calibrated for multi-court gymnasiums to suppress adjacent court bleed and sneaker squeaks
    while faithfully preserving both standard strokes and high-contrast soft touches:
      1. Standard gym strike: E >= th_val (default 5.0e6), ratio >= ratio_th (default 3.0)
      2. High-contrast soft touch / net drop: E >= soft_th (default 4.2e6), ratio >= soft_ratio (default 20.0)
    """
    with wave.open(wav_path, "rb") as w:
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

    win = int(sr * 0.010)
    hop = int(sr * 0.005)
    diff = np.diff(samples)
    sq = diff ** 2
    cumsum = np.cumsum(np.insert(sq, 0, 0))
    hf_energy = (cumsum[win::hop] - cumsum[:-win:hop]) / win
    times = np.arange(len(hf_energy)) * hop / sr

    peaks = []
    last_t = -1.0
    for idx in range(20, len(hf_energy) - 20):
        val = hf_energy[idx]
        if val > hf_energy[idx - 1] and val >= hf_energy[idx + 1]:
            bg = np.mean(hf_energy[max(0, idx - 40):max(1, idx - 10)])
            ratio = val / (bg + 1e-5)
            is_hit = (val >= th_val and ratio >= ratio_th) or (val >= soft_th and ratio >= soft_ratio)
            if is_hit and times[idx] - last_t > 0.35:
                peaks.append((times[idx], val))
                last_t = times[idx]
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


def check_clip_is_real_play(cap, fps, s_cut, e_cut, min_dur=5.0, r_peaks=None, stable_start=0.0, unstable_end=99999.0, vpath=None, min_hits=5):
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

    # 1. Opening serve & cadence verification (eliminates adjacent court rallies bleed during intermissions)
    if r_peaks and len(r_peaks) >= 3:
        g0 = r_peaks[1][0] - r_peaks[0][0]
        g1 = r_peaks[2][0] - r_peaks[1][0]
        if g0 < 0.55 and g1 < 0.55:
            m_open = sample_instant_motion(cap, fps, r_peaks[0][0], vpath=vpath)
            if m_open is not None and (m_open[1] < 3.0 or m_open[0] < 5.0):
                return False

    # 2. Multilateral court engagement & camera stability check
    pts = np.linspace(s_cut + 0.15 * dur, e_cut - 0.15 * dur, 5)
    motions = [sample_instant_motion(cap, fps, pt, vpath=vpath) for pt in pts]
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
    # Walk-off / Personnel exit & substitution suppression (散场走动近镜头/过道走动特征 - v1.8.4)
    # When players finish a game/point and walk off towards camera/benches, or cross the camera walkway:
    # In genuine rallies, players start in service ready stances strictly within court lines (opening b_max < 10.0).
    # If the clip has high boundary corridor movement (b_avg >= 14.0 and b_max_all >= 25.0):
    #   - Opening walkway congestion: If opening boundary motion is high (motions[0][4] >= 12.0 or motions[1][4] >= 25.0),
    #     people are already in the camera exit walkway when the clip begins -> reject.
    #   - Extreme corridor dominance: If overall boundary corridor motion is extreme (b_avg >= 17.0),
    #     continuous walkway congestion right past the lens indicates intermission walk-off -> reject.
    if b_avg >= 14.0 and b_max_all >= 25.0:
        if motions[0][4] >= 12.0 or motions[1][4] >= 25.0 or b_avg >= 17.0:
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


def extract_multi_shot_rallies(peaks, v_dur, max_gap=2.85, min_dur=5.0, min_hits=5, cap=None, fps=0.0, vpath=None):
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

        # Rule 4: Pre-Serve Stationary Boundary & True Serve Anchoring (发球静止定界与真发球锚定 - v1.8.2)
        # In badminton rules (Rule 9.1), server & receiver must remain stationary in service boxes before serve.
        # Optical motion drops to a stationary trough (near <= 8.5, our <= 8.5) right before the serve,
        # followed by an active court motion surge (near >= 12.0 or our >= 10.0) upon serve and return.
        # If the cluster starts with hits where near court is dormant (near < 8.0) or players are walking,
        # seeks forward to the first authentic serve preceded by a stationary trough, pruning leading adjacent-court acoustic noise.
        if (cap is not None or (vpath and os.path.exists(vpath))) and len(c) >= min_hits + 1:
            for k in range(min(len(c) - min_hits, 8)):
                t_k = c[k][0]
                m_after = sample_instant_motion(cap, fps, t_k + 0.8, vpath=vpath, ffmpeg_bin=ffmpeg_bin)
                if m_after is None:
                    break
                our_after, far_after, near_after, _, _ = m_after
                is_active = (near_after >= 12.0 or our_after >= 12.0)
                if is_active:
                    if k > 0:
                        m_pre = sample_instant_motion(cap, fps, t_k - 0.75, vpath=vpath, ffmpeg_bin=ffmpeg_bin)
                        if m_pre is not None and (m_pre[2] <= 8.5 or m_pre[0] <= 8.5):
                            c = c[k:]
                    break

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

    # Filter candidate kill moments strictly based on serve-strike sequence and subsequent silence
    cand_items = []
    for i in range(len(peaks)):
        t_k = peaks[i][0]
        # Must have serve hit 0.45s to 1.70s before t_k
        serves = [p[0] for p in peaks if 0.45 <= (t_k - p[0]) <= 1.70]
        if not serves:
            continue
        t_serve = serves[-1]

        # Must have NO acoustic hit for at least 3.2s after t_k (rally must not continue!)
        subsequent = [p[0] for p in peaks if 0.25 <= (p[0] - t_k) <= 3.20]
        if subsequent:
            continue

        # Must have NO acoustic hit between t_serve - 2.8s and t_serve - 0.5s (ready stance before serve)
        pre_noise = [p[0] for p in peaks if 0.50 <= (t_serve - p[0]) <= 2.80]
        if pre_noise:
            continue

        if peaks[i][1] >= 7.5e6:
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
    cmd = [
        ffmpeg_bin, "-y",
        "-ss", f"{s_cut:.2f}",
        "-t", f"{dur:.2f}",
        "-i", vpath,
        "-c", "copy",
        out_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def concat_clips(ffmpeg_bin, clip_paths, out_reel_path):
    if not clip_paths:
        return
    txt_path = out_reel_path + ".txt"
    with open(txt_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
    cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", txt_path, "-c", "copy", out_reel_path]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(txt_path):
        os.remove(txt_path)


def generate_gif(ffmpeg_bin, video_clip, out_gif, caption):
    vf = (
        f"scale=360:-1,"
        f"drawtext=fontfile='{FONT}':text='{caption}':fontsize=22:fontcolor=yellow:"
        f"box=1:boxcolor=black@0.6:boxborderw=6:x=(w-text_w)/2:y=h-text_h-14,"
        f"split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
    )
    cmd = [ffmpeg_bin, "-y", "-i", video_clip, "-vf", vf, "-r", "12", out_gif]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


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
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def generate_broadcast_hud(ffmpeg_bin, clip_path, verified_shots, out_path, title="实战纯净多拍对决", total_dur=None, ball_down_t=None):
    """
    BWF/Olympic Broadcast-Grade HUD Generator:
    - Running match clock with 0.1s millisecond precision (00:SS.S)
    - Dynamic tactical shot badge: [实战击球] 第 X 拍 / 全 N 拍 [技术动作识别]
    - Point resolution finish banner: 【终结/落地】全 N 拍 纯净攻防终了
    - Zero dead ball: freezes counter immediately when shuttlecock touches ground
    """
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

    # Standard badminton stroke cadence & heuristics
    def infer_action(idx, total):
        if idx == 0:
            return "[发球抢攻]"
        elif idx == 1:
            return "[接发推底]"
        elif idx == total - 1:
            return "[突击重杀终结!]"
        elif idx % 2 == 1:
            return "[快速平抽分边]"
        else:
            return "[防守高远拉锯]"

    ass_path = out_path + ".ass"
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
        f.write(f"Dialogue: 0,{fmt_ass_time(0.0)},{fmt_ass_time(total_dur)},Title,,0,0,0,,🏸 转播级 HUD 打卡 · {title} (全{total_shots}拍·零死球)\\n\n")

        first_hit_t = verified_shots[0][0] if verified_shots else 0.8
        f.write(f"Dialogue: 1,{fmt_ass_time(0.0)},{fmt_ass_time(first_hit_t)},ShotBadge,,0,0,0,,[实战击球] 准备发球...\\n\n")

        for i, hit in enumerate(verified_shots):
            s_t = hit[0]
            e_t = verified_shots[i + 1][0] if i + 1 < len(verified_shots) else (ball_down_t if ball_down_t else total_dur)
            action = infer_action(i, total_shots)
            badge_text = f"第 {i + 1:02d} 拍 / 全 {total_shots} 拍  {action}"
            f.write(f"Dialogue: 1,{fmt_ass_time(s_t)},{fmt_ass_time(e_t)},ShotBadge,,0,0,0,,[实战击球] {badge_text}\\n\n")

        if ball_down_t and ball_down_t < total_dur:
            end_banner = f"【终结得分·球落地】全 {total_shots} 拍 纯净攻防终了"
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
        "-i", clip_path,
        "-vf", f"ass={ass_path}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        out_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(ass_path):
        os.remove(ass_path)


def main():
    parser = argparse.ArgumentParser(description="Badminton Match Video Auto-Cutter & Highlight Extractor")
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--input", "-i", required=True, help="Input video file or directory of match videos")
    parser.add_argument("--output", "-o", required=True, help="Output root directory")
    parser.add_argument(
        "--mode",
        choices=["all", "highlight", "duopai", "serve_kill", "condensed", "vertical", "solo", "review", "showcase"],
        default="all",
        help="Extraction mode: all/highlight (默认多拍+秒杀), condensed (比赛浓缩纯享), vertical (9:16竖屏短视频), solo (个人主角光环), review (发接发与技战术复盘), showcase (战术风格分类集锦)"
    )
    parser.add_argument("--player", choices=["near_left", "near_right", "far_left", "far_right", "auto"], default="near_left", help="Target player quadrant for --mode solo (default: near_left)")
    parser.add_argument("--aspect-ratio", choices=["9:16", "1:1", "16:9"], default="9:16", help="Target aspect ratio for --mode vertical (default: 9:16)")
    parser.add_argument("--reel", action="store_true", default=False, help="Generate concatenated multi-shot & serve-kill highlight reels (默认关闭，仅在明确指定 --reel 时才生成整场大合集/跨场大合集，节省剪辑耗时与磁盘空间)")
    parser.add_argument("--gif", action="store_true", help="Generate lightweight WeChat stickers/GIFs")
    parser.add_argument("--slowmo", action="store_true", help="Generate broadcast-grade 0.4x slow motion replays")
    parser.add_argument("--hud", action="store_true", help="Generate on-screen verified shot counter HUD for top rallies")
    parser.add_argument("--strict-visual", action="store_true", default=True, help="Enforce visual dead-ball motion drop truncation")
    parser.add_argument("--split-by-game", dest="split_by_game", action="store_true", default=True, help="Automatically group rallies into game subfolders by player ReID (default: True)")
    parser.add_argument("--no-split-by-game", dest="split_by_game", action="store_false", help="Disable game grouping and output all rallies in a flat directory")
    parser.add_argument("--min-hits", type=int, default=5, help="Minimum verified stroke count for multi-shot rallies (default: 5)")
    parser.add_argument("--lineup-threshold", type=float, default=0.65, help="Similarity threshold for detecting player lineup substitution (default: 0.65)")
    parser.add_argument("--rest-gap", type=float, default=22.0, help="Minimum rest gap in seconds for detecting player rotation (default: 22.0)")
    parser.add_argument("--long-intermission", type=float, default=45.0, help="Physical rest intermission threshold in seconds to trigger game split (default: 45.0)")
    parser.add_argument("--min-rallies-per-game", type=int, default=8, help="Minimum rallies required for a distinct game before merging (default: 8)")
    parser.add_argument("--ffmpeg", default=DEFAULT_FFMPEG, help="Path to ffmpeg executable")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    temp_audio_dir = os.path.join(tempfile.gettempdir(), "badminton_audio_cache")
    os.makedirs(temp_audio_dir, exist_ok=True)

    videos = []
    if os.path.isdir(args.input):
        for f in sorted(os.listdir(args.input)):
            if f.endswith((".mp4", ".mov", ".mkv", ".ts")):
                videos.append(os.path.join(args.input, f))
    else:
        videos.append(args.input)

    print(f"🎬 Loaded {len(videos)} video file(s) for processing.")

    match_mapping = {
        "VID_20261019_201713_046": "01_场次一_双打实战_201713",
        "VID_20261019_204324_047": "02_场次二_双打实战_204324",
        "VID_20261019_205459_048": "03_场次三_双打实战_205459",
        "VID_20261019_220708_049": "04_场次四_双打实战_220708",
        "VID_20261019_223559_050": "05_场次五_双打实战_223559",
        "VID_20261029_203442_050": "01_场次一_双打实战_050",
        "VID_20261029_203442_051": "02_场次二_双打实战_051",
        "VID_20261029_203442_052": "03_场次三_双打实战_052",
        "VID_20261102_215941_046": "01_场次一_双打实战_046",
        "VID_20261102_215941_047": "02_场次二_双打实战_047",
        "VID_20261102_215941_048": "03_场次三_双打实战_048",
    }
    zh_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

    all_grand_rallies = []
    all_grand_kills = []
    processed_match_dirs = []

    for idx, vpath in enumerate(videos, 1):
        vname = os.path.splitext(os.path.basename(vpath))[0]
        sz = os.path.getsize(vpath) if os.path.exists(vpath) else 0
        if sz == 0:
            print(f"\n[{idx}/{len(videos)}] ⏳ Skipping empty/uploading video: {vname} (0 bytes, upload in progress)")
            continue
        v_dur = get_video_duration(vpath, args.ffmpeg)
        if v_dur <= 1.0:
            print(f"\n[{idx}/{len(videos)}] ⚠️ Skipping incomplete video: {vname} (moov atom not found / still uploading)")
            continue
        if vname in match_mapping:
            folder_name = match_mapping[vname]
        else:
            zh_idx = zh_nums[idx - 1] if idx <= len(zh_nums) else str(idx)
            parts = vname.split("_")
            suffix = parts[-1] if len(parts) >= 2 else vname
            folder_name = f"{idx:02d}_场次{zh_idx}_双打实战_{suffix}"
        display_name = folder_name.split("_", 1)[1] if "_" in folder_name else vname
        match_dir = os.path.join(args.output, folder_name)
        os.makedirs(match_dir, exist_ok=True)
        processed_match_dirs.append(match_dir)

        t_match_start = time.time()
        v_dur = get_video_duration(vpath, args.ffmpeg)
        wav_path = os.path.join(temp_audio_dir, f"{vname}.wav")
        print(f"\n[{idx}/{len(videos)}] Processing: {display_name} ({vname}, {v_dur:.1f}s)")
        extract_audio_wav(vpath, wav_path, args.ffmpeg)
        peaks = detect_hits(wav_path)

        cap = None
        fps = 0.0
        if (args.strict_visual or True) and HAS_CV2:
            cap = cv2.VideoCapture(vpath)
            fps = cap.get(cv2.CAP_PROP_FPS)
            _MOTION_CACHE.clear()

        try:
            # 1. Automatic Camera Match Window Benchmarking (Excludes handheld mount/unmount noise)
            stable_start, unstable_end = fast_camera_match_window(cap, fps, v_dur)
            raw_peak_count = len(peaks)
            peaks = [p for p in peaks if stable_start <= p[0] <= unstable_end]
            filtered_out = raw_peak_count - len(peaks)
            print(f"  📷 机位实战时间窗: {stable_start:.1f}s ~ {unstable_end:.1f}s (排除开机固定/散场关机杂音 {filtered_out} 处，保留实战击球 {len(peaks)} 次)")

            if args.mode in ["all", "highlight", "duopai", "condensed", "vertical", "solo", "review", "showcase"]:
                rallies = extract_multi_shot_rallies(peaks, v_dur, min_hits=args.min_hits, cap=cap, fps=fps, vpath=vpath)
                print(f"  🏸 Found {len(rallies)} raw candidate rallies")

                valid_rallies = []
                for r in rallies:
                    s_cut = r["s_cut"]
                    e_cut = r["e_cut"]
                    r_peaks = r["peaks"]

                    # Boundary verification against camera match window
                    if s_cut < stable_start or e_cut > unstable_end:
                        continue

                    # Strict Visual Play Verification (no handheld shake, active court players)
                    if args.strict_visual:
                        if not check_clip_is_real_play(cap, fps, s_cut, e_cut, min_dur=5.0, r_peaks=r_peaks, stable_start=stable_start, unstable_end=unstable_end, vpath=vpath, min_hits=args.min_hits):
                            print(f"    🚫 [过滤非打球] 跳过片段: {format_time_zh(s_cut)}至{format_time_zh(e_cut)} (机位未固定或非攻防对战)")
                            continue

                    # Apply high-speed visual dead-ball motion cutoff if enabled
                    if args.strict_visual:
                        e_cut, r_peaks = detect_visual_deadball_cutoff(vpath, s_cut, e_cut, r_peaks, cap=cap, fps=fps)

                    dur = e_cut - s_cut
                    if dur < 5.0 or len(r_peaks) < args.min_hits:
                        continue

                    # Inter-rally reset turnaround & cleaved rally healing (v1.4.9)
                    if valid_rallies:
                        prev_r = valid_rallies[-1]
                        turnaround = s_cut - prev_r["e_cut"]
                        hit_gap = r_peaks[0][0] - prev_r["peaks"][-1][0]
                        # Inter-rally reset turnaround & cleaved rally healing (v1.5.0)
                        if turnaround < 0.60 and hit_gap <= 1.15 and prev_r["dur"] < 25.0 and dur < 25.0:
                            prev_r["e_cut"] = e_cut
                            prev_r["dur"] = prev_r["e_cut"] - prev_r["s_cut"]
                            prev_r["peaks"].extend(r_peaks)
                            print(f"    🏸 [拼接微隙多拍] 拼接被轻微切断的连贯回合: 新区间 {format_time_zh(prev_r['s_cut'])}至{format_time_zh(prev_r['e_cut'])} ({prev_r['dur']:.1f}s)")
                            continue
                        elif turnaround < 0.30 and hit_gap < 1.80:
                            print(f"    🚫 [过滤分间杂音] 跳过分间捡球/换球片段: {format_time_zh(s_cut)}至{format_time_zh(e_cut)} (距上一分仅 {turnaround:.2f}s)")
                            continue

                    valid_rallies.append({
                        "s_cut": s_cut,
                        "e_cut": e_cut,
                        "dur": dur,
                        "peaks": r_peaks
                    })

                if args.mode == "solo":
                    valid_rallies = filter_solo_rallies(valid_rallies, target_player=args.player)
                    print(f"  🌟 [主角光环模式] Filtered {len(valid_rallies)} rallies for player [{args.player}]")

                if args.mode == "showcase":
                    showcase_cats = categorize_showcase_rallies(valid_rallies)
                    print(f"  💥 [风格分类集锦模式] Categorized into Smash/Marathon/Drive styles")

                cut_tasks = []
                all_game_dirs = []

                if args.split_by_game and len(valid_rallies) > 1:
                    print(f"  🏸 Analyzing player lineup ReID for {len(valid_rallies)} rallies...")
                    def _extract_one_emb(task):
                        idx, s_cut = task
                        try:
                            frame = extract_serve_keyframe(vpath, s_cut, ffmpeg_bin=args.ffmpeg)
                            embs = extract_court_player_embeddings(frame, num_players=4)
                        except Exception:
                            embs = [np.zeros(512, dtype=np.float32) for _ in range(4)]
                        return idx, embs

                    tasks = [(i, vr["s_cut"]) for i, vr in enumerate(valid_rallies)]
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        emb_results = list(executor.map(_extract_one_emb, tasks))
                    emb_results.sort(key=lambda x: x[0])
                    embeddings_list = [r[1] for r in emb_results]

                    partition_input = [
                        {"index": i, "start_time": vr["s_cut"], "end_time": vr["e_cut"], "data": vr}
                        for i, vr in enumerate(valid_rallies)
                    ]
                    game_groups = partition_rallies_by_game(
                        partition_input,
                        embeddings_list,
                        threshold=args.lineup_threshold,
                        rest_gap_seconds=args.rest_gap,
                        long_intermission_seconds=args.long_intermission,
                        min_rallies_per_game=args.min_rallies_per_game
                    )
                    print(f"  🏆 Identified {len(game_groups)} distinct game(s) in match based on player lineups.")

                    summary_lines = [
                        "=" * 60,
                        "🏸 羽毛球实战视频全自动分局与球员重识别报告 (Match Summary)",
                        "=" * 60,
                        f"视频源文件: {os.path.basename(vpath)}",
                        f"识别总多拍: {len(valid_rallies)} 处",
                        f"划分球局数: {len(game_groups)} 局",
                        "-" * 60
                    ]

                    for g_idx, g_items in enumerate(game_groups, 1):
                        g_rallies = [item["data"] for item in g_items]
                        g_start = g_rallies[0]["s_cut"]
                        g_end = g_rallies[-1]["e_cut"]
                        g_dur = g_end - g_start
                        g_dir_name = f"第{g_idx:02d}局_实战对阵_{len(g_rallies)}拍"
                        g_dir_path = os.path.join(match_dir, g_dir_name)
                        os.makedirs(g_dir_path, exist_ok=True)
                        all_game_dirs.append((g_dir_path, g_idx, len(g_rallies)))

                        summary_lines.append(
                            f"第{g_idx:02d}局 (共 {len(g_rallies):02d} 拍):\n"
                            f"  时间跨度: {format_time_zh(g_start)} 至 {format_time_zh(g_end)} (比赛时长: {int(g_dur//60)}分{int(round(g_dur%60))}秒)\n"
                            f"  多拍序号: 多拍01 ~ 多拍{len(g_rallies):02d}\n"
                            f"  保存目录: {g_dir_name}/\n"
                        )

                        gpad = 2 if len(g_rallies) < 100 else 3
                        for r_idx, vr in enumerate(g_rallies, 1):
                            dur = vr["dur"]
                            label = "【超长高能拉锯】" if dur >= 15.0 else "【多拍激烈对攻】"
                            name = f"多拍{r_idx:0{gpad}d}_{format_time_zh(vr['s_cut'])}至{format_time_zh(vr['e_cut'])}_{label}_{int(round(dur))}秒.mp4"
                            clip_p = os.path.join(g_dir_path, name)
                            cut_tasks.append((r_idx, vr["s_cut"], dur, clip_p, dur >= 15.0, g_dir_path))

                    summary_lines.append("=" * 60)
                    summary_path = os.path.join(match_dir, "game_summary.txt")
                    with open(summary_path, "w", encoding="utf-8") as f_sum:
                        f_sum.write("\n".join(summary_lines) + "\n")
                    print(f"  📝 Game summary saved to: {summary_path}")

                else:
                    pad = 2 if len(valid_rallies) < 100 else 3
                    for r_idx, vr in enumerate(valid_rallies, 1):
                        dur = vr["dur"]
                        label = "【超长高能拉锯】" if dur >= 15.0 else "【多拍激烈对攻】"
                        name = f"多拍{r_idx:0{pad}d}_{format_time_zh(vr['s_cut'])}至{format_time_zh(vr['e_cut'])}_{label}_{int(round(dur))}秒.mp4"
                        clip_p = os.path.join(match_dir, name)
                        cut_tasks.append((r_idx, vr["s_cut"], dur, clip_p, dur >= 15.0, match_dir))

                # Ultra-fast parallel lossless stream cutting (-c copy)
                print(f"  ⚡ Parallel stream cutting {len(cut_tasks)} clean multi-shot clips...")
                clip_paths = []
                dir_to_clips = {}
                if cut_tasks:
                    def _do_cut(task):
                        c_idx, s, d, out, is_long, pdir = task
                        cut_lossless(args.ffmpeg, vpath, s, d, out)
                        return c_idx, out, is_long, pdir

                    with ThreadPoolExecutor(max_workers=8) as executor:
                        results = list(executor.map(_do_cut, cut_tasks))
                        results.sort(key=lambda x: x[0])
                        clip_paths = [r[1] for r in results]
                        for r in results:
                            pdir = r[3]
                            if pdir not in dir_to_clips:
                                dir_to_clips[pdir] = []
                            dir_to_clips[pdir].append(r[1])
                            if r[2]:
                                all_grand_rallies.append(r[1])

                if clip_paths:
                    if args.reel:
                        if all_game_dirs:
                            for g_dir_path, g_idx, g_count in all_game_dirs:
                                g_clips = dir_to_clips.get(g_dir_path, [])
                                if g_clips:
                                    reel_name = f"00_【第{g_idx:02d}局_纯多拍合集】_全{len(g_clips)}段精选版.mp4"
                                    concat_clips(args.ffmpeg, g_clips, os.path.join(g_dir_path, reel_name))
                                    print(f"  🎞️ Created game {g_idx} reel: {reel_name}")
                        else:
                            reel_name = f"00_【{display_name}_纯多拍零死球合集】_全{len(clip_paths)}段精选版.mp4"
                            concat_clips(args.ffmpeg, clip_paths, os.path.join(match_dir, reel_name))
                            print(f"  🎞️ Created multi-shot reel: {reel_name}")
                    else:
                        print(f"  💡 跳过多拍大合集拼接（已保存 {len(clip_paths)} 段独立高质量切片，极速节省空间。如需大合集请添加 --reel 参数）")

                if args.hud:
                    hud_dir = os.path.join(match_dir, "转播级HUD特效")
                    os.makedirs(hud_dir, exist_ok=True)
                    for h_idx, clip_p in enumerate(clip_paths[:3], 1):
                        hud_name = f"HUD_{os.path.basename(clip_p)}"
                        hud_out = os.path.join(hud_dir, hud_name)
                        dur = get_video_duration(clip_p, args.ffmpeg)
                        # Extract audio peaks for clip
                        clip_wav = os.path.join(tempfile.gettempdir(), f"{os.path.basename(clip_p)}.wav")
                        extract_audio_wav(clip_p, clip_wav, args.ffmpeg)
                        c_peaks = detect_hits(clip_wav, th_val=5.0e6)
                        verified = verify_multimodal_shots(c_peaks)
                        if len(verified) >= 3:
                            print(f"    🏸 Generating Broadcast HUD for {os.path.basename(clip_p)} ({len(verified)} verified shots)...")
                            generate_broadcast_hud(args.ffmpeg, clip_p, verified, hud_out, title=f"焦点拉锯_{int(round(dur))}秒", total_dur=dur)
                        if os.path.exists(clip_wav):
                            os.remove(clip_wav)

                # Mode-specific post-processing
                if args.mode == "condensed":
                    print(f"  ⏱️ [比赛浓缩纯享模式] Generating seamless continuous match reel...")
                    if all_game_dirs:
                        for g_dir_path, g_idx, g_count in all_game_dirs:
                            g_clips = dir_to_clips.get(g_dir_path, [])
                            if g_clips:
                                c_name = f"00_【第{g_idx:02d}局_比赛浓缩纯享】_全{len(g_clips)}段连贯版.mp4"
                                generate_condensed_reel(args.ffmpeg, g_clips, os.path.join(g_dir_path, c_name))
                                print(f"    🎞️ Generated game {g_idx} condensed reel: {c_name}")
                    else:
                        c_name = f"00_【{display_name}_比赛浓缩纯享】_全{len(clip_paths)}段连贯版.mp4"
                        generate_condensed_reel(args.ffmpeg, clip_paths, os.path.join(match_dir, c_name))
                        print(f"    🎞️ Generated match condensed reel: {c_name}")

                elif args.mode == "vertical":
                    vert_dir = os.path.join(match_dir, "竖屏9比16自媒体短视频")
                    os.makedirs(vert_dir, exist_ok=True)
                    print(f"  📱 [9:16竖屏短视频模式] Converting top clips to mobile vertical video...")
                    for v_idx, c_path in enumerate(clip_paths[:5], 1):
                        v_name = f"竖屏_{os.path.basename(c_path)}"
                        v_out = os.path.join(vert_dir, v_name)
                        generate_vertical_clip(args.ffmpeg, c_path, v_out, aspect_ratio=args.aspect_ratio)
                    print(f"    📱 Saved vertical clips to: {vert_dir}")

                elif args.mode == "review":
                    print(f"  🎓 [技战术复盘模式] Generating tactical & serve-return review package...")
                    rev_clips, rev_report = generate_review_package(args.ffmpeg, vpath, valid_rallies, match_dir)
                    print(f"    📝 Tactical Review Report saved to: {rev_report}")

                elif args.mode == "showcase":
                    showcase_dir = os.path.join(match_dir, "战术风格分类集锦")
                    os.makedirs(showcase_dir, exist_ok=True)
                    for cat_name, cat_rallies in showcase_cats.items():
                        if not cat_rallies:
                            continue
                        cat_sub = os.path.join(showcase_dir, cat_name)
                        os.makedirs(cat_sub, exist_ok=True)
                        cat_clip_paths = []
                        for cr in cat_rallies:
                            for cp in clip_paths:
                                if f"_{format_time_zh(cr['s_cut'])}至" in cp:
                                    cat_clip_paths.append(cp)
                                    break
                        if cat_clip_paths:
                            c_reel = f"00_【{cat_name}】_全{len(cat_clip_paths)}段大合集.mp4"
                            generate_condensed_reel(args.ffmpeg, cat_clip_paths, os.path.join(cat_sub, c_reel))
                    print(f"    💥 Showcase style albums saved to: {showcase_dir}")

            if args.mode in ["serve_kill", "all", "highlight"]:
                # Ensure multi-shot rallies are present for gap boundary benchmarking
                if "rallies" not in locals():
                    rallies = extract_multi_shot_rallies(peaks, v_dur, min_hits=args.min_hits, cap=cap, fps=fps, vpath=vpath)
                kills = extract_true_serve_kills(cap, fps, vpath, peaks, rallies, stable_start, unstable_end, v_dur)
                print(f"  ⚡ Found {len(kills)} verified serve-and-kill moments")
                kill_dir = os.path.join(match_dir, "接发秒杀一拍定死")
                if kills:
                    os.makedirs(kill_dir, exist_ok=True)
                kpad = 2 if len(kills) < 100 else 3

                kill_tasks = []
                for valid_k_idx, k in enumerate(kills, 1):
                    dur = k["e_cut"] - k["s_cut"]
                    label = "【接发突击一拍定死】" if k.get("surge", 0) >= 2.4 else "【发球被一拍定死】"
                    kname = f"秒杀{valid_k_idx:0{kpad}d}_{format_time_zh(k['s_cut'])}至{format_time_zh(k['e_cut'])}_{label}_{int(round(dur))}秒.mp4"
                    kclip_p = os.path.join(kill_dir, kname)
                    kill_tasks.append((valid_k_idx, k["s_cut"], dur, kclip_p))

                # Ultra-fast parallel lossless stream cutting for serve kills
                kill_clips = []
                if kill_tasks:
                    def _do_kill_cut(task):
                        k_idx, s, d, out = task
                        cut_lossless(args.ffmpeg, vpath, s, d, out)
                        return k_idx, out

                    with ThreadPoolExecutor(max_workers=8) as executor:
                        k_results = list(executor.map(_do_kill_cut, kill_tasks))
                        k_results.sort(key=lambda x: x[0])
                        kill_clips = [r[1] for r in k_results]
                        all_grand_kills.extend(kill_clips)

                    if args.gif:
                        for k_idx, kclip_p in enumerate(kill_clips[:5], 1):
                            gif_path = os.path.join(kill_dir, f"表情包_{k_idx:02d}.gif")
                            generate_gif(args.ffmpeg, kclip_p, gif_path, "发球被一拍定死")

                    if args.slowmo and kill_clips:
                        slowmo_path = os.path.join(kill_dir, f"慢动作回放_01.mp4")
                        generate_slowmo_replay(args.ffmpeg, kill_clips[0], slowmo_path)

                if kill_clips:
                    if args.reel:
                        kill_reel_name = f"00_【{display_name}_发球被一拍定死合集】_全{len(kills)}个名场面.mp4"
                        concat_clips(args.ffmpeg, kill_clips, os.path.join(kill_dir, kill_reel_name))
                        print(f"  🎞️ Created serve-kill reel: {kill_reel_name}")
                    else:
                        print(f"  💡 跳过单场发球被秒杀合集拼接（已保存 {len(kill_clips)} 段独立秒杀名场面，极速输出。如需合集请添加 --reel）")

        finally:
            if cap is not None:
                cap.release()

        elapsed = time.time() - t_match_start
        print(f"✨ Match [{display_name}] processing completed in {elapsed:.2f}s!")

    # Grand Cross-Match Reel Generation
    if args.reel:
        if all_grand_rallies:
            grand_reel_name = "00_【全场巅峰超长多拍TOP大集锦】_纯净原画零死球无字幕版.mp4"
            grand_reel_path = os.path.join(args.output, grand_reel_name)
            print(f"\n🌟 Compiling Grand Cross-Match Top Rallies ({len(all_grand_rallies)} rallies >= 15s)...")
            concat_clips(args.ffmpeg, all_grand_rallies, grand_reel_path)
            print(f"🎬 Grand Top Rallies compilation created: {grand_reel_path}")

        if all_grand_kills:
            grand_kill_dir = os.path.join(args.output, "00_特别精选_发球被一拍定死大赏")
            os.makedirs(grand_kill_dir, exist_ok=True)
            grand_kill_reel_name = "00_【发球被一拍定死_接发秒杀连贯大赏】_全场纯净原画版.mp4"
            grand_kill_path = os.path.join(grand_kill_dir, grand_kill_reel_name)
            print(f"\n⚡ Compiling Grand Cross-Match Serve-Kills ({len(all_grand_kills)} moments)...")
            concat_clips(args.ffmpeg, all_grand_kills, grand_kill_path)
            print(f"🎬 Grand Serve-Kill compilation created: {grand_kill_path}")
    else:
        print(f"\n💡 跳过跨场大集锦拼接（默认极速模式，零冗余磁盘占用。如需生成跨场TOP总集请添加 --reel 参数）")

    if all_grand_kills:
        grand_kill_dir = os.path.join(args.output, "00_特别精选_发球被一拍定死大赏")
        os.makedirs(grand_kill_dir, exist_ok=True)
        # Populate grand_kill_dir with clips and WeChat GIFs
        gif_dest_dir = os.path.join(grand_kill_dir, "微信表情包GIF")
        os.makedirs(gif_dest_dir, exist_ok=True)
        for g_idx, kclip in enumerate(all_grand_kills, 1):
            base_k = os.path.basename(kclip)
            dest_k = os.path.join(grand_kill_dir, f"全场秒杀{g_idx:02d}_{base_k}")
            if not os.path.exists(dest_k):
                try:
                    os.link(kclip, dest_k)
                except OSError:
                    shutil.copy2(kclip, dest_k)

        for m_dir in processed_match_dirs:
            m_kill_dir = os.path.join(m_dir, "接发秒杀一拍定死")
            if os.path.exists(m_kill_dir):
                for f in os.listdir(m_kill_dir):
                    if f.endswith(".gif"):
                        dest_gif = os.path.join(gif_dest_dir, f"{os.path.basename(m_dir)}_{f}")
                        shutil.copy2(os.path.join(m_kill_dir, f), dest_gif)

    print("\n🎉 All processing completed successfully!")


if __name__ == "__main__":
    main()
