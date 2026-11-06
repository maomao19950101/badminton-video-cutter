#!/usr/bin/env python3
"""
羽毛球 AI 视频剪辑大师 —— Codex UI 可视化桌面版 (Windows & macOS) v1.8.0

采用 OpenAI Codex / Linear 极简工作台设计语言，内置 Dark（深邃碳黑）与 Light（纯净纸白）双主题一键切换：
- 100% 纯本地高速运行，专注羽毛球实战视频自动剪辑与多模式输出
- 支持「🌙 Dark / ☀️ Light」主题实时无损切换（快捷键 Ctrl+T / Cmd+T），自动记忆主题偏好
- 自定义圆角胶囊按钮 (CodexButton) 与精细 1px 边框卡片，跨 Windows 与 macOS 保持一致的 Codex 视觉质感
- 支持四大场景预设、六大剪辑模式多选、时间轴鼠标拖拽边缘微调、双画面预览与窗口内连续播放
"""

import argparse
import json
import os
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time

os.environ["TK_SILENCE_DEPRECATION"] = "1"

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from badminton_cutter import DEFAULT_FFMPEG, __version__, cut_lossless, format_time_zh
from gui_engine import (
    CutterConfig,
    RallySegment,
    VideoTimeline,
    analyze_video_file,
    detect_hw_video_encoder,
    export_batch_timelines,
    extract_clip_preview_frames,
    extract_preview_frame_rgb,
    save_timeline_json,
    try_load_cached_timeline,
)

# =============================================================================
# Apple Pro NLE Design System Palettes (Dark & Light)
# =============================================================================
THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "name": "dark",
        "bg_app": "#16161A",          # Studio Slate Gray canvas
        "bg_header": "#1E1E24",       # Top navigation bar
        "bg_sidebar": "#1E1E24",      # Left sidebar surface
        "bg_panel": "#1E1E24",        # Main workspace panel
        "bg_card": "#22222A",         # Elevated card surface
        "bg_well": "#141418",         # Input / canvas recessed well
        "bg_hover": "#2A2A34",        # Subtle hover state
        "border": "#2E2E38",          # 1px hairline divider
        "fg_primary": "#F5F5F7",      # Apple SF Pro crisp primary text
        "fg_secondary": "#8E8E93",    # Apple secondary slate label
        "fg_muted": "#636366",        # Apple tertiary hint text
        "btn_primary_bg": "#0A84FF",  # Apple Pro Blue primary action
        "btn_primary_fg": "#FFFFFF",
        "btn_primary_hover": "#0071E3",
        "btn_secondary_bg": "#2C2C34",
        "btn_secondary_fg": "#F5F5F7",
        "btn_secondary_hover": "#383842",
        "accent_emerald": "#0A84FF",  # Apple Pro Blue accent
        "accent_emerald_hover": "#0071E3",
        "accent_amber": "#FF9F0A",
        "accent_blue": "#0A84FF",
        "accent_red": "#FF453A",
        "block_disabled": "#2A2A34",
        "tree_sel_bg": "#0A84FF",
        "tree_sel_fg": "#FFFFFF",
    },
    "light": {
        "name": "light",
        "bg_app": "#F5F5F7",          # Neutral clean workspace backdrop
        "bg_header": "#FFFFFF",       # Pure white top bar
        "bg_sidebar": "#FFFFFF",      # Crisp white sidebar
        "bg_panel": "#FFFFFF",        # Crisp white main surface
        "bg_card": "#F5F5F7",         # Subtle card container
        "bg_well": "#E5E5EA",         # Recessed input / canvas well
        "bg_hover": "#E5E5EA",        # Hover state
        "border": "#D1D1D6",          # 1px crisp light border
        "fg_primary": "#1D1D1F",      # Deep ink primary text
        "fg_secondary": "#86868B",    # Secondary slate text
        "fg_muted": "#AEAEB2",        # Subtle hint text
        "btn_primary_bg": "#0A84FF",  # Apple Pro Blue action
        "btn_primary_fg": "#FFFFFF",
        "btn_primary_hover": "#0071E3",
        "btn_secondary_bg": "#E5E5EA",
        "btn_secondary_fg": "#1D1D1F",
        "btn_secondary_hover": "#D1D1D6",
        "accent_emerald": "#0A84FF",  # Apple Pro Blue accent
        "accent_emerald_hover": "#0071E3",
        "accent_amber": "#D97706",
        "accent_blue": "#0A84FF",
        "accent_red": "#DC2626",
        "block_disabled": "#D1D5DB",
        "tree_sel_bg": "#0A84FF",
        "tree_sel_fg": "#FFFFFF",
    },
}

PLAYER_LABELS = {
    "近端左半场 (near_left)": "near_left",
    "近端右半场 (near_right)": "near_right",
    "远端左半场 (far_left)": "far_left",
    "远端右半场 (far_right)": "far_right",
    "全自动识别焦点 (auto)": "auto",
}

PREFS_PATH = os.path.join(tempfile.gettempdir(), "badminton_gui_preferences.json")


class CodexButton(tk.Canvas):
    """
    Codex-style flat rounded pill button rendered on a Canvas so that background
    colors, 1px hairline borders, hover transitions, and Dark/Light themes render
    identically on both macOS (bypassing Aqua bezel) and Windows.
    """

    def __init__(
        self,
        parent,
        text: str,
        command: Callable,
        variant: str = "secondary",  # "primary", "emerald", "amber", "blue", "danger", "secondary", "ghost"
        font_family: str = "PingFang SC",
        font_size: int = 9,
        bold: bool = False,
        padx: int = 12,
        pady: int = 5,
        radius: int = 6,
    ):
        self._text = text
        self._command = command
        self._variant = variant
        self._font_family = font_family
        self._font_size = font_size
        self._bold = bold
        self._padx = padx
        self._pady = pady
        self._radius = radius
        self._hovered = False
        self._palette = THEMES["dark"]

        font_spec = (font_family, font_size, "bold") if bold else (font_family, font_size)
        # Estimate text dimensions cleanly
        char_w = sum(1.75 if ord(ch) > 127 else 0.95 for ch in text)
        est_w = int(char_w * font_size * 0.72) + padx * 2 + 4
        est_h = int(font_size * 1.65) + pady * 2

        super().__init__(
            parent,
            width=est_w,
            height=est_h,
            bd=0,
            highlightthickness=0,
            relief=tk.FLAT,
            cursor="hand2",
        )
        self._font_spec = font_spec
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonRelease-1>", self._on_click)
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def set_text(self, text: str):
        self._text = text
        char_w = sum(1.75 if ord(ch) > 127 else 0.95 for ch in text)
        est_w = int(char_w * self._font_size * 0.72) + self._padx * 2 + 4
        self.config(width=est_w)
        self._draw()

    def set_variant(self, variant: str):
        self._variant = variant
        self._draw()

    def apply_theme(self, palette: Dict[str, str], parent_bg: Optional[str] = None):
        self._palette = palette
        bg_col = parent_bg if parent_bg else palette["bg_panel"]
        self.configure(bg=bg_col)
        self._draw()

    def _resolve_colors(self) -> Tuple[str, str, str]:
        p = self._palette
        v = self._variant
        if v == "primary":
            bg = p["btn_primary_hover"] if self._hovered else p["btn_primary_bg"]
            fg = p["btn_primary_fg"]
            bd = bg
        elif v == "emerald":
            bg = p["accent_emerald_hover"] if self._hovered else p["accent_emerald"]
            fg = "#FFFFFF"
            bd = bg
        elif v == "amber":
            bg = "#B45309" if self._hovered else p["accent_amber"]
            fg = "#FFFFFF" if p["name"] == "light" else "#111111"
            bd = bg
        elif v == "blue":
            bg = "#1D4ED8" if self._hovered else p["accent_blue"]
            fg = "#FFFFFF"
            bd = bg
        elif v == "danger":
            bg = "#B91C1C" if self._hovered else p["accent_red"]
            fg = "#FFFFFF"
            bd = bg
        elif v == "ghost":
            bg = p["bg_hover"] if self._hovered else p["bg_header"]
            fg = p["fg_primary"]
            bd = p["border"]
        else:  # "secondary"
            bg = p["btn_secondary_hover"] if self._hovered else p["btn_secondary_bg"]
            fg = p["btn_secondary_fg"]
            bd = p["border"]
        return bg, fg, bd

    def _draw(self):
        self.delete("all")
        w = max(24, int(self.winfo_width()))
        h = max(18, int(self.winfo_height()))
        if w <= 24:
            w = int(self["width"])
            h = int(self["height"])
        bg, fg, bd = self._resolve_colors()
        r = min(self._radius, h // 2, w // 2)
        self._create_rounded_rect(1, 1, w - 1, h - 1, r, fill=bg, outline=bd)
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font_spec)

    def _create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _on_enter(self, _e):
        self._hovered = True
        self._draw()

    def _on_leave(self, _e):
        self._hovered = False
        self._draw()

    def _on_click(self, _e):
        if self._command:
            self._command()


class BadmintonCutterGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.hw_encoder = detect_hw_video_encoder(DEFAULT_FFMPEG)
        self.theme_mode: str = "dark"  # "dark" or "light"
        self.palette: Dict[str, str] = THEMES[self.theme_mode]

        self.font_family = "Microsoft YaHei UI" if platform.system() == "Windows" else "PingFang SC"
        self.mono_font = "Consolas" if platform.system() == "Windows" else "Menlo"

        # State
        self.video_files: List[str] = []
        self.timelines: Dict[str, VideoTimeline] = {}
        self.current_vpath: Optional[str] = None
        self.selected_uid: Optional[int] = None
        self.is_running: bool = False
        self.cancel_requested: bool = False
        self.ui_queue: "queue.Queue" = queue.Queue()

        # Themeable widget registry
        self._codex_buttons: List[Tuple[CodexButton, str]] = []
        self._themed_frames: List[Tuple[tk.Widget, str, bool]] = []  # (widget, bg_key, has_border)
        self._themed_labels: List[Tuple[tk.Widget, str, str]] = []   # (widget, bg_key, fg_key)

        # Timeline drag state
        self._drag_mode: Optional[str] = None
        self._drag_uid: Optional[int] = None

        # Inline playback state
        self._inline_playing: bool = False
        self._inline_frames: List[Tuple[float, np.ndarray]] = []
        self._inline_frame_idx: int = 0
        self._playhead_time: Optional[float] = None

        # Preview image references
        self._start_photo = None
        self._end_photo = None

        self._init_vars()
        self._load_preferences()
        self.palette = THEMES.get(self.theme_mode, THEMES["dark"])

        self.root.title(
            f"羽毛球比赛剪辑工作室 · Badminton Studio Pro v{__version__}  [{self.hw_encoder}]"
        )
        self.root.geometry("1440x900")
        self.root.minsize(1200, 780)

        self._build_layout()
        self._bind_shortcuts()
        self.apply_theme(self.theme_mode)
        self._auto_load_default_match_folder()
        self._poll_ui_queue()

    def _init_vars(self):
        default_out = os.path.join(os.path.expanduser("~"), "Desktop", "羽毛球AI剪辑输出")
        if os.path.exists("/Users/harry/视频/1029羽毛球精彩多拍集锦"):
            default_out = "/Users/harry/视频/1029羽毛球精彩多拍集锦"
        self.output_dir_var = tk.StringVar(value=default_out)

        # Five cutting modes (Mode 0 checked by default)
        self.mode_all_var = tk.BooleanVar(value=True)
        self.mode_condensed_var = tk.BooleanVar(value=False)
        self.mode_vertical_var = tk.BooleanVar(value=False)
        self.mode_solo_var = tk.BooleanVar(value=False)
        self.mode_showcase_var = tk.BooleanVar(value=False)

        self.aspect_ratio_var = tk.StringVar(value="9:16")
        self.solo_player_var = tk.StringVar(value="近端左半场 (near_left)")

        # Extra options
        self.split_by_game_var = tk.BooleanVar(value=True)
        self.reel_var = tk.BooleanVar(value=False)
        self.hud_var = tk.BooleanVar(value=False)
        self.slowmo_var = tk.BooleanVar(value=False)
        self.gif_var = tk.BooleanVar(value=False)

        # Sliders
        self.min_hits_var = tk.IntVar(value=5)
        self.min_dur_var = tk.DoubleVar(value=5.0)
        self.rest_gap_var = tk.DoubleVar(value=22.0)
        self.min_rallies_game_var = tk.IntVar(value=8)
        self.lineup_th_var = tk.DoubleVar(value=0.65)

        # Progress
        self.progress_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(
            value="Ready · 点击「一键全自动剪辑输出」，或在时间轴上拖拽边缘微调任意回合后导出"
        )

    def _load_preferences(self):
        if not os.path.exists(PREFS_PATH):
            return
        try:
            with open(PREFS_PATH, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            if "theme_mode" in prefs and prefs["theme_mode"] in ("dark", "light"):
                self.theme_mode = prefs["theme_mode"]
            if "output_dir" in prefs and prefs["output_dir"]:
                self.output_dir_var.set(prefs["output_dir"])
            self.min_hits_var.set(int(prefs.get("min_hits", 5)))
            self.min_dur_var.set(float(prefs.get("min_dur", 5.0)))
            self.rest_gap_var.set(float(prefs.get("rest_gap", 22.0)))
            self.min_rallies_game_var.set(int(prefs.get("min_rallies_game", 8)))
        except Exception:
            pass

    def _save_preferences(self):
        try:
            prefs = {
                "theme_mode": self.theme_mode,
                "output_dir": self.output_dir_var.get(),
                "min_hits": int(self.min_hits_var.get()),
                "min_dur": float(self.min_dur_var.get()),
                "rest_gap": float(self.rest_gap_var.get()),
                "min_rallies_game": int(self.min_rallies_game_var.get()),
            }
            with open(PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _bind_shortcuts(self):
        self.root.bind("<space>", lambda e: self.toggle_inline_playback())
        self.root.bind("<Delete>", lambda e: self.toggle_selected_rally())
        self.root.bind("<BackSpace>", lambda e: self.toggle_selected_rally())
        self.root.bind("<bracketleft>", lambda e: self.adjust_selected_rally(0.0, -0.5))
        self.root.bind("<bracketright>", lambda e: self.adjust_selected_rally(0.0, 0.5))
        self.root.bind("<Control-s>", lambda e: self.save_current_timeline_manual())
        self.root.bind("<Command-s>", lambda e: self.save_current_timeline_manual())
        self.root.bind("<Control-t>", lambda e: self.toggle_theme())
        self.root.bind("<Command-t>", lambda e: self.toggle_theme())

    def _auto_load_default_match_folder(self):
        default_in = "/Users/harry/视频/1029"
        if os.path.isdir(default_in) and not self.video_files:
            self._import_folder_path(default_in, silent=True)

    # -------------------------------------------------------------------------
    # Theme Registration & Dynamic Dark/Light Switching
    # -------------------------------------------------------------------------
    def _reg_frame(self, w: tk.Widget, bg_key: str = "bg_panel", has_border: bool = False) -> tk.Widget:
        self._themed_frames.append((w, bg_key, has_border))
        return w

    def _reg_label(self, w: tk.Widget, bg_key: str = "bg_panel", fg_key: str = "fg_primary") -> tk.Widget:
        self._themed_labels.append((w, bg_key, fg_key))
        return w

    def _make_btn(
        self,
        parent,
        text: str,
        command: Callable,
        variant: str = "secondary",
        bg_key: str = "bg_panel",
        font_size: int = 9,
        bold: bool = False,
        padx: int = 10,
        pady: int = 5,
    ) -> CodexButton:
        btn = CodexButton(
            parent,
            text=text,
            command=command,
            variant=variant,
            font_family=self.font_family,
            font_size=font_size,
            bold=bold,
            padx=padx,
            pady=pady,
        )
        self._codex_buttons.append((btn, bg_key))
        return btn

    def toggle_theme(self):
        new_mode = "light" if self.theme_mode == "dark" else "dark"
        self.apply_theme(new_mode)
        self._save_preferences()
        mode_label = "☀️ Light (纯净纸白)" if new_mode == "light" else "🌙 Dark (深邃碳黑)"
        self.append_log(f"🎨 已切换 Codex 界面主题为: {mode_label}")

    def apply_theme(self, mode: str):
        if mode not in THEMES:
            mode = "dark"
        self.theme_mode = mode
        p = THEMES[mode]
        self.palette = p

        self.root.configure(bg=p["bg_app"])

        # Update ttk styles
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=p["bg_panel"], foreground=p["fg_primary"], font=(self.font_family, 10))
        style.configure("TFrame", background=p["bg_panel"])
        style.configure("Sidebar.TFrame", background=p["bg_sidebar"])
        style.configure("TLabel", background=p["bg_panel"], foreground=p["fg_primary"], font=(self.font_family, 10))
        style.configure("Sidebar.TLabel", background=p["bg_sidebar"], foreground=p["fg_primary"], font=(self.font_family, 10))
        style.configure("Muted.TLabel", background=p["bg_sidebar"], foreground=p["fg_secondary"], font=(self.font_family, 9))
        style.configure("Header.TLabel", background=p["bg_sidebar"], foreground=p["fg_primary"], font=(self.font_family, 10, "bold"))
        style.configure("PanelHeader.TLabel", background=p["bg_panel"], foreground=p["fg_primary"], font=(self.font_family, 10, "bold"))
        style.configure("TCheckbutton", background=p["bg_sidebar"], foreground=p["fg_primary"], font=(self.font_family, 9))
        style.map(
            "TCheckbutton",
            background=[("active", p["bg_hover"])],
            foreground=[("active", p["fg_primary"])],
        )
        style.configure("TCombobox", fieldbackground=p["bg_well"], background=p["bg_card"], foreground=p["fg_primary"])
        style.configure("TSeparator", background=p["border"])
        style.configure("TScale", background=p["bg_sidebar"], troughcolor=p["bg_well"])

        style.configure(
            "Treeview",
            background=p["bg_well"],
            foreground=p["fg_primary"],
            fieldbackground=p["bg_well"],
            rowheight=27,
            borderwidth=0,
            font=(self.font_family, 9),
        )
        style.configure(
            "Treeview.Heading",
            background=p["bg_card"],
            foreground=p["fg_secondary"],
            relief="flat",
            font=(self.font_family, 9, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", p["tree_sel_bg"])],
            foreground=[("selected", p["tree_sel_fg"])],
        )

        style.configure(
            "Codex.Horizontal.TProgressbar",
            troughcolor=p["bg_well"],
            background=p["accent_emerald"],
            bordercolor=p["border"],
            lightcolor=p["accent_emerald"],
            darkcolor=p["accent_emerald"],
            thickness=10,
        )

        # Update registered tk frames
        for w, bg_key, has_border in self._themed_frames:
            w.configure(bg=p[bg_key])
            if has_border:
                w.configure(highlightbackground=p["border"], highlightcolor=p["border"])

        # Update registered tk labels
        for w, bg_key, fg_key in self._themed_labels:
            w.configure(bg=p[bg_key], fg=p[fg_key])

        # Update CodexButtons
        for btn, bg_key in self._codex_buttons:
            btn.apply_theme(p, parent_bg=p[bg_key])

        # Update theme toggle button text
        if hasattr(self, "btn_theme_toggle"):
            toggle_txt = "☀️ Light 模式" if mode == "dark" else "🌙 Dark 模式"
            self.btn_theme_toggle.set_text(toggle_txt)

        # Update listbox, entry, canvases, log console
        if hasattr(self, "video_listbox"):
            self.video_listbox.configure(
                bg=p["bg_well"],
                fg=p["fg_primary"],
                selectbackground=p["accent_emerald"],
                selectforeground="#FFFFFF",
            )
        if hasattr(self, "out_entry"):
            self.out_entry.configure(
                bg=p["bg_well"],
                fg=p["fg_primary"],
                insertbackground=p["fg_primary"],
                highlightbackground=p["border"],
                highlightcolor=p["accent_emerald"],
                highlightthickness=1,
            )
        if hasattr(self, "timeline_canvas"):
            self.timeline_canvas.configure(bg=p["bg_well"], highlightbackground=p["border"])
            self._redraw_timeline_canvas()
        if hasattr(self, "canvas_start_preview"):
            self.canvas_start_preview.configure(bg=p["bg_well"])
            self.canvas_end_preview.configure(bg=p["bg_well"])
        if hasattr(self, "log_text"):
            self.log_text.configure(bg=p["bg_well"], fg=p["fg_secondary"])

    # -------------------------------------------------------------------------
    # Layout Construction (Codex Minimalist Studio Architecture)
    # -------------------------------------------------------------------------
    def _build_layout(self):
        # 1. Top Codex Navigation Bar
        header = self._reg_frame(tk.Frame(self.root, height=52, highlightthickness=1), "bg_header", True)
        header.pack(fill=tk.X, side=tk.TOP)

        title_box = self._reg_frame(tk.Frame(header), "bg_header", False)
        title_box.pack(side=tk.LEFT, padx=14, pady=8)

        self._reg_label(
            tk.Label(title_box, text="🏸 羽毛球比赛剪辑工作室", font=(self.font_family, 13, "bold")),
            "bg_header",
            "fg_primary",
        ).pack(side=tk.LEFT)

        self._reg_label(
            tk.Label(title_box, text=f"  v{__version__} · Studio Pro  ", font=(self.mono_font, 9)),
            "bg_header",
            "accent_blue",
        ).pack(side=tk.LEFT, padx=(6, 0))

        self._reg_label(
            tk.Label(
                title_box,
                text="纯本地引擎 · 球衣ReID自动分第01/02/03局 · 死球零残留 · 时间轴边缘拖拽",
                font=(self.font_family, 9),
            ),
            "bg_header",
            "fg_secondary",
        ).pack(side=tk.LEFT, padx=8)

        # Right side of Header: Theme Toggle + Quick Presets
        hdr_right = self._reg_frame(tk.Frame(header), "bg_header", False)
        hdr_right.pack(side=tk.RIGHT, padx=14, pady=8)

        self.btn_theme_toggle = self._make_btn(
            hdr_right,
            "☀️ Light 模式",
            self.toggle_theme,
            variant="ghost",
            bg_key="bg_header",
            font_size=9,
            bold=True,
            padx=10,
            pady=4,
        )
        self.btn_theme_toggle.pack(side=tk.RIGHT, padx=(10, 0))

        self._make_btn(
            hdr_right, "全模式大满贯", lambda: self.apply_preset("grand_slam"), variant="ghost", bg_key="bg_header", font_size=8, padx=8, pady=4
        ).pack(side=tk.RIGHT, padx=2)
        self._make_btn(
            hdr_right, "抖音 9:16 竖屏", lambda: self.apply_preset("vertical"), variant="ghost", bg_key="bg_header", font_size=8, padx=8, pady=4
        ).pack(side=tk.RIGHT, padx=2)
        self._make_btn(
            hdr_right, "纯享紧凑长片", lambda: self.apply_preset("condensed"), variant="ghost", bg_key="bg_header", font_size=8, padx=8, pady=4
        ).pack(side=tk.RIGHT, padx=2)
        self._make_btn(
            hdr_right, "默认球局多拍", lambda: self.apply_preset("default"), variant="ghost", bg_key="bg_header", font_size=8, padx=8, pady=4
        ).pack(side=tk.RIGHT, padx=2)

        self._reg_label(
            tk.Label(hdr_right, text="预设:", font=(self.font_family, 9)),
            "bg_header",
            "fg_secondary",
        ).pack(side=tk.RIGHT, padx=4)

        # 2. Main Split Workspace: Left Sidebar (435px) + Right Studio Area
        body = self._reg_frame(tk.Frame(self.root), "bg_app", False)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_sidebar = self._reg_frame(
            tk.Frame(body, width=440, highlightthickness=1), "bg_sidebar", True
        )
        left_sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_sidebar.pack_propagate(False)

        right_studio = self._reg_frame(
            tk.Frame(body, highlightthickness=1), "bg_panel", True
        )
        right_studio.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_sidebar(left_sidebar)
        self._build_studio(right_studio)

    def _build_sidebar(self, parent: tk.Frame):
        # Section 1: Video Queue
        sec1 = self._reg_frame(tk.Frame(parent, padx=14, pady=10), "bg_sidebar", False)
        sec1.pack(fill=tk.X)
        ttk.Label(sec1, text="01 / 视频队列与输出路径", style="Header.TLabel").pack(anchor=tk.W)

        btn_row = self._reg_frame(tk.Frame(sec1), "bg_sidebar", False)
        btn_row.pack(fill=tk.X, pady=(8, 6))
        self._make_btn(btn_row, "＋ 添加视频", self.add_video_files, variant="primary", bg_key="bg_sidebar", font_size=9, bold=True).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        self._make_btn(btn_row, "📁 导入文件夹", self.add_video_folder, variant="secondary", bg_key="bg_sidebar", font_size=9).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        self._make_btn(btn_row, "移除", self.remove_selected_video, variant="secondary", bg_key="bg_sidebar", font_size=9).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        self._make_btn(btn_row, "清空", self.clear_video_queue, variant="secondary", bg_key="bg_sidebar", font_size=9).pack(
            side=tk.LEFT
        )

        list_wrap = self._reg_frame(tk.Frame(sec1, highlightthickness=1), "bg_well", True)
        list_wrap.pack(fill=tk.X, pady=4)
        self.video_listbox = tk.Listbox(
            list_wrap,
            height=4,
            font=(self.mono_font, 9),
            borderwidth=0,
            highlightthickness=0,
        )
        self.video_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)
        self.video_listbox.bind("<<ListboxSelect>>", self._on_video_select)
        v_scroll = ttk.Scrollbar(list_wrap, orient=tk.VERTICAL, command=self.video_listbox.yview)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.video_listbox.config(yscrollcommand=v_scroll.set)

        out_row = self._reg_frame(tk.Frame(sec1), "bg_sidebar", False)
        out_row.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(out_row, text="输出目录", style="Muted.TLabel").pack(side=tk.LEFT)
        self._make_btn(out_row, "打开目录 ↗", self.open_output_dir, variant="secondary", bg_key="bg_sidebar", font_size=8, padx=8, pady=2).pack(
            side=tk.RIGHT
        )
        self._make_btn(out_row, "选择...", self.choose_output_dir, variant="secondary", bg_key="bg_sidebar", font_size=8, padx=8, pady=2).pack(
            side=tk.RIGHT, padx=4
        )

        self.out_entry = tk.Entry(
            sec1,
            textvariable=self.output_dir_var,
            relief=tk.FLAT,
            font=(self.mono_font, 9),
        )
        self.out_entry.pack(fill=tk.X, ipady=5, pady=(2, 0))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=14, pady=4)

        # Section 2: Six Output Modes
        sec2 = self._reg_frame(tk.Frame(parent, padx=14, pady=6), "bg_sidebar", False)
        sec2.pack(fill=tk.X)
        ttk.Label(sec2, text="02 / 剪辑输出模式（支持多选）", style="Header.TLabel").pack(anchor=tk.W, pady=(0, 6))

        ttk.Checkbutton(
            sec2,
            text="经典全能合集（默认：自动换人分局 + 多拍 + 接发秒杀）",
            variable=self.mode_all_var,
        ).pack(anchor=tk.W, pady=2)

        ttk.Checkbutton(
            sec2,
            text="一刀不剪·纯享紧凑版（剔除捡球走动，合成连贯长片）",
            variable=self.mode_condensed_var,
        ).pack(anchor=tk.W, pady=2)

        vert_row = self._reg_frame(tk.Frame(sec2), "bg_sidebar", False)
        vert_row.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(
            vert_row,
            text="竖屏短视频模式（自动焦点平滑居中） 比例:",
            variable=self.mode_vertical_var,
        ).pack(side=tk.LEFT)
        ttk.Combobox(
            vert_row,
            textvariable=self.aspect_ratio_var,
            values=["9:16", "1:1", "16:9"],
            width=5,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)

        solo_row = self._reg_frame(tk.Frame(sec2), "bg_sidebar", False)
        solo_row.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(
            solo_row,
            text="个人高光 Solo 视角   站位:",
            variable=self.mode_solo_var,
        ).pack(side=tk.LEFT)
        ttk.Combobox(
            solo_row,
            textvariable=self.solo_player_var,
            values=list(PLAYER_LABELS.keys()),
            width=18,
            state="readonly",
        ).pack(side=tk.LEFT, padx=4)

        ttk.Checkbutton(
            sec2,
            text="球风分类视频库（重杀突破 / 多拍拉锯 / 平抽快攻）",
            variable=self.mode_showcase_var,
        ).pack(anchor=tk.W, pady=2)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=14, pady=4)

        # Section 3: Parameters & Sliders
        sec3 = self._reg_frame(tk.Frame(parent, padx=14, pady=6), "bg_sidebar", False)
        sec3.pack(fill=tk.BOTH, expand=True)

        hdr_row = self._reg_frame(tk.Frame(sec3), "bg_sidebar", False)
        hdr_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(hdr_row, text="03 / 分局与切分灵敏度", style="Header.TLabel").pack(side=tk.LEFT)
        self._make_btn(
            hdr_row, "重置默认", self.reset_default_params, variant="secondary", bg_key="bg_sidebar", font_size=8, padx=8, pady=2
        ).pack(side=tk.RIGHT)

        opt_grid = self._reg_frame(tk.Frame(sec3), "bg_sidebar", False)
        opt_grid.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(opt_grid, text="自动按换人分第01/02/03局", variable=self.split_by_game_var).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8), pady=1
        )
        ttk.Checkbutton(opt_grid, text="拼接整场连贯大合集", variable=self.reel_var).grid(
            row=0, column=1, sticky=tk.W, pady=1
        )
        ttk.Checkbutton(opt_grid, text="转播级实时拍数 HUD", variable=self.hud_var).grid(
            row=1, column=0, sticky=tk.W, padx=(0, 8), pady=1
        )
        ttk.Checkbutton(
            opt_grid,
            text="0.4x慢动作 & 表情包GIF",
            variable=self.slowmo_var,
            command=lambda: self.gif_var.set(self.slowmo_var.get()),
        ).grid(row=1, column=1, sticky=tk.W, pady=1)

        self._add_slider(sec3, "多拍最少击球数 (拍)", self.min_hits_var, 3, 15, is_int=True)
        self._add_slider(sec3, "多拍最短保留秒数 (s)", self.min_dur_var, 3.0, 15.0, is_int=False)
        self._add_slider(sec3, "换人分局休息间隔 (s)", self.rest_gap_var, 10.0, 60.0, is_int=False)
        self._add_slider(sec3, "每局最少多拍回合数", self.min_rallies_game_var, 3, 20, is_int=True)

    def _add_slider(self, parent: tk.Frame, label_text: str, var, min_v, max_v, is_int: bool = False):
        row = self._reg_frame(tk.Frame(parent), "bg_sidebar", False)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=label_text, style="Muted.TLabel", width=20).pack(side=tk.LEFT)
        val_lbl = self._reg_label(
            tk.Label(row, text=str(var.get()), font=(self.mono_font, 9, "bold"), width=5),
            "bg_sidebar",
            "accent_emerald",
        )
        val_lbl.pack(side=tk.RIGHT)

        def _on_move(v):
            num = int(round(float(v))) if is_int else round(float(v), 1)
            var.set(num)
            val_lbl.config(text=str(num))

        scale = ttk.Scale(row, from_=min_v, to=max_v, orient=tk.HORIZONTAL, command=_on_move)
        scale.set(var.get())
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

    def _build_studio(self, parent: tk.Frame):
        # 1. Top Studio Command Bar
        cmd_bar = self._reg_frame(tk.Frame(parent, padx=16, pady=10, highlightthickness=1), "bg_card", True)
        cmd_bar.pack(fill=tk.X)

        self.btn_one_click = self._make_btn(
            cmd_bar,
            "▶ 一键全自动剪辑并输出视频",
            self.start_one_click_pipeline,
            variant="emerald",
            bg_key="bg_card",
            font_size=10,
            bold=True,
            padx=16,
            pady=6,
        )
        self.btn_one_click.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_scan_only = self._make_btn(
            cmd_bar,
            "扫描/加载时间轴",
            lambda: self.start_scan_only(force_rescan=False),
            variant="primary",
            bg_key="bg_card",
            font_size=9,
            bold=True,
            padx=12,
            pady=6,
        )
        self.btn_scan_only.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_export_tuned = self._make_btn(
            cmd_bar,
            "导出当前时间轴视频",
            self.start_export_current,
            variant="secondary",
            bg_key="bg_card",
            font_size=9,
            bold=True,
            padx=12,
            pady=6,
        )
        self.btn_export_tuned.pack(side=tk.LEFT, padx=(0, 8))

        self._make_btn(
            cmd_bar,
            "重新深度扫描",
            lambda: self.start_scan_only(force_rescan=True),
            variant="secondary",
            bg_key="bg_card",
            font_size=9,
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._make_btn(
            cmd_bar,
            "保存微调 (⌘S)",
            self.save_current_timeline_manual,
            variant="secondary",
            bg_key="bg_card",
            font_size=9,
            padx=10,
            pady=6,
        ).pack(side=tk.LEFT)

        self.btn_stop = self._make_btn(
            cmd_bar,
            "■ 停止",
            self.request_stop,
            variant="danger",
            bg_key="bg_card",
            font_size=9,
            bold=True,
            padx=12,
            pady=6,
        )
        self.btn_stop.pack(side=tk.RIGHT)

        # 2. Interactive Visual Timeline Canvas
        tl_sec = self._reg_frame(tk.Frame(parent, padx=16, pady=8), "bg_panel", False)
        tl_sec.pack(fill=tk.X)

        tl_hdr = self._reg_frame(tk.Frame(tl_sec), "bg_panel", False)
        tl_hdr.pack(fill=tk.X)
        ttk.Label(
            tl_hdr,
            text="TIMELINE · 全场回合时间轴（点击选球 · 拖拽色块边缘直接调整起止秒数 · 蓝虚线=换人分球局）",
            style="PanelHeader.TLabel",
        ).pack(side=tk.LEFT)
        self.lbl_hover_info = self._reg_label(
            tk.Label(tl_hdr, text="", font=(self.mono_font, 9)),
            "bg_panel",
            "accent_emerald",
        )
        self.lbl_hover_info.pack(side=tk.RIGHT)

        self.timeline_canvas = tk.Canvas(
            tl_sec,
            height=96,
            highlightthickness=1,
            cursor="hand2",
        )
        self.timeline_canvas.pack(fill=tk.X, pady=(6, 2))
        self.timeline_canvas.bind("<ButtonPress-1>", self._on_timeline_mouse_down)
        self.timeline_canvas.bind("<B1-Motion>", self._on_timeline_mouse_drag)
        self.timeline_canvas.bind("<ButtonRelease-1>", self._on_timeline_mouse_up)
        self.timeline_canvas.bind("<Motion>", self._on_timeline_mouse_hover)
        self.timeline_canvas.bind("<Configure>", lambda e: self._redraw_timeline_canvas())

        # 3. Dual Frame Preview Cards + Fine-Tuning Controls
        mid_sec = self._reg_frame(tk.Frame(parent, padx=16, pady=4), "bg_panel", False)
        mid_sec.pack(fill=tk.BOTH, expand=True)

        preview_row = self._reg_frame(tk.Frame(mid_sec), "bg_panel", False)
        preview_row.pack(fill=tk.X, pady=(0, 8))

        # Left Card: Start Frame / Inline Video Player
        start_card = self._reg_frame(
            tk.Frame(preview_row, padx=10, pady=8, highlightthickness=1), "bg_card", True
        )
        start_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        self.lbl_start_title = self._reg_label(
            tk.Label(start_card, text="START FRAME · 回合起点画面 (开球前)", font=(self.font_family, 9, "bold")),
            "bg_card",
            "accent_emerald",
        )
        self.lbl_start_title.pack(anchor=tk.W)

        self.canvas_start_preview = tk.Canvas(start_card, width=360, height=185, highlightthickness=0)
        self.canvas_start_preview.pack(pady=6)

        start_tune = self._reg_frame(tk.Frame(start_card), "bg_card", False)
        start_tune.pack(fill=tk.X)
        self._reg_label(tk.Label(start_tune, text="起点微调", font=(self.font_family, 8)), "bg_card", "fg_secondary").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self._make_btn(
            start_tune, "-1.0s", lambda: self.adjust_selected_rally(-1.0, 0.0), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)
        self._make_btn(
            start_tune, "-0.5s", lambda: self.adjust_selected_rally(-0.5, 0.0), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)
        self._make_btn(
            start_tune, "+0.5s", lambda: self.adjust_selected_rally(0.5, 0.0), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)
        self._make_btn(
            start_tune, "+1.0s", lambda: self.adjust_selected_rally(1.0, 0.0), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)

        # Right Card: End Frame
        end_card = self._reg_frame(
            tk.Frame(preview_row, padx=10, pady=8, highlightthickness=1), "bg_card", True
        )
        end_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self.lbl_end_title = self._reg_label(
            tk.Label(end_card, text="END FRAME · 回合终点画面 (球落地瞬间)", font=(self.font_family, 9, "bold")),
            "bg_card",
            "accent_amber",
        )
        self.lbl_end_title.pack(anchor=tk.W)

        self.canvas_end_preview = tk.Canvas(end_card, width=360, height=185, highlightthickness=0)
        self.canvas_end_preview.pack(pady=6)

        end_tune = self._reg_frame(tk.Frame(end_card), "bg_card", False)
        end_tune.pack(fill=tk.X)
        self._reg_label(tk.Label(end_tune, text="终点微调", font=(self.font_family, 8)), "bg_card", "fg_secondary").pack(
            side=tk.LEFT, padx=(0, 4)
        )
        self._make_btn(
            end_tune, "-1.0s 剔除换球", lambda: self.adjust_selected_rally(0.0, -1.0), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)
        self._make_btn(
            end_tune, "-0.5s", lambda: self.adjust_selected_rally(0.0, -0.5), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)
        self._make_btn(
            end_tune, "+0.5s", lambda: self.adjust_selected_rally(0.0, 0.5), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)
        self._make_btn(
            end_tune, "+1.5s 延长救球", lambda: self.adjust_selected_rally(0.0, 1.5), variant="secondary", bg_key="bg_card", font_size=8, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=2)

        # 4. Rally Table & Inspector Toolbar
        tbl_bar = self._reg_frame(tk.Frame(mid_sec), "bg_panel", False)
        tbl_bar.pack(fill=tk.X, pady=(2, 6))
        ttk.Label(tbl_bar, text="RALLIES · 回合列表（双击切换保留/剔除 · Space 键连续播放）", style="PanelHeader.TLabel").pack(
            side=tk.LEFT
        )

        self._make_btn(
            tbl_bar, "系统播放器打开 ↗", self.preview_selected_clip_in_player, variant="secondary", bg_key="bg_panel", font_size=8, padx=8, pady=3
        ).pack(side=tk.RIGHT, padx=2)
        self.btn_inline_play = self._make_btn(
            tbl_bar, "▶ 窗口内连续播放 (Space)", self.toggle_inline_playback, variant="emerald", bg_key="bg_panel", font_size=8, bold=True, padx=10, pady=3
        )
        self.btn_inline_play.pack(side=tk.RIGHT, padx=2)
        self._make_btn(
            tbl_bar, "合并至上一局", self.merge_selected_game, variant="secondary", bg_key="bg_panel", font_size=8, padx=8, pady=3
        ).pack(side=tk.RIGHT, padx=2)
        self._make_btn(
            tbl_bar, "拆分为新一局", self.split_selected_game, variant="secondary", bg_key="bg_panel", font_size=8, padx=8, pady=3
        ).pack(side=tk.RIGHT, padx=2)
        self._make_btn(
            tbl_bar, "保留/剔除 (Del)", self.toggle_selected_rally, variant="secondary", bg_key="bg_panel", font_size=8, padx=8, pady=3
        ).pack(side=tk.RIGHT, padx=2)

        tree_frame = self._reg_frame(tk.Frame(mid_sec, highlightthickness=1), "bg_well", True)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("status", "game", "uid", "start", "end", "dur", "hits", "label")
        self.rally_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=7)
        self.rally_tree.heading("status", text="状态")
        self.rally_tree.heading("game", text="所属球局")
        self.rally_tree.heading("uid", text="序号")
        self.rally_tree.heading("start", text="起点时间")
        self.rally_tree.heading("end", text="终点时间")
        self.rally_tree.heading("dur", text="时长")
        self.rally_tree.heading("hits", text="拍数")
        self.rally_tree.heading("label", text="类型标签")

        self.rally_tree.column("status", width=65, anchor=tk.CENTER)
        self.rally_tree.column("game", width=85, anchor=tk.CENTER)
        self.rally_tree.column("uid", width=55, anchor=tk.CENTER)
        self.rally_tree.column("start", width=95, anchor=tk.CENTER)
        self.rally_tree.column("end", width=95, anchor=tk.CENTER)
        self.rally_tree.column("dur", width=70, anchor=tk.CENTER)
        self.rally_tree.column("hits", width=70, anchor=tk.CENTER)
        self.rally_tree.column("label", width=160, anchor=tk.CENTER)

        self.rally_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.rally_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.rally_tree.bind("<Double-1>", lambda e: self.toggle_selected_rally())

        t_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.rally_tree.yview)
        t_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.rally_tree.config(yscrollcommand=t_scroll.set)

        # 5. Bottom Codex Console & Progress Bar
        bot_frame = self._reg_frame(tk.Frame(parent, padx=16, pady=10, highlightthickness=1), "bg_card", True)
        bot_frame.pack(fill=tk.X, side=tk.BOTTOM)

        prog_row = self._reg_frame(tk.Frame(bot_frame), "bg_card", False)
        prog_row.pack(fill=tk.X)
        self._reg_label(
            tk.Label(prog_row, textvariable=self.status_var, font=(self.mono_font, 9, "bold")),
            "bg_card",
            "accent_emerald",
        ).pack(side=tk.LEFT)

        self.progress_bar = ttk.Progressbar(
            bot_frame, variable=self.progress_var, maximum=100.0, style="Codex.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill=tk.X, pady=(6, 6))

        self.log_text = tk.Text(
            bot_frame,
            height=4,
            font=(self.mono_font, 9),
            relief=tk.FLAT,
            state=tk.DISABLED,
            padx=8,
            pady=4,
        )
        self.log_text.pack(fill=tk.X)

    # -------------------------------------------------------------------------
    # Presets, Configuration & Queue Helpers
    # -------------------------------------------------------------------------
    def apply_preset(self, preset_name: str):
        self.mode_all_var.set(True)
        self.mode_condensed_var.set(preset_name in ("condensed", "grand_slam"))
        self.mode_vertical_var.set(preset_name in ("vertical", "grand_slam"))
        self.mode_solo_var.set(preset_name == "grand_slam")
        self.mode_showcase_var.set(preset_name == "grand_slam")
        self.split_by_game_var.set(True)
        self.append_log(f"✨ 已切换场景预设: [{preset_name}]")

    def build_cutter_config(self) -> CutterConfig:
        modes = []
        if self.mode_all_var.get():
            modes.append("all")
        if self.mode_condensed_var.get():
            modes.append("condensed")
        if self.mode_vertical_var.get():
            modes.append("vertical")
        if self.mode_solo_var.get():
            modes.append("solo")
        if self.mode_showcase_var.get():
            modes.append("showcase")
        if not modes:
            modes = ["all"]

        player_key = PLAYER_LABELS.get(self.solo_player_var.get(), "near_left")
        self._save_preferences()
        return CutterConfig(
            ffmpeg_bin=DEFAULT_FFMPEG,
            modes=modes,
            player=player_key,
            aspect_ratio=self.aspect_ratio_var.get(),
            split_by_game=self.split_by_game_var.get(),
            reel=self.reel_var.get(),
            hud=self.hud_var.get(),
            slowmo=self.slowmo_var.get(),
            gif=self.gif_var.get(),
            strict_visual=True,
            min_hits=int(self.min_hits_var.get()),
            min_duration=float(self.min_dur_var.get()),
            lineup_threshold=float(self.lineup_th_var.get()),
            rest_gap=float(self.rest_gap_var.get()),
            min_rallies_per_game=int(self.min_rallies_game_var.get()),
        )

    def reset_default_params(self):
        self.mode_all_var.set(True)
        self.mode_condensed_var.set(False)
        self.mode_vertical_var.set(False)
        self.mode_solo_var.set(False)
        self.mode_showcase_var.set(False)
        self.split_by_game_var.set(True)
        self.reel_var.set(False)
        self.hud_var.set(False)
        self.slowmo_var.set(False)
        self.gif_var.set(False)
        self.min_hits_var.set(5)
        self.min_dur_var.set(5.0)
        self.rest_gap_var.set(22.0)
        self.min_rallies_game_var.set(8)
        self.append_log("⚙️ 已恢复默认剪辑参数（经典全能合集 + 5拍/5秒起步 + 22秒换人分局）。")

    def _register_video_path(self, full_p: str) -> bool:
        if not full_p or full_p in self.video_files:
            return False
        self.video_files.append(full_p)
        cached_tl = try_load_cached_timeline(full_p)
        if cached_tl and cached_tl.segments:
            self.timelines[full_p] = cached_tl
        return True

    def add_video_files(self):
        paths = filedialog.askopenfilenames(
            title="选择羽毛球比赛视频",
            filetypes=[("视频文件", "*.mp4 *.mov *.mkv *.ts *.MP4 *.MOV"), ("所有文件", "*.*")],
        )
        added = 0
        for p in paths:
            if self._register_video_path(p):
                added += 1
        if added:
            self._refresh_video_listbox()
            self._refresh_timeline_view()
            self.append_log(f"➕ 已添加 {added} 个视频文件。")

    def add_video_folder(self):
        folder = filedialog.askdirectory(title="选择包含羽毛球视频的文件夹")
        if folder:
            self._import_folder_path(folder, silent=False)

    def _import_folder_path(self, folder: str, silent: bool = False):
        added = 0
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith((".mp4", ".mov", ".mkv", ".ts")):
                full_p = os.path.join(folder, f)
                if self._register_video_path(full_p):
                    added += 1
        if added:
            base_name = os.path.basename(os.path.normpath(folder))
            parent_dir = os.path.dirname(os.path.normpath(folder))
            self.output_dir_var.set(os.path.join(parent_dir, f"{base_name}羽毛球精彩多拍集锦"))
            self._refresh_video_listbox()
            self._refresh_timeline_view()
            cached_cnt = sum(1 for v in self.video_files if v in self.timelines)
            self.append_log(
                f"📁 已导入文件夹 [{base_name}] 共 {added} 个视频（{cached_cnt} 个已秒级加载时间轴缓存）。"
            )
        elif not silent:
            messagebox.showinfo("提示", "所选文件夹中未找到 .mp4 / .mov / .mkv / .ts 视频文件。")

    def remove_selected_video(self):
        sel = self.video_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        vpath = self.video_files.pop(idx)
        self.timelines.pop(vpath, None)
        if self.current_vpath == vpath:
            self.current_vpath = self.video_files[0] if self.video_files else None
        self._refresh_video_listbox()
        self._refresh_timeline_view()

    def clear_video_queue(self):
        self._stop_inline_playback()
        self.video_files.clear()
        self.timelines.clear()
        self.current_vpath = None
        self.selected_uid = None
        self._refresh_video_listbox()
        self._refresh_timeline_view()

    def choose_output_dir(self):
        d = filedialog.askdirectory(title="选择剪辑视频输出目录")
        if d:
            self.output_dir_var.set(d)
            self._save_preferences()

    def open_output_dir(self):
        out_dir = self.output_dir_var.get()
        os.makedirs(out_dir, exist_ok=True)
        if platform.system() == "Windows":
            os.startfile(out_dir)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", out_dir])
        else:
            subprocess.Popen(["xdg-open", out_dir])

    def _refresh_video_listbox(self):
        self.video_listbox.delete(0, tk.END)
        for i, vpath in enumerate(self.video_files, 1):
            bname = os.path.basename(vpath)
            if vpath in self.timelines:
                tl = self.timelines[vpath]
                tag = f"✓ {len(tl.enabled_rallies)}拍 / {tl.game_count}局"
            else:
                tag = "… 待扫描"
            self.video_listbox.insert(tk.END, f"{i:02d}. {bname}   [{tag}]")
        if self.video_files and not self.current_vpath:
            self.current_vpath = self.video_files[0]
            self.video_listbox.selection_set(0)

    def _on_video_select(self, _event=None):
        sel = self.video_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.video_files):
            new_v = self.video_files[idx]
            if new_v != self.current_vpath:
                self._stop_inline_playback()
                self.current_vpath = new_v
                self.selected_uid = None
                self._refresh_timeline_view()

    # -------------------------------------------------------------------------
    # Timeline Visualization, Mouse Dragging & Rally Fine-Tuning
    # -------------------------------------------------------------------------
    def _refresh_timeline_view(self):
        for item in self.rally_tree.get_children():
            self.rally_tree.delete(item)

        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl:
            self._redraw_timeline_canvas()
            return

        for seg in tl.segments:
            status_str = "✓ 保留" if seg.enabled else "× 剔除"
            game_str = f"第{seg.game_index:02d}局" if seg.kind == "rally" else "秒杀特辑"
            self.rally_tree.insert(
                "",
                tk.END,
                iid=str(seg.uid),
                values=(
                    status_str,
                    game_str,
                    f"#{seg.uid:02d}",
                    format_time_zh(seg.s_cut),
                    format_time_zh(seg.e_cut),
                    f"{seg.dur:.1f}s",
                    f"{seg.hit_count}拍",
                    seg.label,
                ),
            )

        self._redraw_timeline_canvas()
        if tl.segments and self.selected_uid is None:
            self.selected_uid = tl.segments[0].uid
            self.rally_tree.selection_set(str(self.selected_uid))
            self._update_preview_thumbnails()

    def _redraw_timeline_canvas(self):
        c = self.timeline_canvas
        c.delete("all")
        p = self.palette
        w = max(300, c.winfo_width())
        h = max(70, c.winfo_height())

        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or tl.duration <= 0:
            c.create_text(
                w // 2,
                h // 2,
                text="等待加载时间轴 · 点击上方「▶ 一键全自动剪辑并输出视频」或「扫描/加载时间轴」",
                fill=p["fg_muted"],
                font=(self.font_family, 10),
            )
            return

        dur = tl.duration
        pad_x = 16
        usable_w = max(100, w - 2 * pad_x)
        base_y = h - 22

        # Baseline ruler
        c.create_line(pad_x, base_y, w - pad_x, base_y, fill=p["border"], width=1)
        for tick_i in range(7):
            t_val = dur * tick_i / 6.0
            tx = pad_x + usable_w * (tick_i / 6.0)
            c.create_line(tx, base_y, tx, base_y + 4, fill=p["fg_muted"])
            c.create_text(tx, base_y + 12, text=format_time_zh(t_val), fill=p["fg_muted"], font=(self.mono_font, 8))

        # Draw game boundary markers
        last_game = None
        for seg in tl.segments:
            if seg.kind == "rally" and seg.enabled:
                if last_game is not None and seg.game_index != last_game:
                    gx = pad_x + (seg.s_cut / dur) * usable_w
                    c.create_line(gx, 6, gx, base_y, fill=p["accent_blue"], width=2, dash=(4, 2))
                    c.create_text(
                        gx + 26,
                        12,
                        text=f"第{seg.game_index:02d}局",
                        fill=p["accent_blue"],
                        font=(self.font_family, 8, "bold"),
                    )
                elif last_game is None:
                    gx = pad_x + (seg.s_cut / dur) * usable_w
                    c.create_text(
                        max(pad_x + 24, gx + 22),
                        12,
                        text=f"第{seg.game_index:02d}局",
                        fill=p["accent_blue"],
                        font=(self.font_family, 8, "bold"),
                    )
                last_game = seg.game_index

        # Draw rally blocks
        for seg in tl.segments:
            x1 = pad_x + (seg.s_cut / dur) * usable_w
            x2 = max(x1 + 4, pad_x + (seg.e_cut / dur) * usable_w)
            height_ratio = min(1.0, max(0.32, seg.dur / 22.0))
            bar_h = int((base_y - 22) * height_ratio)
            y1 = base_y - bar_h

            if not seg.enabled:
                fill_col = p["block_disabled"]
            elif seg.kind == "serve_kill":
                fill_col = "#F97316"
            elif seg.dur >= 15.0:
                fill_col = p["accent_amber"]
            else:
                fill_col = p["accent_emerald"]

            is_sel = seg.uid == self.selected_uid
            outline_col = p["fg_primary"] if is_sel else ""
            width_px = 2 if is_sel else 0
            c.create_rectangle(x1, y1, x2, base_y - 1, fill=fill_col, outline=outline_col, width=width_px)

        # Draw active inline playhead if playing
        if self._playhead_time is not None:
            px = pad_x + (self._playhead_time / dur) * usable_w
            c.create_line(px, 4, px, base_y + 4, fill=p["accent_red"], width=2)

    def _x_to_time(self, x_px: int) -> float:
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or tl.duration <= 0:
            return 0.0
        w = max(300, self.timeline_canvas.winfo_width())
        pad_x = 16
        usable_w = max(100, w - 2 * pad_x)
        return max(0.0, min(tl.duration, ((x_px - pad_x) / usable_w) * tl.duration))

    def _find_segment_at_x(self, x_px: int) -> Tuple[Optional[RallySegment], Optional[str]]:
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or tl.duration <= 0 or not tl.segments:
            return None, None
        w = max(300, self.timeline_canvas.winfo_width())
        pad_x = 16
        usable_w = max(100, w - 2 * pad_x)

        for seg in tl.segments:
            x1 = pad_x + (seg.s_cut / tl.duration) * usable_w
            x2 = max(x1 + 4, pad_x + (seg.e_cut / tl.duration) * usable_w)
            if x1 - 4 <= x_px <= x2 + 4:
                if abs(x_px - x1) <= 5:
                    return seg, "start"
                elif abs(x_px - x2) <= 5:
                    return seg, "end"
                return seg, "body"

        click_t = self._x_to_time(x_px)
        best_seg = min(tl.segments, key=lambda s: abs(0.5 * (s.s_cut + s.e_cut) - click_t))
        return best_seg, "body"

    def _on_timeline_mouse_hover(self, event):
        seg, edge = self._find_segment_at_x(event.x)
        if not seg:
            self.lbl_hover_info.config(text="")
            self.timeline_canvas.config(cursor="hand2")
            return
        if edge in ("start", "end"):
            self.timeline_canvas.config(cursor="sb_h_double_arrow")
        else:
            self.timeline_canvas.config(cursor="hand2")
        g_txt = f"第{seg.game_index:02d}局" if seg.kind == "rally" else "秒杀"
        self.lbl_hover_info.config(
            text=f"#{seg.uid:02d} [{g_txt}] {format_time_zh(seg.s_cut)} → {format_time_zh(seg.e_cut)} ({seg.dur:.1f}s · {seg.hit_count}拍)"
        )

    def _on_timeline_mouse_down(self, event):
        self._stop_inline_playback()
        seg, edge = self._find_segment_at_x(event.x)
        if not seg:
            return
        self.selected_uid = seg.uid
        self.rally_tree.selection_set(str(seg.uid))
        self.rally_tree.see(str(seg.uid))
        self._drag_uid = seg.uid
        self._drag_mode = edge if edge in ("start", "end") else None
        self._redraw_timeline_canvas()
        self._update_preview_thumbnails()

    def _on_timeline_mouse_drag(self, event):
        if not self._drag_mode or self._drag_uid is None:
            return
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl:
            return
        seg = tl.get_segment(self._drag_uid)
        if not seg:
            return
        t_new = self._x_to_time(event.x)
        if self._drag_mode == "start":
            tl.set_segment_time(seg.uid, t_new, seg.e_cut)
        elif self._drag_mode == "end":
            tl.set_segment_time(seg.uid, seg.s_cut, t_new)
        self._redraw_timeline_canvas()

    def _on_timeline_mouse_up(self, _event):
        if self._drag_mode and self._drag_uid is not None:
            tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
            if tl:
                seg = tl.get_segment(self._drag_uid)
                if seg:
                    save_timeline_json(tl)
                    self._refresh_timeline_view()
                    self.rally_tree.selection_set(str(seg.uid))
                    self._update_preview_thumbnails()
                    self.append_log(
                        f"🖱️ 拖拽微调回合 #{seg.uid:02d}: 新区间 {format_time_zh(seg.s_cut)} ~ {format_time_zh(seg.e_cut)} ({seg.dur:.1f}s)"
                    )
        self._drag_mode = None
        self._drag_uid = None

    def _on_tree_select(self, _event=None):
        sel = self.rally_tree.selection()
        if not sel:
            return
        uid = int(sel[0])
        if uid != self.selected_uid:
            self._stop_inline_playback()
            self.selected_uid = uid
            self._redraw_timeline_canvas()
            self._update_preview_thumbnails()

    def _update_preview_thumbnails(self):
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or self.selected_uid is None:
            return
        seg = tl.get_segment(self.selected_uid)
        if not seg:
            return

        self.lbl_start_title.config(
            text=f"START FRAME · 回合 #{seg.uid:02d} 起点 ({format_time_zh(seg.s_cut)})"
        )
        self.lbl_end_title.config(
            text=f"END FRAME · 回合 #{seg.uid:02d} 终点 ({format_time_zh(seg.e_cut)} · {seg.dur:.1f}s)"
        )

        vpath = tl.video_path
        s_t = seg.s_cut
        e_t = max(seg.s_cut, seg.e_cut - 0.15)

        def _fetch_frames():
            f_start = extract_preview_frame_rgb(vpath, s_t, width=360, height=185)
            f_end = extract_preview_frame_rgb(vpath, e_t, width=360, height=185)
            self.ui_queue.put(("preview_frames", (seg.uid, f_start, f_end)))

        threading.Thread(target=_fetch_frames, daemon=True).start()

    def _render_preview_frames(self, uid: int, f_start: Optional[np.ndarray], f_end: Optional[np.ndarray]):
        if uid != self.selected_uid or self._inline_playing:
            return
        if HAS_PIL:
            if f_start is not None:
                img1 = Image.fromarray(f_start)
                self._start_photo = ImageTk.PhotoImage(img1)
                self.canvas_start_preview.delete("all")
                self.canvas_start_preview.create_image(0, 0, anchor=tk.NW, image=self._start_photo)
            if f_end is not None:
                img2 = Image.fromarray(f_end)
                self._end_photo = ImageTk.PhotoImage(img2)
                self.canvas_end_preview.delete("all")
                self.canvas_end_preview.create_image(0, 0, anchor=tk.NW, image=self._end_photo)

    # -------------------------------------------------------------------------
    # Inline Rally Video Playback
    # -------------------------------------------------------------------------
    def toggle_inline_playback(self):
        if self._inline_playing:
            self._stop_inline_playback()
            return

        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or self.selected_uid is None:
            return
        seg = tl.get_segment(self.selected_uid)
        if not seg or not os.path.exists(tl.video_path):
            return

        self._inline_playing = True
        self.btn_inline_play.set_text("⏸ 停止播放 (Space)")
        self.btn_inline_play.set_variant("amber")
        self.lbl_start_title.config(text=f"▶ 正在加载回合 #{seg.uid:02d} 连续画面...")

        vpath = tl.video_path
        s_cut = seg.s_cut
        dur = seg.dur
        uid = seg.uid

        def _load_and_play():
            frames = extract_clip_preview_frames(vpath, s_cut, dur, fps_out=8, width=360, height=185)
            self.ui_queue.put(("inline_frames_ready", (uid, frames)))

        threading.Thread(target=_load_and_play, daemon=True).start()

    def _start_inline_frame_loop(self, uid: int, frames: List[Tuple[float, np.ndarray]]):
        if not self._inline_playing or uid != self.selected_uid or not frames:
            self._stop_inline_playback()
            return
        self._inline_frames = frames
        self._inline_frame_idx = 0
        self._step_inline_frame()

    def _step_inline_frame(self):
        if not self._inline_playing or not self._inline_frames:
            return
        if self._inline_frame_idx >= len(self._inline_frames):
            self._stop_inline_playback()
            return

        t_cur, arr = self._inline_frames[self._inline_frame_idx]
        self._playhead_time = t_cur
        if HAS_PIL:
            img = Image.fromarray(arr)
            self._start_photo = ImageTk.PhotoImage(img)
            self.canvas_start_preview.delete("all")
            self.canvas_start_preview.create_image(0, 0, anchor=tk.NW, image=self._start_photo)
        self.lbl_start_title.config(
            text=f"PLAYING · 回合 #{self.selected_uid:02d}  [{format_time_zh(t_cur)}]"
        )
        self._redraw_timeline_canvas()
        self._inline_frame_idx += 1
        self.root.after(125, self._step_inline_frame)

    def _stop_inline_playback(self):
        if self._inline_playing:
            self._inline_playing = False
            self._inline_frames = []
            self._playhead_time = None
            self.btn_inline_play.set_text("▶ 窗口内连续播放 (Space)")
            self.btn_inline_play.set_variant("emerald")
            self._redraw_timeline_canvas()
            self._update_preview_thumbnails()

    # -------------------------------------------------------------------------
    # Fine-Tuning Actions
    # -------------------------------------------------------------------------
    def adjust_selected_rally(self, delta_s: float, delta_e: float):
        self._stop_inline_playback()
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or self.selected_uid is None:
            return
        seg = tl.adjust_segment_time(self.selected_uid, delta_start=delta_s, delta_end=delta_e)
        if seg:
            save_timeline_json(tl)
            self._refresh_timeline_view()
            self.rally_tree.selection_set(str(seg.uid))
            self._update_preview_thumbnails()
            self.append_log(
                f"✂️ 已微调回合 #{seg.uid:02d}: 新区间 {format_time_zh(seg.s_cut)} ~ {format_time_zh(seg.e_cut)} ({seg.dur:.1f}s)"
            )

    def toggle_selected_rally(self):
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or self.selected_uid is None:
            return
        seg = tl.toggle_segment_enabled(self.selected_uid)
        if seg:
            save_timeline_json(tl)
            self._refresh_timeline_view()
            self._refresh_video_listbox()
            self.rally_tree.selection_set(str(seg.uid))
            state_txt = "保留" if seg.enabled else "剔除"
            self.append_log(f"🔄 回合 #{seg.uid:02d} 状态已切换为: [{state_txt}]")

    def split_selected_game(self):
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or self.selected_uid is None:
            return
        if tl.split_game_at_segment(self.selected_uid):
            save_timeline_json(tl)
            self._refresh_timeline_view()
            self._refresh_video_listbox()
            self.rally_tree.selection_set(str(self.selected_uid))
            self.append_log(f"🏆 已从回合 #{self.selected_uid:02d} 处拆分为新的一局（当前共 {tl.game_count} 局）。")

    def merge_selected_game(self):
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or self.selected_uid is None:
            return
        if tl.merge_game_with_previous(self.selected_uid):
            save_timeline_json(tl)
            self._refresh_timeline_view()
            self._refresh_video_listbox()
            self.rally_tree.selection_set(str(self.selected_uid))
            self.append_log(f"🔗 已将该局合并至上一局（当前共 {tl.game_count} 局）。")

    def save_current_timeline_manual(self):
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl:
            return
        p = save_timeline_json(tl)
        self.append_log(f"💾 已保存当前时间轴与球局微调进度: {os.path.basename(p)}")

    def preview_selected_clip_in_player(self):
        tl = self.timelines.get(self.current_vpath) if self.current_vpath else None
        if not tl or self.selected_uid is None:
            return
        seg = tl.get_segment(self.selected_uid)
        if not seg:
            return
        preview_path = os.path.join(tempfile.gettempdir(), f"badminton_preview_uid_{seg.uid}.mp4")
        cut_lossless(DEFAULT_FFMPEG, tl.video_path, seg.s_cut, seg.dur, preview_path)
        if os.path.exists(preview_path):
            if platform.system() == "Windows":
                os.startfile(preview_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", preview_path])
            else:
                subprocess.Popen(["xdg-open", preview_path])

    # -------------------------------------------------------------------------
    # Background Execution Pipelines
    # -------------------------------------------------------------------------
    def start_one_click_pipeline(self):
        if self.is_running:
            messagebox.showwarning("正在运行", "当前已有剪辑任务正在进行中。")
            return
        if not self.video_files:
            messagebox.showwarning("请添加视频", "请先点击「＋ 添加视频」或「📁 导入文件夹」添加羽毛球录像！")
            return

        self._stop_inline_playback()
        config = self.build_cutter_config()
        out_root = self.output_dir_var.get()
        self._set_running_state(True)

        def _worker():
            try:
                total_v = len(self.video_files)
                batch_timelines = []
                for idx, vpath in enumerate(self.video_files, 1):
                    if self.cancel_requested:
                        self.ui_queue.put(("log", "⏹ 用户已手动停止任务。"))
                        break

                    def _prog_scan(pct, msg, i=idx):
                        overall = ((i - 1) + (pct / 100.0)) / total_v * 55.0
                        self.ui_queue.put(("progress", (overall, f"[扫描 {i}/{total_v}] {msg}")))

                    tl = analyze_video_file(
                        vpath,
                        idx=idx,
                        config=config,
                        progress_cb=_prog_scan,
                        log_cb=lambda m: self.ui_queue.put(("log", m)),
                        cancel_check=lambda: self.cancel_requested,
                        use_cache=True,
                    )
                    self.timelines[vpath] = tl
                    batch_timelines.append(tl)
                    self.ui_queue.put(("timeline_ready", vpath))

                if not self.cancel_requested and batch_timelines:
                    export_batch_timelines(
                        batch_timelines,
                        output_root=out_root,
                        config=config,
                        progress_cb=lambda pct, msg: self.ui_queue.put(("progress", (55.0 + pct * 0.45, msg))),
                        log_cb=lambda m: self.ui_queue.put(("log", m)),
                        cancel_check=lambda: self.cancel_requested,
                    )
                    self.ui_queue.put(("done_popup", out_root))
            except Exception as e:
                self.ui_queue.put(("log", f"❌ 处理异常: {e}"))
            finally:
                self.ui_queue.put(("running", False))

        threading.Thread(target=_worker, daemon=True).start()

    def start_scan_only(self, force_rescan: bool = False):
        if self.is_running:
            return
        if not self.video_files:
            messagebox.showwarning("请添加视频", "请先添加要扫描的羽毛球视频文件！")
            return

        self._stop_inline_playback()
        config = self.build_cutter_config()
        self._set_running_state(True)

        def _worker():
            try:
                total_v = len(self.video_files)
                for idx, vpath in enumerate(self.video_files, 1):
                    if self.cancel_requested:
                        break
                    tl = analyze_video_file(
                        vpath,
                        idx=idx,
                        config=config,
                        progress_cb=lambda pct, msg, i=idx: self.ui_queue.put(
                            ("progress", (((i - 1) + pct / 100.0) / total_v * 100.0, f"[{i}/{total_v}] {msg}"))
                        ),
                        log_cb=lambda m: self.ui_queue.put(("log", m)),
                        cancel_check=lambda: self.cancel_requested,
                        use_cache=(not force_rescan),
                    )
                    self.timelines[vpath] = tl
                    self.ui_queue.put(("timeline_ready", vpath))
            finally:
                self.ui_queue.put(("running", False))

        threading.Thread(target=_worker, daemon=True).start()

    def start_export_current(self):
        if self.is_running:
            return
        if not self.timelines:
            messagebox.showinfo("请先扫描", "请先点击「扫描/加载时间轴」或直接点击「▶ 一键全自动剪辑并输出视频」。")
            return

        self._stop_inline_playback()
        config = self.build_cutter_config()
        out_root = self.output_dir_var.get()
        self._set_running_state(True)

        def _worker():
            try:
                items = [self.timelines[v] for v in self.video_files if v in self.timelines]
                export_batch_timelines(
                    items,
                    output_root=out_root,
                    config=config,
                    progress_cb=lambda pct, msg: self.ui_queue.put(("progress", (pct, msg))),
                    log_cb=lambda m: self.ui_queue.put(("log", m)),
                    cancel_check=lambda: self.cancel_requested,
                )
                if not self.cancel_requested:
                    self.ui_queue.put(("done_popup", out_root))
            finally:
                self.ui_queue.put(("running", False))

        threading.Thread(target=_worker, daemon=True).start()

    def request_stop(self):
        if self.is_running:
            self.cancel_requested = True
            self.append_log("⏳ 正在安全停止当前任务...")

    def _set_running_state(self, running: bool):
        self.is_running = running
        if running:
            self.cancel_requested = False

    def append_log(self, msg: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _poll_ui_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "log":
                    self.append_log(str(payload))
                elif kind == "progress":
                    pct, status_txt = payload
                    self.progress_var.set(pct)
                    self.status_var.set(status_txt)
                elif kind == "timeline_ready":
                    vpath = payload
                    self.current_vpath = vpath
                    self._refresh_video_listbox()
                    self._refresh_timeline_view()
                elif kind == "preview_frames":
                    uid, f_s, f_e = payload
                    self._render_preview_frames(uid, f_s, f_e)
                elif kind == "inline_frames_ready":
                    uid, frames = payload
                    self._start_inline_frame_loop(uid, frames)
                elif kind == "running":
                    self._set_running_state(bool(payload))
                elif kind == "done_popup":
                    out_dir = payload
                    self.append_log(f"✅ 全部导出完成！输出目录：{out_dir}")
        except queue.Empty:
            pass
        self.root.after(80, self._poll_ui_queue)


def main():
    parser = argparse.ArgumentParser(description="羽毛球 AI 视频剪辑大师 · Codex UI 可视化桌面版")
    parser.add_argument("--self-test", action="store_true", help="Run automated GUI initialization & Dark/Light theme self-test")
    parser.add_argument("--theme", choices=["dark", "light"], default=None, help="Initial theme mode (dark or light)")
    args, unknown = parser.parse_known_args()

    if not args.self_test:
        from codex_server import main as codex_main
        sys.argv = [sys.argv[0]] + unknown
        codex_main()
        return

    root = tk.Tk()
    app = BadmintonCutterGUI(root)
    if args.theme:
        app.apply_theme(args.theme)

    if args.self_test:
        fake_vpath = "/tmp/fake_match.mp4"
        app.video_files.append(fake_vpath)
        app.timelines[fake_vpath] = VideoTimeline(
            video_path=fake_vpath,
            display_name="场次一_双打实战_050",
            folder_name="01_场次一_双打实战_050",
            duration=300.0,
            segments=[
                RallySegment(uid=1, kind="rally", game_index=1, s_cut=10.0, e_cut=24.0, peaks=[(11.0, 3e7)] * 8),
                RallySegment(uid=2, kind="rally", game_index=2, s_cut=120.0, e_cut=138.0, peaks=[(121.0, 5e7)] * 14),
            ],
        )
        app.current_vpath = fake_vpath
        app._refresh_video_listbox()
        app._refresh_timeline_view()

        # Test Dark -> Light -> Dark theme switching
        app.apply_theme("light")
        assert app.theme_mode == "light"
        assert app.palette["bg_panel"] == "#FFFFFF"
        app.toggle_theme()
        assert app.theme_mode == "dark"
        assert app.palette["bg_app"] == "#0D0D0D"

        print("CODEX_GUI_DARK_LIGHT_SELF_TEST_OK")
        os._exit(0)

    root.mainloop()


if __name__ == "__main__":
    main()
