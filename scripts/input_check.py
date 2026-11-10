"""Check input stability before expensive decoding. Never classify a copy as corrupt."""
import math
import os
import re
import subprocess
import time


def check_input_ready(path, ffmpeg_bin, stable_seconds=1.0, require_audio=True):
    """One bounded check. The caller may queue non-ready inputs for a later retry."""
    before = os.stat(path)
    time.sleep(stable_seconds)
    after = os.stat(path)
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        return False, "文件仍在写入，稍后重试"
    if after.st_size == 0:
        return False, "文件为空，可能尚未复制完成"
    try:
        result = subprocess.run([ffmpeg_bin, "-hide_banner", "-nostdin", "-i", str(path)],
                                capture_output=True, text=True, errors="replace", timeout=15)
    except subprocess.TimeoutExpired:
        return False, "读取视频元数据超时"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match or "Video:" not in result.stderr:
        return False, "视频元数据不可读，可能未复制完成或文件异常"
    duration = int(match[1])*3600 + int(match[2])*60 + float(match[3])
    if not math.isfinite(duration) or duration <= 1:
        return False, "视频时长无效或不足 1 秒"
    if require_audio and "Audio:" not in result.stderr:
        return False, "未检测到音轨，自动分析需要现场声音"
    final = os.stat(path)
    if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (final.st_size, final.st_mtime_ns, final.st_ctime_ns):
        return False, "检查期间文件发生变化，稍后重试"
    return True, "文件稳定且视频元数据可读"
