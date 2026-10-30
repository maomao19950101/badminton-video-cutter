import unittest
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
from match_segmenter import extract_court_player_embeddings

class TestKeyframeFeatureExtractor(unittest.TestCase):
    def test_extract_synthetic_four_players(self):
        # Create a synthetic 360x640 RGB image with 4 distinct colored player boxes
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        # Near court left: Red
        frame[240:320, 160:240, :] = [255, 0, 0]
        # Near court right: Green
        frame[240:320, 400:480, :] = [0, 255, 0]
        # Far court left: Blue
        frame[100:180, 200:260, :] = [0, 0, 255]
        # Far court right: Yellow
        frame[100:180, 380:440, :] = [255, 255, 0]

        embeddings = extract_court_player_embeddings(frame, num_players=4)
        self.assertEqual(len(embeddings), 4)
        for emb in embeddings:
            self.assertEqual(emb.shape, (512,))
            # Must be L2 normalized (norm ~= 1.0)
            self.assertAlmostEqual(np.linalg.norm(emb), 1.0, places=3)

    def test_differentiate_distinct_uniforms(self):
        # Player in red vs player in blue should have low cosine similarity
        frame_red = np.zeros((360, 640, 3), dtype=np.uint8)
        frame_red[200:300, 200:300] = [255, 0, 0]
        emb_red = extract_court_player_embeddings(frame_red, num_players=1)[0]

        frame_blue = np.zeros((360, 640, 3), dtype=np.uint8)
        frame_blue[200:300, 200:300] = [0, 0, 255]
        emb_blue = extract_court_player_embeddings(frame_blue, num_players=1)[0]

        sim = float(np.dot(emb_red, emb_blue))
        self.assertLess(sim, 0.40)

if __name__ == "__main__":
    unittest.main()
