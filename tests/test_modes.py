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


if __name__ == "__main__":
    unittest.main()
