#!/usr/bin/env python3
"""
Unit tests for `gui_engine.py` (Timeline editing, game split/merge, JSON persistence,
hardware encoder detection, and multi-mode single/batch export).
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from badminton_gui import THEMES
from gui_engine import (
    CutterConfig,
    RallySegment,
    VideoTimeline,
    detect_hw_video_encoder,
    export_batch_timelines,
    export_video_timeline,
    load_timeline_json,
    resolve_match_folder_name,
    save_timeline_json,
)


class TestGuiEngine(unittest.TestCase):
    def setUp(self):
        self.timeline = VideoTimeline(
            video_path="/fake/VID_20261029_203442_050.mp4",
            display_name="场次一_双打实战_050",
            folder_name="01_场次一_双打实战_050",
            duration=600.0,
            stable_start=5.0,
            unstable_end=595.0,
            segments=[
                RallySegment(
                    uid=1,
                    kind="rally",
                    game_index=1,
                    s_cut=10.0,
                    e_cut=22.0,
                    peaks=[(10.5 + i * 0.8, 3.0e7) for i in range(10)],
                ),
                RallySegment(
                    uid=2,
                    kind="rally",
                    game_index=1,
                    s_cut=35.0,
                    e_cut=52.0,
                    peaks=[(35.5 + i * 0.9, 6.0e7) for i in range(16)],
                ),
                RallySegment(
                    uid=3,
                    kind="rally",
                    game_index=2,
                    s_cut=120.0,
                    e_cut=130.0,
                    peaks=[(120.5 + i * 0.5, 2.5e7) for i in range(12)],
                ),
                RallySegment(
                    uid=4,
                    kind="serve_kill",
                    game_index=1,
                    s_cut=200.0,
                    e_cut=205.0,
                    peaks=[(201.0, 2.0e7), (201.8, 5.5e7)],
                    surge=2.8,
                ),
            ],
        )

    def test_adjust_and_set_segment_time(self):
        seg = self.timeline.adjust_segment_time(1, delta_start=-2.0, delta_end=3.5)
        self.assertAlmostEqual(seg.s_cut, 8.0)
        self.assertAlmostEqual(seg.e_cut, 25.5)
        self.assertAlmostEqual(seg.dur, 17.5)
        self.assertEqual(seg.label, "【超长高能拉锯】")

        # Clamp start at 0.0 and end at duration
        seg = self.timeline.adjust_segment_time(1, delta_start=-50.0, delta_end=900.0)
        self.assertAlmostEqual(seg.s_cut, 0.0)
        self.assertAlmostEqual(seg.e_cut, 600.0)

        # Direct set_segment_time
        seg = self.timeline.set_segment_time(1, 12.0, 19.0)
        self.assertAlmostEqual(seg.s_cut, 12.0)
        self.assertAlmostEqual(seg.e_cut, 19.0)
        self.assertEqual(seg.label, "【多拍激烈对攻】")

    def test_toggle_segment_enabled(self):
        self.assertEqual(len(self.timeline.enabled_rallies), 3)
        self.timeline.toggle_segment_enabled(2)
        self.assertEqual(len(self.timeline.enabled_rallies), 2)
        self.timeline.toggle_segment_enabled(2, enabled=True)
        self.assertEqual(len(self.timeline.enabled_rallies), 3)

    def test_split_and_merge_games(self):
        self.assertEqual(self.timeline.game_count, 2)
        ok = self.timeline.split_game_at_segment(2)
        self.assertTrue(ok)
        self.assertEqual(self.timeline.get_segment(1).game_index, 1)
        self.assertEqual(self.timeline.get_segment(2).game_index, 2)
        self.assertEqual(self.timeline.get_segment(3).game_index, 3)
        self.assertEqual(self.timeline.game_count, 3)

        ok_merge = self.timeline.merge_game_with_previous(2)
        self.assertTrue(ok_merge)
        self.assertEqual(self.timeline.get_segment(1).game_index, 1)
        self.assertEqual(self.timeline.get_segment(2).game_index, 1)
        self.assertEqual(self.timeline.get_segment(3).game_index, 2)
        self.assertEqual(self.timeline.game_count, 2)

    def test_timeline_json_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "test.timeline.json")
            save_timeline_json(self.timeline, json_path)
            self.assertTrue(os.path.exists(json_path))
            loaded = load_timeline_json(json_path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.display_name, self.timeline.display_name)
            self.assertEqual(len(loaded.segments), 4)
            self.assertEqual(loaded.game_count, 2)
            self.assertAlmostEqual(loaded.get_segment(2).s_cut, 35.0)
            self.assertEqual(loaded.get_segment(4).kind, "serve_kill")

    def test_detect_hw_video_encoder(self):
        enc = detect_hw_video_encoder("/nonexistent/ffmpeg_binary")
        self.assertEqual(enc, "libx264")

    def test_export_video_timeline_multi_modes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            def fake_cut(ffmpeg_bin, vpath, s, d, out):
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(b"fake_mp4_bytes")

            def fake_condensed(ffmpeg_bin, clips, out):
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(b"fake_reel_bytes")
                return out

            def fake_vertical(ffmpeg_bin, clip_in, clip_out, aspect_ratio="9:16"):
                os.makedirs(os.path.dirname(clip_out), exist_ok=True)
                with open(clip_out, "wb") as f:
                    f.write(b"fake_vert_bytes")
                return clip_out

            def fake_review(ffmpeg_bin, vpath, rallies, match_dir):
                rev_dir = os.path.join(match_dir, "技战术与发接发复盘")
                os.makedirs(rev_dir, exist_ok=True)
                rep = os.path.join(rev_dir, "tactical_review_report.txt")
                with open(rep, "w") as f:
                    f.write("report")
                return [], rep

            config = CutterConfig(
                modes=["all", "condensed", "vertical", "solo", "review", "showcase"],
                player="near_left",
                split_by_game=True,
                reel=True,
            )

            with patch("gui_engine.cut_lossless", side_effect=fake_cut), \
                 patch("gui_engine.concat_clips", side_effect=fake_condensed), \
                 patch("gui_engine.generate_condensed_reel", side_effect=fake_condensed), \
                 patch("gui_engine.generate_vertical_clip", side_effect=fake_vertical), \
                 patch("gui_engine.generate_review_package", side_effect=fake_review):
                res = export_batch_timelines([self.timeline], tmpdir, config=config)

            self.assertEqual(len(res["matches"]), 1)
            match_dir = res["matches"][0]["match_dir"]
            self.assertTrue(os.path.exists(os.path.join(match_dir, "game_summary.txt")))
            self.assertTrue(os.path.exists(os.path.join(match_dir, "match_timeline.json")))
            self.assertTrue(os.path.exists(os.path.join(match_dir, "竖屏9比16自媒体短视频")))
            self.assertTrue(os.path.exists(os.path.join(match_dir, "个人高光Solo视角_near_left")))
            self.assertTrue(os.path.exists(os.path.join(match_dir, "战术风格分类集锦")))
            self.assertTrue(os.path.exists(os.path.join(match_dir, "接发秒杀一拍定死")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "00_特别精选_发球被一拍定死大赏")))

    def test_resolve_match_folder_name(self):
        folder, disp = resolve_match_folder_name("/path/VID_20261029_203442_050.mp4", 1)
        self.assertEqual(folder, "01_场次一_双打实战_050")
        self.assertEqual(disp, "场次一_双打实战_050")

    def test_codex_dark_and_light_themes(self):
        self.assertIn("dark", THEMES)
        self.assertIn("light", THEMES)
        for mode in ("dark", "light"):
            palette = THEMES[mode]
            self.assertEqual(palette["accent_blue"], "#0A84FF")
            for key in (
                "bg_app",
                "bg_header",
                "bg_sidebar",
                "bg_panel",
                "bg_card",
                "bg_well",
                "border",
                "fg_primary",
                "fg_secondary",
                "btn_primary_bg",
                "btn_primary_fg",
            ):
                self.assertIn(key, palette)
                self.assertTrue(palette[key].startswith("#"))
        self.assertNotEqual(THEMES["dark"]["bg_panel"], THEMES["light"]["bg_panel"])


if __name__ == "__main__":
    unittest.main()
