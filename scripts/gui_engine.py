#!/usr/bin/env python3
"""
GUI Engine & Timeline Controller for Badminton AI Video Cutter (v1.7.0)

Separates video analysis (acoustic + optical motion + player ReID segmentation)
and multi-mode video export so that the visual desktop GUI can:
1. Run 1-click full automatic batch cutting & exporting, OR
2. Scan & preview the interactive rally timeline, fine-tune start/end timestamps
   (via buttons or direct mouse drag on the timeline), toggle individual clips,
   split/merge games, preview start/end video frames or play the rally inline,
   save/load `.timeline.json` caches instantaneously, and export all selected
   video modes at lossless / hardware-accelerated speed.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple
import numpy as np

from badminton_cutter import (
    DEFAULT_FFMPEG,
    HAS_CV2,
    _MOTION_CACHE,
    check_clip_is_real_play,
    concat_clips,
    cut_lossless,
    detect_hits,
    detect_visual_deadball_cutoff,
    extract_audio_wav,
    extract_multi_shot_rallies,
    extract_true_serve_kills,
    fast_camera_match_window,
    format_time_zh,
    generate_broadcast_hud,
    generate_gif,
    generate_slowmo_replay,
    get_video_duration,
    verify_multimodal_shots,
)
from match_segmenter import (
    extract_court_player_embeddings,
    extract_serve_keyframe,
    partition_rallies_by_game,
)
from modes_handler import (
    categorize_showcase_rallies,
    filter_solo_rallies,
    generate_condensed_reel,
    generate_review_package,
    generate_vertical_clip,
)

if HAS_CV2:
    import cv2

_HW_ENCODER_CACHE: Dict[str, str] = {}


def detect_hw_video_encoder(ffmpeg_bin: str = DEFAULT_FFMPEG) -> str:
    """
    Probes available hardware H.264 encoders (NVIDIA NVENC, Intel QSV, AMD AMF on Windows;
    VideoToolbox on macOS) and falls back to `libx264`.
    """
    if ffmpeg_bin in _HW_ENCODER_CACHE:
        return _HW_ENCODER_CACHE[ffmpeg_bin]

    candidates = (
        ["h264_nvenc", "h264_qsv", "h264_amf"]
        if platform.system() == "Windows"
        else ["h264_videotoolbox", "h264_nvenc"]
    )
    for enc in candidates:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=0.1",
            "-c:v",
            enc,
            "-f",
            "null",
            "-",
        ]
        try:
            res = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4
            )
            if res.returncode == 0:
                _HW_ENCODER_CACHE[ffmpeg_bin] = enc
                return enc
        except Exception:
            continue

    _HW_ENCODER_CACHE[ffmpeg_bin] = "libx264"
    return "libx264"


@dataclass
class CutterConfig:
    ffmpeg_bin: str = DEFAULT_FFMPEG
    modes: List[str] = field(default_factory=lambda: ["all"])
    player: str = "near_left"
    aspect_ratio: str = "9:16"
    split_by_game: bool = True
    reel: bool = False
    hud: bool = False
    slowmo: bool = False
    gif: bool = False
    strict_visual: bool = True
    min_hits: int = 5
    min_duration: float = 5.0
    lineup_threshold: float = 0.65
    rest_gap: float = 22.0
    long_intermission: float = 45.0
    min_rallies_per_game: int = 8


@dataclass
class RallySegment:
    uid: int
    kind: str  # "rally" or "serve_kill"
    game_index: int
    s_cut: float
    e_cut: float
    peaks: List[Tuple[float, float]] = field(default_factory=list)
    enabled: bool = True
    surge: float = 0.0

    @property
    def dur(self) -> float:
        return max(0.5, self.e_cut - self.s_cut)

    @property
    def hit_count(self) -> int:
        return len(self.peaks)

    @property
    def label(self) -> str:
        if self.kind == "serve_kill":
            return "【接发突击一拍定死】" if self.surge >= 2.4 else "【发球被一拍定死】"
        return "【超长高能拉锯】" if self.dur >= 15.0 else "【多拍激烈对攻】"

    def to_rally_dict(self) -> dict:
        return {
            "s_cut": self.s_cut,
            "e_cut": self.e_cut,
            "dur": self.dur,
            "peaks": self.peaks,
            "surge": self.surge,
        }

    def to_json_dict(self) -> dict:
        return {
            "uid": int(self.uid),
            "kind": str(self.kind),
            "game_index": int(self.game_index),
            "s_cut": float(self.s_cut),
            "e_cut": float(self.e_cut),
            "peaks": [[float(t), float(v)] for t, v in self.peaks],
            "enabled": bool(self.enabled),
            "surge": float(self.surge),
        }

    @classmethod
    def from_json_dict(cls, d: dict) -> "RallySegment":
        return cls(
            uid=int(d["uid"]),
            kind=str(d.get("kind", "rally")),
            game_index=int(d.get("game_index", 1)),
            s_cut=float(d["s_cut"]),
            e_cut=float(d["e_cut"]),
            peaks=[(float(p[0]), float(p[1])) for p in d.get("peaks", [])],
            enabled=bool(d.get("enabled", True)),
            surge=float(d.get("surge", 0.0)),
        )


@dataclass
class VideoTimeline:
    video_path: str
    display_name: str
    folder_name: str
    duration: float
    stable_start: float = 0.0
    unstable_end: float = 0.0
    segments: List[RallySegment] = field(default_factory=list)

    def get_segment(self, uid: int) -> Optional[RallySegment]:
        for seg in self.segments:
            if seg.uid == uid:
                return seg
        return None

    def adjust_segment_time(
        self, uid: int, delta_start: float = 0.0, delta_end: float = 0.0
    ) -> Optional[RallySegment]:
        seg = self.get_segment(uid)
        if not seg:
            return None
        max_dur = self.duration if self.duration > 0 else 999999.0
        new_s = max(0.0, min(seg.s_cut + delta_start, seg.e_cut - 1.0))
        new_e = min(max_dur, max(new_s + 1.0, seg.e_cut + delta_end))
        seg.s_cut = round(new_s, 2)
        seg.e_cut = round(new_e, 2)
        return seg

    def set_segment_time(
        self, uid: int, new_start: float, new_end: float
    ) -> Optional[RallySegment]:
        seg = self.get_segment(uid)
        if not seg:
            return None
        max_dur = self.duration if self.duration > 0 else 999999.0
        s = max(0.0, min(new_start, max_dur - 1.0))
        e = min(max_dur, max(s + 1.0, new_end))
        seg.s_cut = round(s, 2)
        seg.e_cut = round(e, 2)
        return seg

    def toggle_segment_enabled(
        self, uid: int, enabled: Optional[bool] = None
    ) -> Optional[RallySegment]:
        seg = self.get_segment(uid)
        if not seg:
            return None
        seg.enabled = (not seg.enabled) if enabled is None else bool(enabled)
        return seg

    def split_game_at_segment(self, uid: int) -> bool:
        """
        Splits a new game starting from the given rally segment `uid`.
        All rally segments at or after `uid` have their game_index incremented by 1.
        """
        rally_segs = [s for s in self.segments if s.kind == "rally"]
        target_pos = None
        for idx, s in enumerate(rally_segs):
            if s.uid == uid:
                target_pos = idx
                break
        if target_pos is None or target_pos == 0:
            return False
        for s in rally_segs[target_pos:]:
            s.game_index += 1
        self._normalize_game_indices()
        return True

    def merge_game_with_previous(self, uid: int) -> bool:
        """
        Merges the game containing `uid` into the previous game (`game_index - 1`).
        """
        seg = self.get_segment(uid)
        if not seg or seg.kind != "rally" or seg.game_index <= 1:
            return False
        target_game = seg.game_index
        for s in self.segments:
            if s.kind == "rally" and s.game_index >= target_game:
                s.game_index = max(1, s.game_index - 1)
        self._normalize_game_indices()
        return True

    def _normalize_game_indices(self) -> None:
        rally_segs = [s for s in self.segments if s.kind == "rally"]
        if not rally_segs:
            return
        unique_games = []
        for s in rally_segs:
            if s.game_index not in unique_games:
                unique_games.append(s.game_index)
        mapping = {old_g: new_g for new_g, old_g in enumerate(unique_games, 1)}
        for s in rally_segs:
            s.game_index = mapping[s.game_index]

    @property
    def enabled_rallies(self) -> List[RallySegment]:
        return [s for s in self.segments if s.kind == "rally" and s.enabled]

    @property
    def enabled_serve_kills(self) -> List[RallySegment]:
        return [s for s in self.segments if s.kind == "serve_kill" and s.enabled]

    @property
    def game_count(self) -> int:
        games = {s.game_index for s in self.enabled_rallies}
        return len(games) if games else (1 if self.enabled_rallies else 0)

    def to_dict(self) -> dict:
        return {
            "version": "1.8.1",
            "video_path": self.video_path,
            "display_name": self.display_name,
            "folder_name": self.folder_name,
            "duration": float(self.duration),
            "stable_start": float(self.stable_start),
            "unstable_end": float(self.unstable_end),
            "segments": [s.to_json_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VideoTimeline":
        return cls(
            video_path=str(d["video_path"]),
            display_name=str(d["display_name"]),
            folder_name=str(d["folder_name"]),
            duration=float(d.get("duration", 0.0)),
            stable_start=float(d.get("stable_start", 0.0)),
            unstable_end=float(d.get("unstable_end", 0.0)),
            segments=[RallySegment.from_json_dict(s) for s in d.get("segments", [])],
        )


def get_default_timeline_cache_path(vpath: str) -> str:
    cache_dir = os.path.join(tempfile.gettempdir(), "badminton_timeline_cache")
    os.makedirs(cache_dir, exist_ok=True)
    abs_p = os.path.abspath(vpath)
    mtime = int(os.path.getmtime(abs_p)) if os.path.exists(abs_p) else 0
    key = hashlib.md5(f"{abs_p}:{mtime}".encode("utf-8")).hexdigest()[:12]
    bname = os.path.splitext(os.path.basename(abs_p))[0]
    return os.path.join(cache_dir, f"{bname}_{key}.timeline.json")


def save_timeline_json(timeline: VideoTimeline, path: Optional[str] = None) -> str:
    if path is None:
        path = get_default_timeline_cache_path(timeline.video_path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(timeline.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def load_timeline_json(path: str) -> Optional[VideoTimeline]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return VideoTimeline.from_dict(data)
    except Exception:
        return None


def try_load_cached_timeline(vpath: str) -> Optional[VideoTimeline]:
    # Check sidecar file next to video first, then temp cache
    sidecar = os.path.splitext(vpath)[0] + ".timeline.json"
    if os.path.exists(sidecar):
        tl = load_timeline_json(sidecar)
        if tl:
            tl.video_path = vpath
            return tl
    cache_p = get_default_timeline_cache_path(vpath)
    if os.path.exists(cache_p):
        return load_timeline_json(cache_p)
    return None


MATCH_MAPPING = {
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
ZH_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def resolve_match_folder_name(vpath: str, idx: int = 1) -> Tuple[str, str]:
    vname = os.path.splitext(os.path.basename(vpath))[0]
    if vname in MATCH_MAPPING:
        folder_name = MATCH_MAPPING[vname]
    else:
        zh_idx = ZH_NUMS[idx - 1] if 1 <= idx <= len(ZH_NUMS) else str(idx)
        parts = vname.split("_")
        suffix = parts[-1] if len(parts) >= 2 else vname
        folder_name = f"{idx:02d}_场次{zh_idx}_双打实战_{suffix}"
    display_name = folder_name.split("_", 1)[1] if "_" in folder_name else vname
    return folder_name, display_name


def extract_preview_frame_rgb(
    vpath: str,
    t_sec: float,
    width: int = 440,
    height: int = 248,
    ffmpeg_bin: str = DEFAULT_FFMPEG,
) -> Optional[np.ndarray]:
    """
    Extracts a single RGB24 preview frame at `t_sec` scaled to `width x height`.
    Returns a numpy array of shape (height, width, 3) dtype uint8, or None on error.
    """
    if not vpath or not os.path.exists(vpath):
        return None
    cmd = [
        ffmpeg_bin,
        "-ss",
        f"{max(0.0, t_sec):.2f}",
        "-i",
        vpath,
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:{height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    try:
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8
        )
        expected = width * height * 3
        if len(res.stdout) >= expected:
            arr = np.frombuffer(res.stdout[:expected], dtype=np.uint8)
            return arr.reshape((height, width, 3))
    except Exception:
        return None
    return None


def extract_clip_preview_frames(
    vpath: str,
    s_cut: float,
    dur: float,
    fps_out: int = 8,
    width: int = 360,
    height: int = 185,
    ffmpeg_bin: str = DEFAULT_FFMPEG,
) -> List[Tuple[float, np.ndarray]]:
    """
    Extracts a sequence of `(timestamp_sec, rgb_frame)` for inline GUI playback.
    """
    if not vpath or not os.path.exists(vpath) or dur <= 0:
        return []
    play_dur = min(25.0, max(1.0, dur))
    cmd = [
        ffmpeg_bin,
        "-ss",
        f"{max(0.0, s_cut):.2f}",
        "-i",
        vpath,
        "-t",
        f"{play_dur:.2f}",
        "-vf",
        f"fps={fps_out},scale={width}:{height}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    frames = []
    frame_bytes = width * height * 3
    try:
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15
        )
        raw = res.stdout
        n_frames = len(raw) // frame_bytes
        for i in range(n_frames):
            chunk = raw[i * frame_bytes : (i + 1) * frame_bytes]
            arr = np.frombuffer(chunk, dtype=np.uint8).reshape((height, width, 3))
            t_cur = s_cut + (i / float(fps_out))
            frames.append((t_cur, arr))
    except Exception:
        pass
    return frames


def analyze_video_file(
    vpath: str,
    idx: int = 1,
    config: Optional[CutterConfig] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    use_cache: bool = True,
) -> VideoTimeline:
    """
    Scans a badminton match video to build an interactive `VideoTimeline` containing
    verified multi-shot rallies (auto-grouped by game via player ReID) and serve-kill clips.
    Automatically saves `.timeline.json` cache on completion.
    """
    if config is None:
        config = CutterConfig()

    def _log(msg: str):
        if log_cb:
            log_cb(msg)

    def _prog(pct: float, status: str):
        if progress_cb:
            progress_cb(pct, status)

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    if use_cache:
        cached = try_load_cached_timeline(vpath)
        if cached and cached.segments:
            _prog(
                100.0,
                f"已从缓存秒级加载：{len(cached.enabled_rallies)} 个多拍 ({cached.game_count} 局)，{len(cached.enabled_serve_kills)} 个接发秒杀",
            )
            _log(
                f"⚡ [{cached.display_name}] 已秒级加载时间轴缓存：{len(cached.enabled_rallies)} 个多拍（{cached.game_count} 局），{len(cached.enabled_serve_kills)} 个秒杀"
            )
            return cached

    folder_name, display_name = resolve_match_folder_name(vpath, idx)
    v_dur = get_video_duration(vpath, config.ffmpeg_bin)
    timeline = VideoTimeline(
        video_path=vpath,
        display_name=display_name,
        folder_name=folder_name,
        duration=v_dur,
        stable_start=0.0,
        unstable_end=v_dur,
    )

    if v_dur <= 1.0:
        _log(f"⚠️ 视频时长异常或尚未写入完成: {os.path.basename(vpath)}")
        return timeline

    temp_audio_dir = os.path.join(tempfile.gettempdir(), "badminton_audio_cache")
    os.makedirs(temp_audio_dir, exist_ok=True)
    vname = os.path.splitext(os.path.basename(vpath))[0]
    wav_path = os.path.join(temp_audio_dir, f"{vname}.wav")

    _prog(5.0, f"正在提取音频轨: {display_name}...")
    _log(f"🎬 开始扫描视频 [{display_name}] (总时长: {format_time_zh(v_dur)})")
    extract_audio_wav(vpath, wav_path, config.ffmpeg_bin)
    if _cancelled():
        return timeline

    _prog(15.0, "正在分析高频击球声波峰值...")
    peaks = detect_hits(wav_path)
    _log(f"  🔊 检测到原始声学击球脉冲: {len(peaks)} 次")

    cap = None
    fps = 0.0
    if HAS_CV2:
        cap = cv2.VideoCapture(vpath)
        fps = cap.get(cv2.CAP_PROP_FPS)
        _MOTION_CACHE.clear()

    try:
        _prog(22.0, "正在校准固定机位实战时间窗...")
        stable_start, unstable_end = fast_camera_match_window(cap, fps, v_dur)
        timeline.stable_start = stable_start
        timeline.unstable_end = unstable_end
        peaks = [p for p in peaks if stable_start <= p[0] <= unstable_end]
        _log(
            f"  📷 机位稳定时间窗: {format_time_zh(stable_start)} ~ {format_time_zh(unstable_end)} (有效击球 {len(peaks)} 次)"
        )
        if _cancelled():
            return timeline

        _prog(32.0, "正在提取候选多拍回合与死球截断...")
        rallies = extract_multi_shot_rallies(
            peaks, v_dur, min_hits=config.min_hits, cap=cap, fps=fps, vpath=vpath
        )
        _log(f"  🏸 初步聚合出候选多拍区间: {len(rallies)} 处")

        valid_rallies = []
        total_cand = max(1, len(rallies))
        for r_i, r in enumerate(rallies, 1):
            if _cancelled():
                return timeline
            if r_i % 5 == 0 or r_i == total_cand:
                pct = 32.0 + 30.0 * (r_i / total_cand)
                _prog(pct, f"正在精验多拍与死球切分 ({r_i}/{total_cand})...")

            s_cut = r["s_cut"]
            e_cut = r["e_cut"]
            r_peaks = r["peaks"]

            if s_cut < stable_start or e_cut > unstable_end:
                continue

            if config.strict_visual:
                if not check_clip_is_real_play(
                    cap,
                    fps,
                    s_cut,
                    e_cut,
                    min_dur=config.min_duration,
                    r_peaks=r_peaks,
                    stable_start=stable_start,
                    unstable_end=unstable_end,
                    vpath=vpath,
                    min_hits=config.min_hits,
                ):
                    continue
                e_cut, r_peaks = detect_visual_deadball_cutoff(
                    vpath, s_cut, e_cut, r_peaks, cap=cap, fps=fps
                )

            dur = e_cut - s_cut
            if dur < config.min_duration or len(r_peaks) < config.min_hits:
                continue

            if valid_rallies:
                prev_r = valid_rallies[-1]
                turnaround = s_cut - prev_r["e_cut"]
                hit_gap = r_peaks[0][0] - prev_r["peaks"][-1][0]
                if turnaround < 3.0:
                    prev_had_smash = any(
                        prev_r["peaks"][k][1] >= 4.5e7
                        for k in range(
                            max(0, len(prev_r["peaks"]) - 2), len(prev_r["peaks"])
                        )
                    )
                    if hit_gap <= 2.20 and not (
                        prev_had_smash and prev_r["peaks"][-1][1] >= 2.0e7
                    ):
                        prev_r["e_cut"] = e_cut
                        prev_r["dur"] = prev_r["e_cut"] - prev_r["s_cut"]
                        prev_r["peaks"].extend(r_peaks)
                        continue
                    elif turnaround < 0.50 and hit_gap < 2.50:
                        continue

            valid_rallies.append(
                {
                    "s_cut": round(s_cut, 2),
                    "e_cut": round(e_cut, 2),
                    "dur": round(dur, 2),
                    "peaks": r_peaks,
                }
            )

        # Assign game indices via Player ReID if enabled
        rally_game_map = {i: 1 for i in range(len(valid_rallies))}
        if config.split_by_game and len(valid_rallies) > 1:
            _prog(68.0, f"正在提取 {len(valid_rallies)} 个回合的球员上衣色彩特征 (ReID)...")
            _log("  👕 正在分析四名球员球衣色彩特征与休息间隔，自动划分球局...")

            def _extract_one_emb(task):
                i_idx, s_t = task
                try:
                    frame = extract_serve_keyframe(
                        vpath, s_t, ffmpeg_bin=config.ffmpeg_bin
                    )
                    embs = extract_court_player_embeddings(frame, num_players=4)
                except Exception:
                    embs = [np.zeros(512, dtype=np.float32) for _ in range(4)]
                return i_idx, embs

            tasks = [(i, vr["s_cut"]) for i, vr in enumerate(valid_rallies)]
            with ThreadPoolExecutor(max_workers=8) as executor:
                emb_results = list(executor.map(_extract_one_emb, tasks))
            emb_results.sort(key=lambda x: x[0])
            embeddings_list = [r[1] for r in emb_results]

            partition_input = [
                {
                    "index": i,
                    "start_time": vr["s_cut"],
                    "end_time": vr["e_cut"],
                    "data": vr,
                }
                for i, vr in enumerate(valid_rallies)
            ]
            game_groups = partition_rallies_by_game(
                partition_input,
                embeddings_list,
                threshold=config.lineup_threshold,
                rest_gap_seconds=config.rest_gap,
                long_intermission_seconds=config.long_intermission,
                min_rallies_per_game=config.min_rallies_per_game,
            )
            for g_idx, g_items in enumerate(game_groups, 1):
                for item in g_items:
                    rally_game_map[item["index"]] = g_idx
            _log(f"  🏆 自动识别并划分为 {len(game_groups)} 局实战对阵！")

        uid_counter = 1
        for i, vr in enumerate(valid_rallies):
            timeline.segments.append(
                RallySegment(
                    uid=uid_counter,
                    kind="rally",
                    game_index=rally_game_map.get(i, 1),
                    s_cut=vr["s_cut"],
                    e_cut=vr["e_cut"],
                    peaks=vr["peaks"],
                    enabled=True,
                )
            )
            uid_counter += 1

        # Also extract serve-and-kill clips if requested by modes
        want_kills = any(m in config.modes for m in ["all", "highlight", "serve_kill"])
        if want_kills:
            _prog(85.0, "正在扫描发球/接发球一拍定死名场面...")
            kills = extract_true_serve_kills(
                cap, fps, vpath, peaks, rallies, stable_start, unstable_end, v_dur
            )
            for k in kills:
                timeline.segments.append(
                    RallySegment(
                        uid=uid_counter,
                        kind="serve_kill",
                        game_index=1,
                        s_cut=round(k["s_cut"], 2),
                        e_cut=round(k["e_cut"], 2),
                        peaks=k.get("peaks", []),
                        enabled=True,
                        surge=float(k.get("surge", 0.0)),
                    )
                )
                uid_counter += 1
            _log(f"  ⚡ 识别到发球/接发秒杀回合: {len(kills)} 处")

        try:
            save_timeline_json(timeline)
        except Exception:
            pass

        _prog(
            100.0,
            f"扫描完成：{len(timeline.enabled_rallies)} 个多拍 ({timeline.game_count} 局)，{len(timeline.enabled_serve_kills)} 个接发秒杀",
        )
        _log(
            f"✅ [{display_name}] 时间轴扫描完成：共 {len(timeline.enabled_rallies)} 个多拍回合（分为 {timeline.game_count} 局），{len(timeline.enabled_serve_kills)} 个接发秒杀"
        )
        return timeline
    finally:
        if cap is not None:
            cap.release()


def export_video_timeline(
    timeline: VideoTimeline,
    output_root: str,
    config: Optional[CutterConfig] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, object]:
    """
    Exports all enabled segments in `timeline` to `output_root` across all selected `config.modes`.
    Returns a summary dictionary with exported paths and counts.
    """
    if config is None:
        config = CutterConfig()

    def _log(msg: str):
        if log_cb:
            log_cb(msg)

    def _prog(pct: float, status: str):
        if progress_cb:
            progress_cb(pct, status)

    def _cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    os.makedirs(output_root, exist_ok=True)
    match_dir = os.path.join(output_root, timeline.folder_name)
    os.makedirs(match_dir, exist_ok=True)

    # Save timeline JSON inside the match output folder as well
    try:
        save_timeline_json(timeline, os.path.join(match_dir, "match_timeline.json"))
    except Exception:
        pass

    enabled_rallies = timeline.enabled_rallies
    enabled_kills = timeline.enabled_serve_kills
    vpath = timeline.video_path

    export_summary = {
        "match_dir": match_dir,
        "rally_clips": [],
        "kill_clips": [],
        "grand_rallies": [],
    }

    # 1. Cut base multi-shot rally clips (grouped by game if split_by_game is True)
    cut_tasks = []
    all_game_dirs = []

    if config.split_by_game and enabled_rallies:
        games_dict: Dict[int, List[RallySegment]] = {}
        for seg in enabled_rallies:
            games_dict.setdefault(seg.game_index, []).append(seg)
        sorted_game_indices = sorted(games_dict.keys())

        summary_lines = [
            "=" * 60,
            "🏸 羽毛球实战视频全自动分局与球员重识别报告 (Match Summary)",
            "=" * 60,
            f"视频源文件: {os.path.basename(vpath)}",
            f"输出总多拍: {len(enabled_rallies)} 处",
            f"划分球局数: {len(sorted_game_indices)} 局",
            "-" * 60,
        ]

        global_order = 1
        for new_g_idx, orig_g_idx in enumerate(sorted_game_indices, 1):
            g_segs = games_dict[orig_g_idx]
            g_start = g_segs[0].s_cut
            g_end = g_segs[-1].e_cut
            g_dur = max(0.0, g_end - g_start)
            g_dir_name = f"第{new_g_idx:02d}局_实战对阵_{len(g_segs)}拍"
            g_dir_path = os.path.join(match_dir, g_dir_name)
            os.makedirs(g_dir_path, exist_ok=True)
            all_game_dirs.append((g_dir_path, new_g_idx, len(g_segs)))

            summary_lines.append(
                f"第{new_g_idx:02d}局 (共 {len(g_segs):02d} 拍):\n"
                f"  时间跨度: {format_time_zh(g_start)} 至 {format_time_zh(g_end)} (比赛时长: {int(g_dur // 60)}分{int(round(g_dur % 60))}秒)\n"
                f"  多拍序号: 多拍01 ~ 多拍{len(g_segs):02d}\n"
                f"  保存目录: {g_dir_name}/\n"
            )

            gpad = 2 if len(g_segs) < 100 else 3
            for r_idx, seg in enumerate(g_segs, 1):
                dur = seg.dur
                name = f"多拍{r_idx:0{gpad}d}_{format_time_zh(seg.s_cut)}至{format_time_zh(seg.e_cut)}_{seg.label}_{int(round(dur))}秒.mp4"
                clip_p = os.path.join(g_dir_path, name)
                cut_tasks.append(
                    (global_order, seg.s_cut, dur, clip_p, dur >= 15.0, g_dir_path, seg)
                )
                global_order += 1

        summary_lines.append("=" * 60)
        summary_path = os.path.join(match_dir, "game_summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f_sum:
            f_sum.write("\n".join(summary_lines) + "\n")
    else:
        pad = 2 if len(enabled_rallies) < 100 else 3
        for r_idx, seg in enumerate(enabled_rallies, 1):
            dur = seg.dur
            name = f"多拍{r_idx:0{pad}d}_{format_time_zh(seg.s_cut)}至{format_time_zh(seg.e_cut)}_{seg.label}_{int(round(dur))}秒.mp4"
            clip_p = os.path.join(match_dir, name)
            cut_tasks.append(
                (r_idx, seg.s_cut, dur, clip_p, dur >= 15.0, match_dir, seg)
            )

    _prog(5.0, f"导出多拍 0/{len(cut_tasks)}")
    _log(f"  ⚡ 正在并行无损导出 {len(cut_tasks)} 段多拍高清视频...")

    clip_paths = []
    dir_to_clips: Dict[str, List[str]] = {}
    seg_to_clip: Dict[int, str] = {}

    if cut_tasks:
        import threading
        _cut_lock = threading.Lock()
        _cut_done = [0]
        _total_cuts = max(1, len(cut_tasks))

        def _do_cut(task):
            c_idx, s, d, out, is_long, pdir, seg_obj = task
            if not _cancelled():
                cut_lossless(config.ffmpeg_bin, vpath, s, d, out)
            with _cut_lock:
                _cut_done[0] += 1
                cur_n = _cut_done[0]
                pct_val = 5.0 + (cur_n / _total_cuts) * 50.0
                _prog(pct_val, f"导出多拍 {cur_n}/{_total_cuts}")
            return c_idx, out, is_long, pdir, seg_obj.uid

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(_do_cut, cut_tasks))
        results.sort(key=lambda x: x[0])
        for c_idx, out, is_long, pdir, seg_uid in results:
            clip_paths.append(out)
            seg_to_clip[seg_uid] = out
            dir_to_clips.setdefault(pdir, []).append(out)
            if is_long:
                export_summary["grand_rallies"].append(out)

    export_summary["rally_clips"] = clip_paths
    if _cancelled():
        return export_summary

    # 2. Optional Multi-shot Reels
    if clip_paths and config.reel:
        _prog(45.0, "正在拼接纯多拍连贯大合集...")
        if all_game_dirs:
            for g_dir_path, g_idx, _ in all_game_dirs:
                g_clips = dir_to_clips.get(g_dir_path, [])
                if g_clips:
                    reel_name = f"00_【第{g_idx:02d}局_纯多拍合集】_全{len(g_clips)}段精选版.mp4"
                    concat_clips(
                        config.ffmpeg_bin, g_clips, os.path.join(g_dir_path, reel_name)
                    )
        else:
            reel_name = f"00_【{timeline.display_name}_纯多拍零死球合集】_全{len(clip_paths)}段精选版.mp4"
            concat_clips(
                config.ffmpeg_bin, clip_paths, os.path.join(match_dir, reel_name)
            )

    # 3. Optional Broadcast HUD
    if clip_paths and config.hud:
        _prog(52.0, "正在渲染转播级实时拍数 HUD 视频...")
        hud_dir = os.path.join(match_dir, "转播级HUD特效")
        os.makedirs(hud_dir, exist_ok=True)
        for clip_p in clip_paths[:3]:
            if _cancelled():
                break
            hud_out = os.path.join(hud_dir, f"HUD_{os.path.basename(clip_p)}")
            dur = get_video_duration(clip_p, config.ffmpeg_bin)
            clip_wav = os.path.join(
                tempfile.gettempdir(), f"{os.path.basename(clip_p)}.wav"
            )
            extract_audio_wav(clip_p, clip_wav, config.ffmpeg_bin)
            c_peaks = detect_hits(clip_wav, th_val=5.0e6)
            verified = verify_multimodal_shots(c_peaks)
            if len(verified) >= 3:
                generate_broadcast_hud(
                    config.ffmpeg_bin,
                    clip_p,
                    verified,
                    hud_out,
                    title=f"焦点拉锯_{int(round(dur))}秒",
                    total_dur=dur,
                )
            if os.path.exists(clip_wav):
                os.remove(clip_wav)

    # 4. Additional Selected Modes (condensed, vertical, solo, review, showcase)
    if "condensed" in config.modes and clip_paths:
        _prog(60.0, "正在生成【一刀不剪·纯享紧凑版】连贯长片...")
        _log("  ⏱️ 正在合成【一刀不剪·纯享紧凑版】连贯视频...")
        if all_game_dirs:
            for g_dir_path, g_idx, _ in all_game_dirs:
                g_clips = dir_to_clips.get(g_dir_path, [])
                if g_clips:
                    c_name = f"00_【第{g_idx:02d}局_比赛浓缩纯享】_全{len(g_clips)}段连贯版.mp4"
                    generate_condensed_reel(
                        config.ffmpeg_bin, g_clips, os.path.join(g_dir_path, c_name)
                    )
        else:
            c_name = f"00_【{timeline.display_name}_比赛浓缩纯享】_全{len(clip_paths)}段连贯版.mp4"
            generate_condensed_reel(
                config.ffmpeg_bin, clip_paths, os.path.join(match_dir, c_name)
            )

    if "vertical" in config.modes and clip_paths:
        _prog(68.0, f"正在生成【{config.aspect_ratio} 竖屏短视频】...")
        _log(f"  📱 正在裁剪生成【{config.aspect_ratio} 竖屏短视频】...")
        vert_dir = os.path.join(match_dir, "竖屏9比16自媒体短视频")
        os.makedirs(vert_dir, exist_ok=True)
        for c_path in clip_paths[:5]:
            if _cancelled():
                break
            v_out = os.path.join(vert_dir, f"竖屏_{os.path.basename(c_path)}")
            generate_vertical_clip(
                config.ffmpeg_bin, c_path, v_out, aspect_ratio=config.aspect_ratio
            )

    if "solo" in config.modes and enabled_rallies:
        _prog(74.0, f"正在导出【个人高光 Solo 视角 ({config.player})】...")
        _log(f"  🌟 正在筛选导出【个人高光 Solo 视角 ({config.player})】...")
        rally_dicts = [
            {**seg.to_rally_dict(), "_uid": seg.uid, "index": idx}
            for idx, seg in enumerate(enabled_rallies)
        ]
        solo_selected = filter_solo_rallies(rally_dicts, target_player=config.player)
        solo_dir = os.path.join(match_dir, f"个人高光Solo视角_{config.player}")
        os.makedirs(solo_dir, exist_ok=True)
        solo_clips = []
        for s_item in solo_selected:
            src_clip = seg_to_clip.get(s_item["_uid"])
            if src_clip and os.path.exists(src_clip):
                dst_clip = os.path.join(solo_dir, os.path.basename(src_clip))
                if not os.path.exists(dst_clip):
                    try:
                        os.link(src_clip, dst_clip)
                    except OSError:
                        shutil.copy2(src_clip, dst_clip)
                solo_clips.append(dst_clip)
        if solo_clips:
            solo_reel = os.path.join(
                solo_dir,
                f"00_【个人高光Solo合集_{config.player}】_全{len(solo_clips)}段.mp4",
            )
            generate_condensed_reel(config.ffmpeg_bin, solo_clips, solo_reel)

    if "review" in config.modes and enabled_rallies:
        _prog(80.0, "正在导出【发接发前三拍切片】...")
        _log("  🎓 正在导出【发接发前三拍 3.5秒切片】...")
        rally_dicts = [seg.to_rally_dict() for seg in enabled_rallies]
        generate_review_package(config.ffmpeg_bin, vpath, rally_dicts, match_dir)

    if "showcase" in config.modes and enabled_rallies:
        _prog(86.0, "正在分拣导出【球风分类视频库】...")
        _log("  💥 正在按重杀突破/多拍拉锯/平抽快攻分拣视频...")
        rally_dicts = [
            {**seg.to_rally_dict(), "_uid": seg.uid} for seg in enabled_rallies
        ]
        showcase_cats = categorize_showcase_rallies(rally_dicts)
        showcase_dir = os.path.join(match_dir, "战术风格分类集锦")
        os.makedirs(showcase_dir, exist_ok=True)
        for cat_name, cat_rallies in showcase_cats.items():
            if not cat_rallies:
                continue
            cat_sub = os.path.join(showcase_dir, cat_name)
            os.makedirs(cat_sub, exist_ok=True)
            cat_clip_paths = []
            for cr in cat_rallies:
                src_cp = seg_to_clip.get(cr.get("_uid"))
                if src_cp and os.path.exists(src_cp):
                    dst_cp = os.path.join(cat_sub, os.path.basename(src_cp))
                    if not os.path.exists(dst_cp):
                        try:
                            os.link(src_cp, dst_cp)
                        except OSError:
                            shutil.copy2(src_cp, dst_cp)
                    cat_clip_paths.append(dst_cp)
            if cat_clip_paths:
                c_reel = f"00_【{cat_name}】_全{len(cat_clip_paths)}段大合集.mp4"
                generate_condensed_reel(
                    config.ffmpeg_bin, cat_clip_paths, os.path.join(cat_sub, c_reel)
                )

    # 5. Serve-and-kill clips export
    want_kills = any(m in config.modes for m in ["all", "highlight", "serve_kill"])
    if want_kills and enabled_kills:
        _prog(92.0, f"正在导出 {len(enabled_kills)} 段接发秒杀视频...")
        kill_dir = os.path.join(match_dir, "接发秒杀一拍定死")
        os.makedirs(kill_dir, exist_ok=True)
        kpad = 2 if len(enabled_kills) < 100 else 3
        kill_tasks = []
        for k_idx, kseg in enumerate(enabled_kills, 1):
            dur = kseg.dur
            kname = f"秒杀{k_idx:0{kpad}d}_{format_time_zh(kseg.s_cut)}至{format_time_zh(kseg.e_cut)}_{kseg.label}_{int(round(dur))}秒.mp4"
            kclip_p = os.path.join(kill_dir, kname)
            kill_tasks.append((k_idx, kseg.s_cut, dur, kclip_p))

        def _do_kill_cut(task):
            k_i, s, d, out = task
            if not _cancelled():
                cut_lossless(config.ffmpeg_bin, vpath, s, d, out)
            return k_i, out

        with ThreadPoolExecutor(max_workers=8) as executor:
            k_results = list(executor.map(_do_kill_cut, kill_tasks))
        k_results.sort(key=lambda x: x[0])
        kill_clips = [r[1] for r in k_results]
        export_summary["kill_clips"] = kill_clips

        if config.gif:
            for k_i, kclip_p in enumerate(kill_clips[:5], 1):
                gif_path = os.path.join(kill_dir, f"表情包_{k_i:02d}.gif")
                generate_gif(config.ffmpeg_bin, kclip_p, gif_path, "发球被一拍定死")

        if config.slowmo and kill_clips:
            slowmo_path = os.path.join(kill_dir, "慢动作回放_01.mp4")
            generate_slowmo_replay(config.ffmpeg_bin, kill_clips[0], slowmo_path)

        if config.reel and kill_clips:
            kill_reel_name = f"00_【{timeline.display_name}_发球被一拍定死合集】_全{len(kill_clips)}个名场面.mp4"
            concat_clips(
                config.ffmpeg_bin, kill_clips, os.path.join(kill_dir, kill_reel_name)
            )

    _prog(
        100.0,
        f"导出完成！共输出 {len(clip_paths)} 段多拍、{len(export_summary['kill_clips'])} 段秒杀",
    )
    _log(f"🎉 [{timeline.display_name}] 视频导出完毕！保存目录: {match_dir}")
    return export_summary


def export_batch_timelines(
    timelines: List[VideoTimeline],
    output_root: str,
    config: Optional[CutterConfig] = None,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, object]:
    """
    Exports a batch of `VideoTimeline` objects and compiles cross-match grand
    collections (`00_特别精选_发球被一拍定死大赏` and `00_【全场巅峰超长多拍TOP大集锦】`).
    """
    if config is None:
        config = CutterConfig()

    all_grand_rallies: List[str] = []
    all_grand_kills: List[str] = []
    match_summaries = []
    total_v = max(1, len(timelines))

    for idx, tl in enumerate(timelines, 1):
        if cancel_check and cancel_check():
            break

        def _sub_prog(pct: float, msg: str, i=idx):
            if progress_cb:
                overall = ((i - 1) + pct / 100.0) / total_v * 95.0
                progress_cb(overall, f"[{i}/{total_v}] {msg}")

        res = export_video_timeline(
            tl,
            output_root=output_root,
            config=config,
            progress_cb=_sub_prog,
            log_cb=log_cb,
            cancel_check=cancel_check,
        )
        match_summaries.append(res)
        all_grand_rallies.extend(res.get("grand_rallies", []))
        all_grand_kills.extend(res.get("kill_clips", []))

    if all_grand_kills and not (cancel_check and cancel_check()):
        grand_kill_dir = os.path.join(output_root, "00_特别精选_发球被一拍定死大赏")
        os.makedirs(grand_kill_dir, exist_ok=True)
        for g_idx, kclip in enumerate(all_grand_kills, 1):
            if os.path.exists(kclip):
                base_k = os.path.basename(kclip)
                dest_k = os.path.join(grand_kill_dir, f"全场秒杀{g_idx:02d}_{base_k}")
                if not os.path.exists(dest_k):
                    try:
                        os.link(kclip, dest_k)
                    except OSError:
                        shutil.copy2(kclip, dest_k)
        if config.reel:
            grand_kill_reel = os.path.join(
                grand_kill_dir, "00_【发球被一拍定死_接发秒杀连贯大赏】_全场纯净原画版.mp4"
            )
            concat_clips(config.ffmpeg_bin, all_grand_kills, grand_kill_reel)

    if config.reel and all_grand_rallies and not (cancel_check and cancel_check()):
        grand_reel_path = os.path.join(
            output_root, "00_【全场巅峰超长多拍TOP大集锦】_纯净原画零死球无字幕版.mp4"
        )
        concat_clips(config.ffmpeg_bin, all_grand_rallies, grand_reel_path)

    if progress_cb:
        progress_cb(100.0, f"🎉 全部 {len(match_summaries)} 场视频剪辑与导出完成！")

    return {
        "matches": match_summaries,
        "grand_rallies": all_grand_rallies,
        "grand_kills": all_grand_kills,
    }
