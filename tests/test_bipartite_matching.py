import unittest
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
from match_segmenter import compute_lineup_similarity, solve_bipartite_matching, cosine_similarity

class TestBipartiteMatching(unittest.TestCase):
    def test_cosine_similarity(self):
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.0, 1.0])
        v3 = np.array([2.0, 0.0])
        v_zero = np.array([0.0, 0.0])

        self.assertAlmostEqual(cosine_similarity(v1, v1), 1.0, places=4)
        self.assertAlmostEqual(cosine_similarity(v1, v2), 0.0, places=4)
        self.assertAlmostEqual(cosine_similarity(v1, v3), 1.0, places=4)
        self.assertAlmostEqual(cosine_similarity(v1, v_zero), 0.0, places=4)

    def test_identical_lineups_perfect_score(self):
        # 4 distinct orthogonal vectors
        v1 = np.array([1.0, 0.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0, 0.0])
        v3 = np.array([0.0, 0.0, 1.0, 0.0])
        v4 = np.array([0.0, 0.0, 0.0, 1.0])
        lineup_a = [v1, v2, v3, v4]
        lineup_b = [v1, v2, v3, v4]
        score = compute_lineup_similarity(lineup_a, lineup_b)
        self.assertAlmostEqual(score, 1.0, places=4)

    def test_permutation_invariance(self):
        # Lineup B is a permutation of Lineup A (players swapped positions)
        v1 = np.array([1.0, 0.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0, 0.0])
        v3 = np.array([0.0, 0.0, 1.0, 0.0])
        v4 = np.array([0.0, 0.0, 0.0, 1.0])
        lineup_a = [v1, v2, v3, v4]
        lineup_b = [v4, v1, v2, v3]
        score = compute_lineup_similarity(lineup_a, lineup_b)
        self.assertAlmostEqual(score, 1.0, places=4)

    def test_one_substitution(self):
        # 3 same players, 1 completely new orthogonal player
        v1 = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0, 0.0, 0.0])
        v3 = np.array([0.0, 0.0, 1.0, 0.0, 0.0])
        v4 = np.array([0.0, 0.0, 0.0, 1.0, 0.0])
        v5_new = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
        lineup_a = [v1, v2, v3, v4]
        lineup_b = [v1, v2, v3, v5_new]
        score = compute_lineup_similarity(lineup_a, lineup_b)
        # 3 matches of 1.0, 1 match of 0.0 => average 0.75
        self.assertAlmostEqual(score, 0.75, places=4)

    def test_complete_team_change(self):
        # All 4 players replaced
        lineup_a = [np.eye(8)[i] for i in range(4)]
        lineup_b = [np.eye(8)[i + 4] for i in range(4)]
        score = compute_lineup_similarity(lineup_a, lineup_b)
        self.assertAlmostEqual(score, 0.0, places=4)

    def test_empty_lineups(self):
        self.assertEqual(compute_lineup_similarity([], []), 0.0)
        self.assertEqual(compute_lineup_similarity([np.array([1.0, 0.0])], []), 0.0)

if __name__ == "__main__":
    unittest.main()
