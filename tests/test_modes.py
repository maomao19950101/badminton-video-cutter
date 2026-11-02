#!/usr/bin/env python3
import unittest
import os
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
from modes_handler import (
    filter_solo_rallies,
    categorize_showcase_rallies,
    generate_condensed_reel,
    generate_vertical_clip,
    generate_review_package,
)


class TestModesHandler(unittest.TestCase):
    def test_showcase_categorization(self):
        rallies = [
            {"index": 1, "s_cut": 0.0, "e_cut": 18.0, "dur": 18.0, "is_smash": False},
            {"index": 2, "s_cut": 20.0, "e_cut": 28.0, "dur": 8.0, "is_smash": True},
            {"index": 3, "s_cut": 30.0, "e_cut": 38.0, "dur": 8.0, "is_smash": False},
            {"index": 4, "s_cut": 40.0, "e_cut": 62.0, "dur": 22.0, "is_smash": False},
        ]
        cats = categorize_showcase_rallies(rallies)
        self.assertEqual(len(cats["01_后场重杀突破"]), 1)
        self.assertEqual(cats["01_后场重杀突破"][0]["index"], 2)

        self.assertEqual(len(cats["02_多拍高能拉锯"]), 2)
        self.assertEqual(cats["02_多拍高能拉锯"][0]["index"], 1)
        self.assertEqual(cats["02_多拍高能拉锯"][1]["index"], 4)

        self.assertEqual(len(cats["03_网前平抽快攻"]), 1)
        self.assertEqual(cats["03_网前平抽快攻"][0]["index"], 3)

    def test_filter_solo_rallies(self):
        rallies = [
            {"index": 1, "lead_quadrant": 0},
            {"index": 2, "lead_quadrant": 1},
            {"index": 3, "lead_quadrant": 0},
            {"index": 4, "lead_quadrant": 2},
        ]
        solo = filter_solo_rallies(rallies, target_player="near_left")
        self.assertEqual(len(solo), 2)
        self.assertEqual(solo[0]["index"], 1)
        self.assertEqual(solo[1]["index"], 3)

        solo_right = filter_solo_rallies(rallies, target_player="near_right")
        self.assertEqual(len(solo_right), 1)
        self.assertEqual(solo_right[0]["index"], 2)

    def test_condensed_reel_empty_or_missing(self):
        # Empty list should return False gracefully
        self.assertFalse(generate_condensed_reel("ffmpeg", [], "/tmp/empty.mp4"))
        self.assertFalse(generate_condensed_reel("ffmpeg", ["/nonexistent/file.mp4"], "/tmp/empty.mp4"))

    def test_vertical_clip_missing_input(self):
        # Missing file should return False gracefully
        self.assertFalse(generate_vertical_clip("ffmpeg", "/nonexistent/in.mp4", "/tmp/out.mp4"))

    def test_review_report_calculation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            rallies = [
                {"s_cut": 10.0, "e_cut": 18.0, "dur": 8.0},
                {"s_cut": 30.0, "e_cut": 45.0, "dur": 15.0},
                {"s_cut": 60.0, "e_cut": 85.0, "dur": 25.0},
            ]
            # Mock review report generation with dummy video
            dummy_vid = os.path.join(tmp_dir, "dummy.mp4")
            with open(dummy_vid, "w") as f:
                f.write("dummy")

            clips, report_path = generate_review_package(
                "echo", dummy_vid, rallies, tmp_dir
            )
            self.assertTrue(os.path.exists(report_path))
            with open(report_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.assertIn("羽毛球技战术与发接发专项复盘报告", content)
                self.assertIn("分析总回合: 3 处", content)
                self.assertIn("平均回合时长: 16.0 秒", content)
                self.assertIn("全场最长拉锯: 25.0 秒", content)


if __name__ == "__main__":
    unittest.main()
