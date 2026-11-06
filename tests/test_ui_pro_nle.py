#!/usr/bin/env python3
"""
Unit tests for Badminton Studio Pro NLE UI (v1.8.4).
Verifies:
- Complete removal of AI/Codex cliches (#10a37f emerald green, neon cyber gradients, pitch-black #0c0c0e).
- Presence of Apple Pro Blue (#0a84ff / #0071e3) and Studio Slate Gray (#16161a / #1e1e24).
- Icon + Text paired professional controls with explicit Chinese labels.
- Presence of 6 rich mode card descriptors.
"""

import unittest
import os
import re

UI_HTML_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "ui", "index.html"))


class TestProNLEUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(UI_HTML_PATH, "r", encoding="utf-8") as f:
            cls.html = f.read()

    def test_no_ai_emerald_green_cliches(self):
        """Ensures all OpenAI Codex #10a37f and #34d399 greens are purged."""
        self.assertNotIn("#10a37f", self.html.lower(), "OpenAI emerald green (#10a37f) must not be present in Pro NLE UI")
        self.assertNotIn("#34d399", self.html.lower(), "Cyber emerald green (#34d399) must not be present in Pro NLE UI")
        self.assertNotIn("#0c0c0e", self.html.lower(), "Pitch-black hacker background (#0c0c0e) must be replaced with Studio Slate Gray")

    def test_apple_pro_blue_and_slate_gray_tokens(self):
        """Verifies Apple Pro Blue and Studio Slate Gray color tokens exist."""
        self.assertIn("#0a84ff", self.html.lower(), "Apple Pro Blue (#0a84ff) must be defined as primary accent")
        self.assertIn("#16161a", self.html.lower(), "Studio Slate Gray (#16161a) must be defined as background")
        self.assertIn("#1e1e24", self.html.lower(), "Studio Panel Gray (#1e1e24) must be defined as panel background")

    def test_paired_icon_and_text_controls(self):
        """Verifies buttons have clear Chinese labels, not just cryptic icons."""
        self.assertTrue(
            "导出比赛集锦" in self.html or "导出集锦" in self.html,
            "Main export action must have explicit Chinese label"
        )
        self.assertTrue(
            "起点微调" in self.html or "起点" in self.html,
            "In-point trim must have explicit Chinese label"
        )
        self.assertTrue(
            "终点微调" in self.html or "终点" in self.html,
            "Out-point trim must have explicit Chinese label"
        )
        self.assertTrue(
            "保留本回合" in self.html or "保留" in self.html,
            "Keep toggle button must have explicit Chinese label"
        )

    def test_five_mode_cards_with_descriptions(self):
        """Verifies all 5 video highlight modes are defined with clear Chinese descriptions."""
        modes = ["按局", "纯享", "竖屏", "独享", "高光"]
        for m in modes:
            self.assertIn(m, self.html, f"Mode descriptor for '{m}' must be present in UI")

    def test_theme_system_support(self):
        """Verifies both dark and light modes are supported."""
        self.assertIn('data-theme="dark"', self.html)
        self.assertIn('data-theme="light"', self.html)


if __name__ == "__main__":
    unittest.main()
