import unittest
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
from match_segmenter import partition_rallies_by_game

class TestMatchSegmentationStateMachine(unittest.TestCase):
    def test_single_game_no_substitution(self):
        # 10 rallies played by the same 4 players
        team_a = [np.eye(4)[i] for i in range(4)]
        rallies = [
            {"index": i, "start_time": i * 30.0, "end_time": i * 30.0 + 15.0}
            for i in range(10)
        ]
        embeddings = [team_a for _ in range(10)]
        games = partition_rallies_by_game(rallies, embeddings)
        self.assertEqual(len(games), 1)
        self.assertEqual(len(games[0]), 10)

    def test_two_distinct_games_with_substitution(self):
        # 5 rallies with Team A, 90s break, 5 rallies with Team B (new players)
        team_a = [np.eye(8)[i] for i in range(4)]
        team_b = [np.eye(8)[i + 4] for i in range(4)]

        rallies_g1 = [
            {"index": i, "start_time": i * 30.0, "end_time": i * 30.0 + 15.0}
            for i in range(5)
        ]
        # Inter-game gap of 100 seconds
        rallies_g2 = [
            {"index": i + 5, "start_time": 250.0 + i * 30.0, "end_time": 250.0 + i * 30.0 + 15.0}
            for i in range(5)
        ]
        rallies = rallies_g1 + rallies_g2
        embeddings = [team_a] * 5 + [team_b] * 5

        games = partition_rallies_by_game(rallies, embeddings, threshold=0.65, rest_gap_seconds=60.0)
        self.assertEqual(len(games), 2)
        self.assertEqual(len(games[0]), 5)
        self.assertEqual(len(games[1]), 5)

    def test_transient_single_shot_occlusion_smoothing(self):
        # 1 rally in the middle has a temporary occlusion/outlier, but reverts immediately
        team_a = [np.eye(8)[i] for i in range(4)]
        corrupted_team = [np.zeros(8) for _ in range(4)]

        rallies = [
            {"index": i, "start_time": i * 20.0, "end_time": i * 20.0 + 10.0}
            for i in range(7)
        ]
        # Short gap (10s), index 3 has corrupted detection
        embeddings = [team_a, team_a, team_a, corrupted_team, team_a, team_a, team_a]

        games = partition_rallies_by_game(rallies, embeddings, threshold=0.65, rest_gap_seconds=60.0)
        # Should NOT split into new game because gap < 60s and it reverts next shot
        self.assertEqual(len(games), 1)
        self.assertEqual(len(games[0]), 7)

if __name__ == "__main__":
    unittest.main()
