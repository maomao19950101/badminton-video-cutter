#!/usr/bin/env python3
"""
Unit tests for Badminton Rally Decoupling & Dead-Ball Separation (v1.4.4).
"""

import unittest
from unittest.mock import patch
import os
import sys

# Ensure scripts dir is on sys.path
SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from badminton_cutter import extract_multi_shot_rallies


class TestRallyDecoupling(unittest.TestCase):
    def test_decouple_smash_landing_and_subsequent_serve(self):
        """
        Tests that a rally ending with a decisive smash and ground contact
        is strictly decoupled from a subsequent serve, even when dead-ball
        floor scoop taps bridge the intermission with individual gaps < 2.85s.
        """
        # Simulated sequence representing Rally 81 from Match 2 followed by a genuine 5-shot Point 2:
        # Point 1: 10 hits ending with smash (1774.00, E=1.55e8), block (1774.53), landing (1775.09)
        # Intermission: 5 floor scoop taps (1775.96, 1776.44, 1778.07, 1778.88, 1780.21)
        # Point 2: 5 hits starting with serve (1782.38), return (1784.05), hit (1784.99), kill (1786.67), counter (1787.80)
        peaks = [
            (1767.19, 1.90e7), # P1 Serve
            (1769.16, 1.21e7), # P1 Return
            (1770.44, 5.14e6),
            (1771.95, 2.14e7),
            (1772.43, 8.40e6),
            (1772.89, 2.68e7),
            (1773.59, 1.08e7),
            (1774.00, 1.55e8), # P1 Smash
            (1774.53, 1.53e7), # P1 Block
            (1775.09, 5.86e6), # P1 Ground Contact
            (1775.96, 1.15e7), # Dead-ball floor scoop 1
            (1776.44, 1.52e7), # Dead-ball floor scoop 2
            (1778.07, 1.11e7), # Dead-ball floor tap 3
            (1778.88, 6.36e6), # Dead-ball floor tap 4
            (1780.21, 4.92e6), # Dead-ball floor tap 5
            (1782.38, 5.28e6), # P2 Serve
            (1784.05, 5.62e6), # P2 Return
            (1784.99, 2.30e7), # P2 Stroke
            (1786.67, 1.59e7), # P2 Winner
            (1787.80, 2.50e7), # P2 Continuation
        ]
        v_dur = 1812.0

        rallies = extract_multi_shot_rallies(peaks, v_dur)
        self.assertEqual(len(rallies), 2, f"Expected exactly 2 rallies, got {len(rallies)}")

        p1 = rallies[0]
        p2 = rallies[1]

        # Verify Point 1 bounds
        self.assertAlmostEqual(p1["first_hit"], 1767.19, places=2)
        self.assertAlmostEqual(p1["last_hit"], 1775.09, places=2)
        self.assertEqual(p1["hits"], 10)
        self.assertTrue(p1["s_cut"] <= 1767.19)
        self.assertTrue(p1["e_cut"] >= 1775.09)

        # Verify Point 2 bounds
        self.assertAlmostEqual(p2["first_hit"], 1782.38, places=2)
        self.assertAlmostEqual(p2["last_hit"], 1787.80, places=2)
        self.assertEqual(p2["hits"], 5)
        self.assertTrue(p2["s_cut"] <= 1782.38)
        self.assertTrue(p2["e_cut"] >= 1787.80)

        # Verify no dead-ball overlap
        self.assertTrue(p1["e_cut"] < p2["s_cut"], "Rallies must not overlap")

    def test_reject_deadball_ball_retrieval_after_rally(self):
        """
        Tests that an intermission where players are simply walking and retrieving
        shuttlecocks (or cross-talk impact from adjacent courts with < 5 hits)
        is completely rejected, while the preceding genuine multi-shot rally
        is cleanly preserved. (Fix for Rally 105 in v1.4.7).
        """
        peaks = [
            (1767.19, 1.90e7), # P1 Serve
            (1769.16, 1.21e7), # P1 Return
            (1770.44, 5.14e6),
            (1771.95, 2.14e7),
            (1772.43, 8.40e6),
            (1772.89, 2.68e7),
            (1773.59, 1.08e7),
            (1774.00, 1.55e8), # P1 Smash
            (1774.53, 1.53e7), # P1 Block
            (1775.09, 5.86e6), # P1 Ground Contact
            (1775.96, 1.15e7), # Floor scoop 1
            (1776.44, 1.52e7), # Floor scoop 2
            (1778.07, 1.11e7), # Floor tap 3
            (1778.88, 6.36e6), # Floor tap 4
            (1780.21, 4.92e6), # Floor tap 5
            (1782.38, 5.28e6), # Ball retrieval scoop across net
            (1784.05, 5.62e6), # Floor bounce
            (1784.99, 2.30e7), # Adjacent court smash bleed
            (1786.67, 1.59e7), # Adjacent court return bleed
        ]
        v_dur = 1812.0

        # With default min_hits=5, exactly 1 rally (Point 1) is returned
        rallies = extract_multi_shot_rallies(peaks, v_dur, min_hits=5)
        self.assertEqual(len(rallies), 1, f"Expected exactly 1 rally, got {len(rallies)}")
        p1 = rallies[0]
        self.assertEqual(p1["hits"], 10)
        self.assertAlmostEqual(p1["first_hit"], 1767.19, places=2)
        self.assertAlmostEqual(p1["last_hit"], 1775.09, places=2)

        # With min_hits=3, the 4-hit noise cluster would be admitted
        rallies_lenient = extract_multi_shot_rallies(peaks, v_dur, min_hits=3)
        self.assertEqual(len(rallies_lenient), 2)

    def test_preserve_high_clear_active_continuation(self):
        """
        Tests that an active high clear with flight time 2.50s is preserved
        without premature cutoff when bilateral play continues.
        """
        peaks = [
            (100.0, 1.2e7), # Serve
            (101.5, 8.0e6), # Return
            (103.0, 2.5e7), # Deep high clear / lift
            (105.5, 3.2e7), # Smash return (gap = 2.50s)
            (106.3, 1.5e7), # Defensive block
            (107.5, 4.0e7), # Net kill winner
        ]
        v_dur = 200.0

        rallies = extract_multi_shot_rallies(peaks, v_dur)
        self.assertEqual(len(rallies), 1, "High clear must not cleave active rally")
        self.assertEqual(rallies[0]["hits"], 6)
        self.assertAlmostEqual(rallies[0]["first_hit"], 100.0, places=2)
        self.assertAlmostEqual(rallies[0]["last_hit"], 107.5, places=2)

    def test_preserve_smash_defense_and_counter_stroke(self):
        """
        Tests that an active rally where a smash is returned by a defender
        and followed by a counter-stroke is preserved intact without premature cutoff.
        Simulated sequence representing Rally 67 from Match 2:
        - 1193.68 (E=6.07e6): Serve
        - 1195.46 (E=3.35e7): Return of serve (gap=1.78s)
        - 1195.87 (E=1.04e7): Drive (gap=0.41s)
        - 1197.31 (E=6.62e6): Drop (gap=1.44s)
        - 1198.75 (E=8.64e6): Lift (gap=1.44s)
        - 1199.16 (E=1.82e7): Drive (gap=0.41s)
        - 1199.56 (E=5.33e7): Smash (gap=0.40s)
        - 1200.71 (E=8.24e6): Defensive lift return (gap=1.15s)
        - 1201.73 (E=6.09e6): Counter-kill / stroke (gap=1.02s)
        """
        peaks = [
            (1193.68, 6.07e6),
            (1195.46, 3.35e7),
            (1195.87, 1.04e7),
            (1197.31, 6.62e6),
            (1198.75, 8.64e6),
            (1199.16, 1.82e7),
            (1199.56, 5.33e7),
            (1200.71, 8.24e6),
            (1201.73, 6.09e6),
        ]
        v_dur = 1812.0
        rallies = extract_multi_shot_rallies(peaks, v_dur)
        self.assertEqual(len(rallies), 1, "Rally 67 must not be truncated or cleaved")
        r = rallies[0]
        self.assertEqual(r["hits"], 9, "Must retain all 9 shots from serve to counter-kill")
        self.assertAlmostEqual(r["first_hit"], 1193.68, places=2)
        self.assertAlmostEqual(r["last_hit"], 1201.73, places=2)
        self.assertTrue(r["s_cut"] <= 1193.68)
        self.assertTrue(r["e_cut"] >= 1201.73 + 0.85)

    def test_preserve_opening_serve_with_return_flight(self):
        """
        Tests that an opening serve with flight time up to 2.10s
        is not falsely pruned as a leading dead-ball tap when followed
        by an active attacking return.
        """
        peaks = [
            (50.00, 5.5e6), # Soft high serve
            (51.85, 2.8e7), # Attack return of serve (gap=1.85s)
            (52.25, 1.2e7), # Drive return
            (53.50, 1.6e7), # Lift / drop
            (54.80, 3.5e7), # Smash winner
        ]
        v_dur = 100.0
        rallies = extract_multi_shot_rallies(peaks, v_dur)
        self.assertEqual(len(rallies), 1)
        r = rallies[0]
        self.assertEqual(r["hits"], 5)
        self.assertAlmostEqual(r["first_hit"], 50.00, places=2)
        self.assertAlmostEqual(r["last_hit"], 54.80, places=2)

    def test_preserve_multi_shot_rally_with_intermediate_smash_and_clear(self):
        """
        Tests that an extended rally containing an intermediate smash,
        defensive return, subsequent high clear, and continuation attacks
        is preserved intact as a single 20s+ rally without being cleaved in half.
        Simulated sequence representing Rally 40 from Match 2:
        - 715.32: Serve
        - 716.47: Return
        - 718.25: Intermediate smash (E=6.38e7)
        - 719.07: Defensive return (gap=0.82s, E=1.04e7)
        - 720.54: Counter-stroke (gap=1.47s, E=9.34e6)
        - 722.62: Deep high clear (gap=2.08s, E=9.70e6)
        - 722.97: Attack (gap=0.35s, E=1.99e7)
        - 724.90: Drive attack (E=2.35e7)
        - 725.83: Smash attack (E=4.07e7)
        - 726.80: Defense (E=1.05e7)
        - 728.29: Lift (E=5.66e6)
        - 729.35: Attack (E=2.89e7)
        - 731.17: Drive (E=1.83e7)
        - 733.15: Counter (E=2.43e7)
        - 733.68: Smash kill (E=6.67e7)
        - 734.21: Block / landing (E=4.32e7)
        """
        peaks = [
            (715.32, 7.73e6),
            (716.47, 4.50e6),
            (718.25, 6.38e7),
            (719.07, 1.04e7),
            (720.54, 9.34e6),
            (722.62, 9.70e6),
            (722.97, 1.99e7),
            (724.90, 2.35e7),
            (725.83, 4.07e7),
            (726.80, 1.05e7),
            (728.29, 5.66e6),
            (729.35, 2.89e7),
            (731.17, 1.83e7),
            (733.15, 2.43e7),
            (733.68, 6.67e7),
            (734.21, 4.32e7),
        ]
        v_dur = 1812.0
        rallies = extract_multi_shot_rallies(peaks, v_dur)
        self.assertEqual(len(rallies), 1, "Rally with intermediate smash and clear must remain 1 continuous rally")
        r = rallies[0]
        self.assertEqual(r["hits"], 16)
        self.assertAlmostEqual(r["first_hit"], 715.32, places=2)
        self.assertAlmostEqual(r["last_hit"], 734.21, places=2)

    def test_preserve_net_exchange_after_smash_defense(self):
        """
        Tests that an active rally where a smash is defended and immediately followed
        by a rapid net exchange / flat drive counter-attack (all gaps <= 1.15s, soft touch)
        is preserved intact in its entirety without premature severance at the smash defense.
        (Fix for Rally 03 in v1.4.8).
        Simulated sequence representing Rally 03 from Match 2:
        - 51.09: Serve (E=1.95e7)
        - 53.15: Return (E=1.59e7)
        - 54.565: Counter (E=5.15e6)
        - 55.425: Drive (E=6.65e6)
        - 56.72: Push (E=1.11e7)
        - 57.09: Setup (E=1.07e7)
        - 57.445: Smash (E=7.80e7)
        - 58.335: Defensive block (gap=0.89s, E=9.61e6)
        - 59.200: Counter-drive (gap=0.865s, E=7.82e6)
        - 59.605: Net tap (gap=0.405s, E=7.37e6)
        - 60.470: Lift (gap=0.865s, E=7.68e6)
        - 60.835: Fast push (gap=0.365s, E=1.24e7)
        - 61.750: Block / floor landing (gap=0.915s, E=4.62e6)
        - 64.340: Dead-ball floor tap (gap=2.59s, E=6.75e6)
        - 66.575: Next serve (gap=2.235s, E=4.04e7)
        """
        peaks = [
            (51.090, 1.95e7),
            (53.150, 1.59e7),
            (54.565, 5.15e6),
            (55.425, 6.65e6),
            (56.720, 1.11e7),
            (57.090, 1.07e7),
            (57.445, 7.80e7),
            (58.335, 9.61e6),
            (59.200, 7.82e6),
            (59.605, 7.37e6),
            (60.470, 7.68e6),
            (60.835, 1.24e7),
            (61.750, 4.62e6),
            (64.340, 6.75e6),
            (66.575, 4.04e7),
            (68.735, 4.59e7),
            (69.315, 5.20e6),
            (69.790, 1.18e7),
            (70.185, 4.32e7),
        ]
        v_dur = 1812.0
        rallies = extract_multi_shot_rallies(peaks, v_dur, min_hits=5)
        self.assertTrue(len(rallies) >= 2, f"Expected at least 2 rallies, got {len(rallies)}")
        r3 = rallies[0]
        self.assertEqual(r3["hits"], 13, f"Rally 03 must preserve all 13 hits, got {r3['hits']}")
        self.assertAlmostEqual(r3["first_hit"], 51.09, places=2)
        self.assertAlmostEqual(r3["last_hit"], 61.75, places=2)
        self.assertTrue(r3["s_cut"] <= 51.09)
        self.assertTrue(r3["e_cut"] >= 61.75 + 0.85)

    def test_preserve_soft_finish_after_smash(self):
        """
        Tests that a rally containing a smash followed by defensive block,
        net push, and high clear to baseline is preserved in its entirety
        without premature cutoff at the smash defense.
        Simulated sequence representing Rally 85 from Match 2:
        - 1606.81: Serve (E=2.71e7)
        - 1607.29: Return (E=8.16e7)
        - 1608.14: Counter (E=6.46e6)
        - 1608.97: Push (E=1.60e7)
        - 1609.69: Clear (E=6.59e6)
        - 1610.49: Drop (E=1.72e7)
        - 1610.85: Smash (E=8.16e7)
        - 1611.38: Defensive block (gap=0.53s, E=5.35e6)
        - 1612.10: Net push (gap=0.72s, E=5.73e6)
        - 1613.95: High clear to baseline (gap=1.85s, E=7.01e6)
        """
        peaks = [
            (1606.81, 2.71e7),
            (1607.29, 8.16e7),
            (1608.14, 6.46e6),
            (1608.97, 1.60e7),
            (1609.69, 6.59e6),
            (1610.49, 1.72e7),
            (1610.85, 8.16e7),
            (1611.38, 5.35e6),
            (1612.10, 5.73e6),
            (1613.95, 7.01e6),
        ]
        v_dur = 1812.0
        rallies = extract_multi_shot_rallies(peaks, v_dur)
        self.assertEqual(len(rallies), 1, "Rally 85 must remain 1 complete rally without being cleaved after smash defense")
        r = rallies[0]
        self.assertEqual(r["hits"], 10, "Must preserve all 10 strokes from serve to high clear")
        self.assertAlmostEqual(r["first_hit"], 1606.81, places=2)
        self.assertAlmostEqual(r["last_hit"], 1613.95, places=2)
        self.assertTrue(r["s_cut"] <= 1606.81)
        self.assertTrue(r["e_cut"] >= 1613.95 + 1.50, "e_cut must allow high clear to descend and land on court")

    def test_reject_ball_change_intermission_with_adjacent_court_bleed(self):
        """
        Tests that an intermission where players are changing shuttlecocks
        (floor scoop taps + walk to net basket + adjacent court 16-hit rally bleed)
        is completely decoupled and eliminated, while the preceding Point 16
        and subsequent Point 18 are preserved intact. (Fix for Rally 17 in v1.4.9).
        """
        peaks = [
            # Point 16 (20 hits, ends with smash at 268.21, defense at 270.36, net kill at 276.46)
            (254.51, 1.50e7), # Serve
            (255.49, 1.38e7), # Return
            (257.82, 1.57e7), # High clear
            (259.74, 5.58e6), # Drop
            (260.43, 1.01e7), # Net push
            (261.86, 5.70e6), # Lift
            (262.71, 2.77e7), # Attack
            (265.44, 1.80e7), # Drive
            (267.44, 5.95e6), # Block
            (268.21, 4.99e7), # Smash
            (270.36, 2.48e7), # Defense
            (270.72, 3.03e7), # Net attack
            (271.90, 2.94e7), # Drive
            (272.77, 1.40e7),
            (273.49, 2.19e7),
            (274.17, 7.36e6),
            (274.89, 1.77e7),
            (275.61, 1.44e7),
            (276.11, 3.38e7),
            (276.46, 2.02e7), # Winner / ground contact
            # Intermission (ball change): 2 floor scoop taps by player in black
            (279.00, 1.44e7), # Floor scoop 1
            (280.42, 2.35e7), # Floor flip into hand 2 (gap=1.42s)
            # Gap of 2.69s as player walks to net post basket
            # Court 7 (adjacent court) plays 16 hits:
            (283.11, 1.31e7), # Court 7 shot 1
            (283.64, 7.53e6), # Court 7 shot 2 (gap=0.53s < 0.65s)
            (284.12, 7.97e6),
            (285.39, 7.37e6),
            (285.77, 1.67e7),
            (287.18, 1.56e7),
            (287.90, 2.38e7),
            (288.87, 1.27e7),
            (290.32, 4.41e6),
            (291.56, 1.14e7),
            (292.62, 6.47e6),
            (294.10, 6.74e6),
            (295.08, 8.28e6),
            (295.57, 1.02e7),
            (295.94, 3.61e7),
            (297.33, 9.46e6),
            # Gap of 4.31s while players reset
            # Point 18 (18 hits, starts with high serve at 301.64, return at 304.38)
            (301.64, 4.88e7), # High serve
            (304.38, 8.24e6), # Return of high serve (gap=2.74s)
            (304.80, 1.28e7), # Net cutoff
            (305.17, 2.21e7), # Drive
            (306.37, 1.14e7),
            (307.04, 1.43e7),
            (307.56, 1.59e7),
            (308.33, 7.08e6),
            (308.70, 1.42e7),
            (309.05, 6.17e6),
            (309.48, 6.57e6),
            (309.85, 2.14e7),
            (310.83, 1.16e8), # Smash
            (311.82, 3.71e7),
            (312.51, 2.13e7),
            (313.14, 1.24e7),
            (314.23, 4.39e7), # Smash
            (315.44, 5.84e6), # Ground contact
        ]
        v_dur = 1812.0
        rallies = extract_multi_shot_rallies(peaks, v_dur, min_hits=5)

        # Floor scoop taps [279.00, 280.42] must decouple from Court 7 (gap=2.69s >= 2.10s, len(sub)==2, next_g=0.53s < 0.65s)
        # and be pruned because len(sub) == 2 < min_hits (5).
        # Point 16 and Point 18 must be preserved!
        p16 = next((r for r in rallies if abs(r["first_hit"] - 254.51) < 1.0), None)
        self.assertIsNotNone(p16, "Point 16 must be preserved")
        self.assertEqual(p16["hits"], 20)
        self.assertAlmostEqual(p16["last_hit"], 276.46, places=2)

        p18 = next((r for r in rallies if abs(r["first_hit"] - 301.64) < 1.0), None)
        self.assertIsNotNone(p18, "Point 18 must be preserved")
        self.assertEqual(p18["hits"], 18)
        self.assertAlmostEqual(p18["first_hit"], 301.64, places=2)

        # Confirm no rally starts with the floor scoop at 279.00 or 280.42
        has_scoop_rally = any(abs(r["first_hit"] - 279.00) < 0.5 or abs(r["first_hit"] - 280.42) < 0.5 for r in rallies)
        self.assertFalse(has_scoop_rally, "Floor scoop taps during ball change must not form a rally")

    def test_anchor_rally_start_to_serve_pruning_adjacent_noise(self):
        """
        Tests that when adjacent-court acoustic hits bleed into the start of a rally
        while our court players are walking / taking service stance,
        Rule 4 (Pre-Serve Stationary Boundary & Serve Anchoring) detects the pre-serve
        stationary pause and explosive surge, pruning leading adjacent-court hits.
        """
        from unittest.mock import patch

        # Simulated cluster representing Match 2 Game 3 Clip 1:
        # First 3 hits: adjacent court noise (588.85, 590.22, 592.50) while our players walk
        # Authentic serve: 598.54
        # Followed by 5 active rally hits
        peaks = [
            (588.85, 1.2e7),
            (590.22, 1.1e7),
            (592.50, 1.3e7),
            (598.54, 2.5e7), # Genuine serve
            (599.09, 3.1e7), # Return
            (601.20, 4.5e7), # Smash
            (602.10, 2.2e7), # Drive
            (603.35, 1.8e7), # Kill
        ]

        def mock_motion(cap, fps, t_sec, vpath=None, ffmpeg_bin=None):
            # If sampling before or after the genuine serve at 598.54:
            if t_sec < 598.0:
                # Walking or stationary pause (near <= 7.0, our <= 7.5)
                return (6.5, 7.0, 6.0, 1.0, 3.0)
            else:
                # Active play surge after serve (near >= 25.0, our >= 20.0)
                return (22.0, 18.0, 25.0, 1.0, 4.0)

        with patch("badminton_cutter.sample_instant_motion", side_effect=mock_motion):
            rallies = extract_multi_shot_rallies(peaks, v_dur=1000.0, min_hits=5, vpath="/dummy/test.mp4")

        self.assertEqual(len(rallies), 1)
        r = rallies[0]
        # s_cut must be anchored to the authentic serve at 598.54 - 0.75 = 597.79s
        # NOT the adjacent court noise at 588.85 - 0.75 = 588.10s!
        self.assertAlmostEqual(r["s_cut"], 598.54 - 0.75, places=2)
        self.assertEqual(r["first_hit"], 598.54)
        self.assertEqual(r["hits"], 5)

    def test_check_clip_is_real_play_rejects_walkoff_corridor(self):
        """
        Tests that check_clip_is_real_play rejects walk-off intervals where players
        have exited the court and walk along the camera walkway with backpacks/phones (v1.8.4).
        """
        from badminton_cutter import check_clip_is_real_play
        from unittest.mock import patch

        # Mock motions for a walk-off interval (UID 33: b_avg >= 14.0, b_max >= 25.0, opening b_max >= 12.0)
        def mock_walkoff_motion(cap, fps, t_sec, vpath=None, ffmpeg_bin=None):
            # our_m, far_m, near_m, top_d, b_max
            return (21.0, 25.0, 17.0, 1.8, 30.0)

        peaks = [(1047.7, 1.8e7), (1049.2, 2.8e7), (1050.0, 6.7e6), (1051.2, 9.7e6), (1051.9, 2.5e7)]
        with patch("os.path.exists", return_value=True), patch("badminton_cutter.sample_instant_motion", side_effect=mock_walkoff_motion):
            is_real = check_clip_is_real_play(
                cap="dummy_cap", fps=30.0, s_cut=1046.0, e_cut=1054.0,
                min_dur=5.0, r_peaks=peaks, vpath="/dummy/video.mp4", min_hits=5
            )
        self.assertFalse(is_real, "Walk-off corridor motion must be rejected by check_clip_is_real_play")

        # Mock motions for an authentic rally (UID 10: opening b_max is low 2.7, play is active)
        def mock_authentic_motion(cap, fps, t_sec, vpath=None, ffmpeg_bin=None):
            # Returns normal rally motion with low boundary movement
            return (18.0, 16.0, 20.0, 1.5, 4.0)

        with patch("os.path.exists", return_value=True), patch("badminton_cutter.sample_instant_motion", side_effect=mock_authentic_motion):
            is_real = check_clip_is_real_play(
                cap="dummy_cap", fps=30.0, s_cut=209.0, e_cut=231.0,
                min_dur=5.0, r_peaks=peaks, vpath="/dummy/video.mp4", min_hits=5
            )
        self.assertTrue(is_real, "Authentic rally must pass check_clip_is_real_play")

    def test_pre_serve_ball_picking_walking_pruned(self):
        """
        Tests that extract_multi_shot_rallies prunes leading dead-ball walking / ball-picking hits
        clustered before the genuine serve by identifying the pre-serve stationary trough (v1.8.5).
        """
        # Walking/ball-picking noise hits (gaps < 2.0s), followed by pre-serve stillness and genuine serve
        peaks = [
            (1243.04, 7.1e6),  # Walking step / floor tap
            (1244.12, 1.7e7),  # Walking step / adjacent noise
            (1245.83, 2.3e7),  # Footstep
            (1247.80, 6.2e6),  # Walking back to position
            (1249.50, 6.0e6),  # Ball bounce / tap
            (1251.00, 7.0e6),  # Settling into stance
            (1252.78, 1.0e7),  # Genuine serve (preceded by stillness at 1250-1252)
            (1253.73, 2.5e7),  # Return
            (1254.32, 1.5e7),  # Stroke 3
            (1255.06, 1.5e7),  # Stroke 4
            (1256.12, 1.8e7),  # Stroke 5
            (1257.10, 2.0e7),  # Stroke 6
        ]

        def mock_motion(cap, fps, t_sec, vpath=None, ffmpeg_bin=None):
            if 1242.0 <= t_sec < 1250.0:
                # Walking to pick up ball (active footsteps, no pre-serve stance)
                return (14.0, 18.0, 8.0, 1.0, 3.0)
            elif 1250.0 <= t_sec < 1252.0:
                # Pre-serve stationary trough (players standing still in service boxes)
                return (3.8, 6.0, 1.5, 0.8, 2.5)
            else:
                # Active rally play after serve
                return (18.0, 24.0, 12.0, 0.9, 3.5)

        with patch("badminton_cutter.sample_instant_motion", side_effect=mock_motion):
            rallies = extract_multi_shot_rallies(peaks, v_dur=1800.0, min_hits=5, vpath="/dummy/video.mp4")

        self.assertEqual(len(rallies), 1)
        r = rallies[0]
        # Must be anchored to the authentic serve at 1252.78 - 0.75 = 1252.03s,
        # NOT the initial walking at 1243.04!
        self.assertAlmostEqual(r["s_cut"], 1252.78 - 0.75, places=2)
        self.assertEqual(r["first_hit"], 1252.78)
        self.assertEqual(r["hits"], 6)


if __name__ == "__main__":
    unittest.main()
