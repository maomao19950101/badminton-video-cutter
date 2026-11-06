#!/usr/bin/env python3
"""
Badminton Video Multi-Mode Processing Engine (modes_handler.py).
Provides specialized video editing and analytical modes:
  - condensed: Seamless pure-play match condensation without ball-pickup downtime
  - vertical: 9:16 smart-cropped mobile vertical video for social media (Douyin/Reels/Xiaohongshu)
  - solo: Star player solo focus highlight extraction by court quadrant ReID
  - showcase: Style-based highlight categorization (Smash, Marathon Rally, Fast Drive)
"""

import os
import subprocess
import tempfile
from typing import List, Dict, Any, Optional


VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".ts")
PLAYER_QUADRANTS = ("near_left", "near_right", "far_left", "far_right")


def run_media_export(ffmpeg_bin: str, args: List[str], output_path: str, cwd: Optional[str] = None) -> None:
    """Publish completed FFmpeg outputs atomically and retain useful diagnostics."""
    output_path = os.path.abspath(output_path)
    if cwd and os.path.dirname(ffmpeg_bin):
        ffmpeg_bin = os.path.abspath(ffmpeg_bin)
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".badminton-", suffix=os.path.splitext(output_path)[1], dir=output_dir
    )
    os.close(fd)
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args, temp_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace", cwd=cwd,
        )
        if result.returncode or not os.path.getsize(temp_path):
            detail = result.stderr.strip() or "FFmpeg returned an empty file"
            raise RuntimeError(f"FFmpeg 导出失败 [{output_path}]: {detail}")
        os.replace(temp_path, output_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def generate_condensed_reel(
    ffmpeg_bin: str, clip_paths: List[str], output_path: str
) -> bool:
    if not clip_paths:
        return False
    valid_clips = [c for c in clip_paths if os.path.isfile(c) and os.path.getsize(c) > 0]
    if not valid_clips:
        return False
    if len(valid_clips) != len(clip_paths):
        raise RuntimeError(f"拼接片段缺失或为空: {output_path}")

    with tempfile.TemporaryDirectory(prefix="badminton-concat-") as work_dir:
        list_path = os.path.join(work_dir, "clips.ffconcat")
        with open(list_path, "w", encoding="utf-8", newline="\n") as listing:
            for path in valid_clips:
                path = os.path.abspath(path)
                if os.name == "nt":
                    path = path.replace("\\", "/")
                if "\n" in path or "\r" in path:
                    raise ValueError(f"拼接路径包含换行符: {path!r}")
                escaped = path.replace("'", "'\\''")
                listing.write(f"file '{escaped}'\n")
        run_media_export(
            ffmpeg_bin, ["-f", "concat", "-safe", "0", "-protocol_whitelist", "file",
                         "-i", list_path, "-c", "copy"], output_path
        )
    return True


def generate_vertical_clip(
    ffmpeg_bin: str,
    in_path: str,
    out_path: str,
    aspect_ratio: str = "9:16",
    width: int = 720,
    height: int = 1280
) -> bool:
    if not os.path.isfile(in_path) or not os.path.getsize(in_path):
        return False
    sizes = {"9:16": (width, height), "1:1": (width, width), "16:9": (height, width)}
    target_w, target_h = sizes[aspect_ratio]
    ratio_w, ratio_h = aspect_ratio.split(":")
    crop = (
        f"crop=trunc(min(iw\\,ih*{ratio_w}/{ratio_h})/2)*2:"
        f"trunc(min(ih\\,iw*{ratio_h}/{ratio_w})/2)*2"
    )
    run_media_export(
        ffmpeg_bin,
        ["-i", in_path, "-vf", f"{crop},scale={target_w}:{target_h},setsar=1",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart"],
        out_path,
    )
    return True


def filter_solo_rallies(
    rallies: List[Dict[str, Any]],
    target_player: str = "near_left"
) -> List[Dict[str, Any]]:
    """
    Filters rallies where the designated player quadrant is primary.
    Quadrants: 'near_left', 'near_right', 'far_left', 'far_right'.
    """
    if target_player == "auto":
        return [r for r in rallies if r.get("lead_quadrant") in range(4)]
    target_idx = PLAYER_QUADRANTS.index(target_player.lower())
    return [r for r in rallies if r.get("lead_quadrant") == target_idx]


def categorize_showcase_rallies(
    rallies: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Categorizes rallies by tactical style:
      - 'smash': Explosive smashes and decisive kills
      - 'marathon': Extended multi-shot endurance battles (dur >= 15s)
      - 'drive': Fast flat-drive exchanges and rapid net battles
    """
    categories: Dict[str, List[Dict[str, Any]]] = {
        "01_后场重杀突破": [],
        "02_多拍高能拉锯": [],
        "03_网前平抽快攻": [],
        "04_打法未判定": [],
    }

    for r in rallies:
        dur = r.get("dur", r.get("e_cut", 0.0) - r.get("s_cut", 0.0))
        is_smash = r.get("is_smash", False)

        if is_smash:
            categories["01_后场重杀突破"].append(r)
        elif dur >= 15.0:
            categories["02_多拍高能拉锯"].append(r)
        elif r.get("is_drive"):
            categories["03_网前平抽快攻"].append(r)
        else:
            categories["04_打法未判定"].append(r)

    return categories
