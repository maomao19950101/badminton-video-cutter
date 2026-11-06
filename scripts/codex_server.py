#!/usr/bin/env python3
"""
Codex Studio Local Multimedia & Cutting Server (codex_server.py) v1.8.0

100% Local, Zero-Dependency HTTP/REST + Byte-Range Video Streaming Server for
the Badminton AI Video Cutter Desktop Studio (macOS & Windows).

Features:
- HTTP 206 Partial Content (`Range: bytes=...`) streaming for instant 60fps HTML5 `<video>` seeking
- Instant `.timeline.json` cache loading & real-time persistence
- Native OS file/folder picker integration (macOS Finder `osascript` & Windows Explorer PowerShell)
- Background worker thread for 1-click scan+export, scan-only, and multi-mode export with live progress
"""

import argparse
import hashlib
import math
import secrets
import json
import mimetypes
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from badminton_cutter import DEFAULT_FFMPEG, __version__, format_time_zh
from modes_handler import VIDEO_EXTENSIONS
from gui_engine import (
    CutterConfig,
    VideoTimeline,
    analyze_video_file,
    detect_hw_video_encoder,
    export_batch_timelines,
    save_timeline_json,
    try_load_cached_timeline,
)

def _resolve_ui_html_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "ui", "index.html"),
    ]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates.insert(0, os.path.join(meipass, "ui", "index.html"))
        candidates.insert(1, os.path.join(os.path.dirname(sys.executable), "ui", "index.html"))
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


def _resolve_asset_path(filename: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(base_dir)
    candidates = [
        os.path.join(skill_root, "assets", filename),
        os.path.join(base_dir, "assets", filename),
    ]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates.insert(0, os.path.join(meipass, "assets", filename))
        candidates.insert(1, os.path.join(os.path.dirname(sys.executable), "assets", filename))
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


PREFS_PATH = os.path.join(tempfile.gettempdir(), "badminton_gui_preferences.json")
UI_HTML_PATH = _resolve_ui_html_path()
APP_ICON_PNG_PATH = _resolve_asset_path("app_icon.png")
APP_ICON_ICO_PATH = _resolve_asset_path("app_icon.ico")
SESSION_TOKEN = secrets.token_urlsafe(32)


class StudioState:
    def __init__(self):
        self.lock = threading.Lock()
        self.hw_encoder = detect_hw_video_encoder(DEFAULT_FFMPEG)
        self.theme_mode = "dark"
        self.output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "羽毛球剪辑输出")

        self.video_files: List[str] = []
        self.timelines: Dict[str, VideoTimeline] = {}
        self.current_vpath: Optional[str] = None

        self.is_running = False
        self.cancel_requested = False
        self.progress = 0.0
        self.status_text = "Ready · 点击「一键全自动剪辑输出」，或在时间轴点选/拖拽任意球实时预览微调"
        self.logs: List[str] = [
            f"🏸 Codex Studio v{__version__} 已就绪 (本地硬件编码器: {self.hw_encoder})"
        ]

        self._load_prefs()

    def _load_prefs(self):
        if os.path.exists(PREFS_PATH):
            try:
                with open(PREFS_PATH, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("theme_mode") in ("dark", "light"):
                    self.theme_mode = d["theme_mode"]
                if d.get("output_dir"):
                    self.output_dir = d["output_dir"]
            except Exception:
                pass

    def save_prefs(self, theme_mode: Optional[str] = None, output_dir: Optional[str] = None):
        if theme_mode in ("dark", "light"):
            self.theme_mode = theme_mode
        if output_dir:
            self.output_dir = output_dir
        try:
            with open(PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {"theme_mode": self.theme_mode, "output_dir": self.output_dir},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass

    def add_log(self, msg: str):
        with self.lock:
            ts = time.strftime("%H:%M:%S")
            self.logs.append(f"[{ts}] {msg}")
            if len(self.logs) > 200:
                self.logs = self.logs[-200:]

    def set_progress(self, pct: float, status: str):
        with self.lock:
            self.progress = round(float(pct), 1)
            self.status_text = status

    def register_video(self, vpath: str) -> bool:
        vpath = os.path.realpath(vpath)
        if (not vpath.lower().endswith(VIDEO_EXTENSIONS) or not os.path.isfile(vpath)
                or vpath in self.video_files):
            return False
        self.video_files.append(vpath)
        cached = try_load_cached_timeline(vpath)
        if cached and cached.segments:
            self.timelines[vpath] = cached
        if not self.current_vpath:
            self.current_vpath = vpath
        return True

    def import_folder(self, folder: str) -> int:
        if not os.path.isdir(folder):
            return 0
        added = 0
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(VIDEO_EXTENSIONS):
                if self.register_video(os.path.join(folder, fname)):
                    added += 1
        if added:
            base_name = os.path.basename(os.path.normpath(folder))
            parent_dir = os.path.dirname(os.path.normpath(folder))
            self.output_dir = os.path.join(parent_dir, f"{base_name}羽毛球精彩多拍集锦")
            cached_cnt = sum(1 for v in self.video_files if v in self.timelines)
            self.add_log(
                f"📁 已加载文件夹 [{base_name}] 共 {added} 个视频（{cached_cnt} 个已秒级加载时间轴缓存）"
            )
        return added

    def to_summary_dict(self) -> dict:
        with self.lock:
            videos_list = []
            for v in self.video_files:
                tl = self.timelines.get(v)
                videos_list.append(
                    {
                        "path": v,
                        "id": video_id(v),
                        "name": os.path.basename(v),
                        "cached": tl is not None,
                        "rally_count": len(tl.enabled_rallies) if tl else 0,
                        "kill_count": len(tl.enabled_serve_kills) if tl else 0,
                        "game_count": tl.game_count if tl else 0,
                        "duration": tl.duration if tl else 0.0,
                    }
                )
            cur_tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
            return {
                "version": __version__,
                "hw_encoder": self.hw_encoder,
                "theme_mode": self.theme_mode,
                "output_dir": self.output_dir,
                "videos": videos_list,
                "current_vpath": self.current_vpath,
                "timeline": cur_tl.to_dict() if cur_tl else None,
                "job": {
                    "is_running": self.is_running,
                    "progress": self.progress,
                    "status": self.status_text,
                    "logs": self.logs[-40:],
                },
            }


def video_id(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8", errors="surrogatepass")).hexdigest()


STATE = StudioState()


def native_pick_dialog(kind: str) -> List[str]:
    """
    Opens a native macOS Finder or Windows Explorer dialog for selecting video files or folders.
    """
    sys_name = platform.system()
    if sys_name == "Darwin":
        if kind == "files":
            script = (
                'set theFiles to choose file with prompt "选择羽毛球比赛视频" '
                'of type {"mp4", "mov", "mkv", "MP4", "MOV"} with multiple selections allowed\n'
                'set outStr to ""\n'
                'repeat with f in theFiles\n'
                'set outStr to outStr & (POSIX path of f) & "\\n"\n'
                'end repeat\n'
                'return outStr'
            )
        else:
            prompt = "选择包含羽毛球视频的文件夹" if kind == "folder" else "选择剪辑输出目录"
            script = f'POSIX path of (choose folder with prompt "{prompt}")'
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=120,
            )
            if res.returncode == 0 and res.stdout.strip():
                return [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        except Exception:
            pass
    elif sys_name == "Windows":
        if kind == "files":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                "$f.Filter = 'Video Files (*.mp4;*.mov;*.mkv;*.ts)|*.mp4;*.mov;*.mkv;*.ts|All Files (*.*)|*.*'; "
                "$f.Multiselect = $true; "
                "if ($f.ShowDialog() -eq 'OK') { $f.FileNames -join \"`n\" }"
            )
        else:
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "if ($f.ShowDialog() -eq 'OK') { $f.SelectedPath }"
            )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=120,
            )
            if res.returncode == 0 and res.stdout.strip():
                return [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        except Exception:
            pass
    return []


def extract_jpeg_frame_bytes(vpath: str, t_sec: float, width: int = 960, height: int = 540) -> Optional[bytes]:
    if not vpath or not os.path.isfile(vpath):
        return None
    cmd = [
        DEFAULT_FFMPEG,
        "-ss",
        f"{max(0.0, t_sec):.2f}",
        "-i",
        vpath,
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:{height}",
        "-f",
        "image2pipe",
        "-vcodec",
        "mjpeg",
        "-q:v",
        "4",
        "-",
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
        if res.returncode == 0 and res.stdout:
            return res.stdout
    except Exception:
        pass
    return None


class CodexRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suppress noisy access logs
        pass

    def _send_json(self, data: dict, status: int = 200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _valid_host(self) -> bool:
        return self.headers.get_all("Host", []) == [f"127.0.0.1:{self.server.server_port}"]

    def _registered_video(self, identifier: str) -> Optional[str]:
        for path in STATE.video_files:
            if video_id(path) == identifier and os.path.realpath(path) == path:
                return path
        return None

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 64 * 1024:
            raise ValueError("无效的请求长度")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("请求需要 JSON 对象")
        return data

    def do_GET(self):
        if not self._valid_host():
            self.send_error(403)
            return
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            if not os.path.exists(UI_HTML_PATH):
                self.send_error(404, "UI index.html not found")
                return
            with open(UI_HTML_PATH, "rb") as f:
                content = f.read().replace(b"__STUDIO_SESSION_TOKEN__", SESSION_TOKEN.encode("ascii"))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(content)
            return

        if route in ("/api/icon", "/app_icon.png"):
            if not os.path.exists(APP_ICON_PNG_PATH):
                self.send_error(404, "App icon not found")
                return
            with open(APP_ICON_PNG_PATH, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            return

        if route == "/favicon.ico":
            icon_file = APP_ICON_ICO_PATH if os.path.exists(APP_ICON_ICO_PATH) else APP_ICON_PNG_PATH
            if not os.path.exists(icon_file):
                self.send_error(404, "Favicon not found")
                return
            with open(icon_file, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/x-icon" if icon_file.endswith(".ico") else "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            return

        if route == "/api/state":
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/frame":
            vpath = self._registered_video(qs.get("id", [""])[0])
            if not vpath:
                self.send_error(404, "Video not registered")
                return
            try:
                t_sec = float(qs.get("t", ["0"])[0])
                if not math.isfinite(t_sec) or t_sec < 0:
                    raise ValueError
            except ValueError:
                self.send_error(400, "Invalid timestamp")
                return
            jpg = extract_jpeg_frame_bytes(vpath, t_sec)
            if not jpg:
                self.send_error(404, "Frame not available")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.send_header("Cache-Control", "max-age=30")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(jpg)
            return

        if route in ("/api/video", "/api/video_stream"):
            vpath = self._registered_video(qs.get("id", [""])[0])
            self._serve_video_stream(vpath)
            return

        self.send_error(404, "Not Found")

    def _serve_video_stream(self, vpath: str):
        if not vpath or not os.path.isfile(vpath):
            self.send_error(404, "Video file not found")
            return

        file_size = os.path.getsize(vpath)
        range_hdr = self.headers.get("Range")
        ctype = mimetypes.guess_type(vpath)[0] or "video/mp4"

        start = 0
        end = file_size - 1
        status = HTTPStatus.OK

        if range_hdr:
            m = re.fullmatch(r"bytes=(\d{0,20})-(\d{0,20})", range_hdr)
            if not m or not any(m.groups()):
                self.send_error(400, "Invalid Range")
                return
            if not m.group(1):
                start = max(0, file_size - int(m.group(2)))
            else:
                start = int(m.group(1))
                if m.group(2):
                    end = min(file_size - 1, int(m.group(2)))
                else:
                    end = min(file_size - 1, start + 4 * 1024 * 1024 - 1)
            status = HTTPStatus.PARTIAL_CONTENT

        if start >= file_size or end < start:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.send_header("Connection", "close")
            self.end_headers()
            return

        chunk_len = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(chunk_len))
        self.send_header("Connection", "close")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        try:
            with open(vpath, "rb") as f:
                f.seek(start)
                remaining = chunk_len
                while remaining > 0:
                    buf = f.read(min(65536, remaining))
                    if not buf:
                        break
                    self.wfile.write(buf)
                    remaining -= len(buf)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        origin = self.headers.get("Origin")
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        token = self.headers.get("X-Studio-Token", "").encode("latin-1")
        if (not self._valid_host() or (origin and origin != expected_origin)
                or not secrets.compare_digest(token, SESSION_TOKEN.encode("ascii"))):
            self._send_json({"error": "请求来源或工作台会话无效"}, 403)
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json({"error": "需要 JSON 请求"}, 415)
            return
        route = urllib.parse.urlparse(self.path).path
        try:
            body = self._read_json_body()
        except (ValueError, UnicodeError):
            self._send_json({"error": "请求 JSON 无效"}, 400)
            return

        if route == "/api/select_video":
            vpath = body.get("path")
            if vpath in STATE.video_files:
                STATE.current_vpath = vpath
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/browse":
            kind = body.get("kind", "files")  # "files", "folder", "output"
            picked = native_pick_dialog(kind)
            if picked:
                if kind == "files":
                    for p in picked:
                        STATE.register_video(p)
                    STATE.add_log(f"➕ 已添加 {len(picked)} 个视频文件")
                elif kind == "folder":
                    STATE.import_folder(picked[0])
                elif kind == "output":
                    STATE.save_prefs(output_dir=picked[0])
                    STATE.add_log(f"📂 输出目录已更新为: {picked[0]}")
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/add_path":
            raw_path = body.get("path", "").strip()
            if os.path.isdir(raw_path):
                STATE.import_folder(raw_path)
            elif os.path.isfile(raw_path):
                STATE.register_video(raw_path)
                STATE.add_log(f"➕ 已添加视频: {os.path.basename(raw_path)}")
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/remove_video":
            vpath = body.get("path")
            if vpath in STATE.video_files:
                STATE.video_files.remove(vpath)
                STATE.timelines.pop(vpath, None)
                if STATE.current_vpath == vpath:
                    STATE.current_vpath = STATE.video_files[0] if STATE.video_files else None
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/clear_videos":
            STATE.video_files.clear()
            STATE.timelines.clear()
            STATE.current_vpath = None
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/save_prefs":
            STATE.save_prefs(
                theme_mode=body.get("theme_mode"),
                output_dir=body.get("output_dir"),
            )
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/open_folder":
            target = body.get("path") or STATE.output_dir
            os.makedirs(target, exist_ok=True)
            if platform.system() == "Windows":
                os.startfile(target)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
            self._send_json({"ok": True})
            return

        if route == "/api/update_segment":
            tl = STATE.timelines.get(STATE.current_vpath) if STATE.current_vpath else None
            if not tl:
                self._send_json({"error": "No active timeline"}, 400)
                return
            uid = int(body.get("uid", 0))
            action = body.get("action")
            if action == "mark_rally":
                quadrant = body.get("lead_quadrant")
                style = body.get("stroke_style", "")
                seg = tl.get_segment(uid)
                if (not seg or seg.kind != "rally" or style not in ("", "smash", "drive")
                        or (quadrant is not None and (type(quadrant) is not int or quadrant not in range(4)))):
                    self._send_json({"error": "无效的回合标注"}, 400)
                    return
                seg.lead_quadrant, seg.stroke_style = quadrant, style
            elif action == "adjust_time":
                ds = float(body.get("delta_start", 0.0))
                de = float(body.get("delta_end", 0.0))
                seg = tl.adjust_segment_time(uid, delta_start=ds, delta_end=de)
                if seg:
                    STATE.add_log(
                        f"✂️ 微调回合 #{seg.uid:02d}: {format_time_zh(seg.s_cut)} → {format_time_zh(seg.e_cut)} ({seg.dur:.1f}s)"
                    )
            elif action == "set_time":
                ns = float(body.get("s_cut", 0.0))
                ne = float(body.get("e_cut", 0.0))
                seg = tl.set_segment_time(uid, ns, ne)
                if seg:
                    STATE.add_log(
                        f"🖱️ 拖拽微调回合 #{seg.uid:02d}: {format_time_zh(seg.s_cut)} → {format_time_zh(seg.e_cut)} ({seg.dur:.1f}s)"
                    )
            elif action == "toggle":
                seg = tl.toggle_segment_enabled(uid)
                if seg:
                    st = "保留" if seg.enabled else "剔除"
                    STATE.add_log(f"🔄 回合 #{seg.uid:02d} 状态已切换为 [{st}]")
            elif action == "split_game":
                if tl.split_game_at_segment(uid):
                    STATE.add_log(f"🏆 已从回合 #{uid:02d} 拆分为新的一局（共 {tl.game_count} 局）")
            elif action == "merge_game":
                if tl.merge_game_with_previous(uid):
                    STATE.add_log(f"🔗 已将该局合并至上一局（共 {tl.game_count} 局）")

            save_timeline_json(tl)
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/start_job":
            if STATE.is_running:
                self._send_json({"error": "Job already running"}, 400)
                return
            job_type = body.get("job_type", "one_click")  # "one_click", "scan_only", "force_rescan", "export_only"
            cfg_data = body.get("config", {})
            out_dir = cfg_data.get("output_dir") or STATE.output_dir
            STATE.save_prefs(output_dir=out_dir)

            config = CutterConfig(
                ffmpeg_bin=DEFAULT_FFMPEG,
                modes=cfg_data.get("modes", ["all"]) or ["all"],
                player=cfg_data.get("player", "near_left"),
                aspect_ratio=cfg_data.get("aspect_ratio", "9:16"),
                split_by_game=bool(cfg_data.get("split_by_game", True)),
                reel=bool(cfg_data.get("reel", False)),
                hud=bool(cfg_data.get("hud", False)),
                slowmo=bool(cfg_data.get("slowmo", False)),
                gif=bool(cfg_data.get("gif", False)),
                exact=bool(cfg_data.get("exact", False)),
                strict_visual=True,
                min_hits=int(cfg_data.get("min_hits", 5)),
                min_duration=float(cfg_data.get("min_duration", 5.0)),
                rest_gap=float(cfg_data.get("rest_gap", 22.0)),
                min_rallies_per_game=int(cfg_data.get("min_rallies_per_game", 8)),
            )

            with STATE.lock:
                if STATE.is_running:
                    self._send_json({"error": "Job already running"}, 400)
                    return
                STATE.is_running = True
                STATE.cancel_requested = False

            def _worker():
                try:
                    total_v = max(1, len(STATE.video_files))
                    if job_type in ("one_click", "scan_only", "force_rescan"):
                        for idx, vp in enumerate(list(STATE.video_files), 1):
                            if STATE.cancel_requested:
                                break

                            def _pscan(pct, msg, i=idx):
                                weight = 0.55 if job_type == "one_click" else 1.0
                                overall = ((i - 1) + (pct / 100.0)) / total_v * (100.0 * weight)
                                STATE.set_progress(overall, f"[扫描 {i}/{total_v}] {msg}")

                            tl = analyze_video_file(
                                vp,
                                idx=idx,
                                config=config,
                                progress_cb=_pscan,
                                log_cb=STATE.add_log,
                                cancel_check=lambda: STATE.cancel_requested,
                                use_cache=(job_type != "force_rescan"),
                            )
                            STATE.timelines[vp] = tl
                            if not STATE.current_vpath:
                                STATE.current_vpath = vp

                    if job_type in ("one_click", "export_only") and not STATE.cancel_requested:
                        items = [STATE.timelines[v] for v in STATE.video_files if v in STATE.timelines]
                        if not items:
                            raise ValueError("请先扫描视频，建立时间轴后再导出")
                        base_pct = 55.0 if job_type == "one_click" else 0.0
                        span_pct = 45.0 if job_type == "one_click" else 100.0
                        result = export_batch_timelines(
                            items,
                            output_root=STATE.output_dir,
                            config=config,
                            progress_cb=lambda pct, msg: STATE.set_progress(
                                base_pct + (pct / 100.0) * span_pct, msg
                            ),
                            log_cb=STATE.add_log,
                            cancel_check=lambda: STATE.cancel_requested,
                        )
                        warnings = [msg for match in result["matches"] for msg in match["warnings"]]
                        if warnings and not STATE.cancel_requested:
                            STATE.set_progress(100.0, f"导出提示: {warnings[0]}")
                except Exception as e:
                    STATE.add_log(f"❌ 任务执行异常: {e}")
                    STATE.set_progress(STATE.progress, f"任务失败: {e}")
                finally:
                    with STATE.lock:
                        STATE.is_running = False

            threading.Thread(target=_worker, daemon=True).start()
            self._send_json(STATE.to_summary_dict())
            return

        if route == "/api/stop_job":
            if STATE.is_running:
                STATE.cancel_requested = True
                STATE.add_log("⏹ 正在安全停止当前任务...")
            self._send_json(STATE.to_summary_dict())
            return

        self.send_error(404, "Unknown API endpoint")


def find_free_port(preferred: int = 18765) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_standalone_app_window(url: str):
    """
    Launches the Codex Studio UI in a standalone desktop app window:
    - On macOS: opens the native `羽毛球AI剪辑大师.app` Cocoa/WKWebView app bundle
      (with the Cat+Badminton Dock icon) and brings it to the foreground, falling back
      to Chrome/Edge app mode and activating the window.
    - On Windows: opens Edge/Chrome `--app=` mode with an isolated profile.
    """
    profile_dir = os.path.join(tempfile.gettempdir(), "badminton_codex_app_profile")
    os.makedirs(profile_dir, exist_ok=True)
    common_flags = [
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        "--window-size=1480,920",
        "--no-first-run",
        "--no-default-browser-check",
        "--proxy-bypass-list=<-loopback>,127.0.0.1,localhost",
    ]
    sys_name = platform.system()
    if sys_name == "Darwin":
        native_app = os.environ.get("BADMINTON_STUDIO_APP")
        if native_app and os.path.exists(native_app):
            subprocess.Popen(
                ["open", "-a", native_app, "--args", f"--url={url}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        chrome_apps = [
            "Google Chrome",
            "Microsoft Edge",
            "Brave Browser",
        ]
        for app_name in chrome_apps:
            app_bundle = f"/Applications/{app_name}.app"
            if os.path.exists(app_bundle):
                subprocess.Popen(
                    ["open", "-na", app_bundle, "--args"] + common_flags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
    elif sys_name == "Windows":
        win_bins = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for wbin in win_bins:
            if os.path.exists(wbin):
                subprocess.Popen(
                    [wbin] + common_flags,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

    webbrowser.open(url)


def is_server_already_running(port: int) -> bool:
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/state", timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("version") == __version__ and "videos" in data
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Codex Studio Local Server for Badminton AI Video Cutter")
    parser.add_argument("--port", type=int, default=18765, help="Preferred local port (default: 18765)")
    parser.add_argument("--no-open", action="store_true", help="Start server without opening desktop app window")
    parser.add_argument("--self-test", action="store_true", help="Run automated server API self-test and exit")
    args = parser.parse_args()

    if not args.self_test and is_server_already_running(args.port):
        url = f"http://127.0.0.1:{args.port}"
        print(f"🏸 Codex Studio Server already active at {url}, opening window...")
        if not args.no_open:
            open_standalone_app_window(url)
        return

    port = find_free_port(args.port)
    server = ThreadingHTTPServer(("127.0.0.1", port), CodexRequestHandler)
    url = f"http://127.0.0.1:{port}"

    if args.self_test:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"{url}/api/state", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert "version" in data
            assert "videos" in data
        print(f"CODEX_SERVER_SELF_TEST_OK ({url})")
        server.shutdown()
        server.server_close()
        return

    print(f"🏸 Codex Studio Local Engine running at: {url}")
    if not args.no_open:
        threading.Timer(0.3, lambda: open_standalone_app_window(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Codex Studio Server...")
        server.shutdown()


if __name__ == "__main__":
    main()
