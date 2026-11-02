#!/usr/bin/env python3
"""
Unit tests for Badminton Rally Decoupling & Dead-Ball Separation (v1.4.4).
"""

import unittest
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


if __name__ == "__main__":
    unittest.main()
