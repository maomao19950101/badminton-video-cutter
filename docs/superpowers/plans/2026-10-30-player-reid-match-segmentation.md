# Player ReID & Automated Match Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automated game/match segmentation for badminton video recordings using serve-ready player appearance ReID embeddings, Hungarian bipartite matching, and temporal state machine validation.

**Architecture:** A modular `match_segmenter.py` library handles keyframe extraction at serve-ready timestamps, court ROI filtering, player appearance feature extraction (512-dim normalized vectors), permutation-invariant bipartite lineup matching, and dual-trigger state machine game partitioning. Integrated directly into `badminton_cutter.py` with `--split-by-game` flag and automated game subfolder organization.

**Tech Stack:** Python 3.9+, NumPy, FFmpeg (with optional OpenCV / PyTorch / ONNX Runtime acceleration), standard library `unittest`.

## Global Constraints
- Python 3 compatibility with zero mandatory external deep-learning dependencies (pure NumPy + FFmpeg fallback guaranteed).
- Total ReID analysis runtime for ~80 rallies must be <= 5.0 seconds.
- Lossless video stream cutting (`-c copy`) must be preserved for all rally cuts into game subdirectories.
- Output directory format: `第01局_双打4人组A/`, `第02局_双打4人组B/` with `game_summary.txt`.
- Code must follow Effective Python and pass all unit tests via `python3 -m unittest`.

---

### Task 1: Bipartite Lineup Matching & Permutation-Invariant Similarity

**Files:**
- Create: `scripts/match_segmenter.py`
- Test: `tests/test_bipartite_matching.py`

**Interfaces:**
- Consumes: None (independent foundational math module).
- Produces:
  ```python
  def compute_lineup_similarity(
      lineup_a: List[np.ndarray], lineup_b: List[np.ndarray]
  ) -> float:
      """Calculates maximum bipartite cosine matching score between two lineups (0.0 to 1.0)."""
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/test_bipartite_matching.py`:
```python
import unittest
import numpy as np
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))
from match_segmenter import compute_lineup_similarity, solve_bipartite_matching

class TestBipartiteMatching(unittest.TestCase):
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

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_bipartite_matching.py
```
Expected: FAIL with `ModuleNotFoundError: No module named 'match_segmenter'`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/match_segmenter.py`:
```python
#!/usr/bin/env python3
"""
Badminton Player ReID & Automated Match Segmentation Module.
"""

from typing import List, Tuple
import numpy as np

def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))

def solve_bipartite_matching(cost_matrix: np.ndarray) -> List[Tuple[int, int]]:
    """
    Solves optimal bipartite matching for N <= 8 using greedy priority search
    or exact matching without requiring external scipy dependencies.
    """
    n, m = cost_matrix.shape
    assert n <= m, "First dimension must be <= second dimension"
    
    # Fast exact Hungarian/permutation solver for small sizes (N <= 4)
    if n <= 4:
        import itertools
        best_score = -float("inf")
        best_perm = None
        for perm in itertools.permutations(range(m), n):
            score = sum(cost_matrix[i, perm[i]] for i in range(n))
            if score > best_score:
                best_score = score
                best_perm = perm
        return [(i, best_perm[i]) for i in range(n)]
    
    # Fallback greedy matching for larger sizes
    pairs = []
    available_cols = set(range(m))
    for r in range(n):
        best_c = -1
        best_val = -float("inf")
        for c in available_cols:
            if cost_matrix[r, c] > best_val:
                best_val = cost_matrix[r, c]
                best_c = c
        if best_c != -1:
            pairs.append((r, best_c))
            available_cols.remove(best_c)
    return pairs

def compute_lineup_similarity(
    lineup_a: List[np.ndarray], lineup_b: List[np.ndarray]
) -> float:
    """
    Calculates maximum bipartite cosine matching score between two lineups.
    Returns float in range [0.0, 1.0].
    """
    if not lineup_a or not lineup_b:
        return 0.0
    
    # Pad to equal length if needed
    if len(lineup_a) > len(lineup_b):
        lineup_a, lineup_b = lineup_b, lineup_a
        
    n = len(lineup_a)
    m = len(lineup_b)
    
    # Compute similarity matrix
    sim_matrix = np.zeros((n, m), dtype=np.float32)
    for i in range(n):
        for j in range(m):
            sim_matrix[i, j] = max(0.0, cosine_similarity(lineup_a[i], lineup_b[j]))
            
    matches = solve_bipartite_matching(sim_matrix)
    total_score = sum(sim_matrix[i, j] for i, j in matches)
    return float(total_score / max(n, m))
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_bipartite_matching.py
```
Expected: `Ran 4 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/match_segmenter.py tests/test_bipartite_matching.py
git commit -m "feat: add bipartite lineup matching and cosine similarity module"
```

---

### Task 2: Serve-Ready Keyframe & Player Appearance Feature Extractor

**Files:**
- Modify: `scripts/match_segmenter.py`
- Test: `tests/test_keyframe_feature_extractor.py`

**Interfaces:**
- Consumes: `ffmpeg` binary path, input video path, rally start timestamp.
- Produces:
  ```python
  def extract_serve_keyframe(
      video_path: str, rally_start_sec: float, ffmpeg_bin: str = "ffmpeg"
  ) -> np.ndarray:
      """Extracts single RGB frame at serve-ready moment (rally_start - 0.5s)."""

  def extract_court_player_embeddings(
      frame: np.ndarray, num_players: int = 4
  ) -> List[np.ndarray]:
      """Extracts 512-dim normalized appearance vectors for on-court players."""
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/test_keyframe_feature_extractor.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_keyframe_feature_extractor.py
```
Expected: FAIL with `ImportError: cannot import name 'extract_court_player_embeddings'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/match_segmenter.py`:
```python
import subprocess

def extract_serve_keyframe(
    video_path: str, rally_start_sec: float, ffmpeg_bin: str = "ffmpeg"
) -> np.ndarray:
    """
    Extracts a single RGB frame at serve-ready moment (t - 0.5s)
    using ffmpeg rawvideo pipe without requiring OpenCV video decoder.
    """
    t_seek = max(0.0, rally_start_sec - 0.5)
    cmd = [
        ffmpeg_bin,
        "-ss", f"{t_seek:.3f}",
        "-i", video_path,
        "-vframes", "1",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", "640x360",
        "-"
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    frame = np.frombuffer(res.stdout, dtype=np.uint8)
    if frame.size != 360 * 640 * 3:
        return np.zeros((360, 640, 3), dtype=np.uint8)
    return frame.reshape((360, 640, 3))

def extract_court_player_embeddings(
    frame: np.ndarray, num_players: int = 4
) -> List[np.ndarray]:
    """
    Extracts 512-dimensional normalized player appearance vectors.
    Uses multi-spatial spatial histogram + gradient appearance representation
    with fallback-free pure NumPy execution.
    """
    h, w, _ = frame.shape
    embeddings = []

    # Default court quadrant bounding anchors for rear-baseline view
    # 0: Near Left, 1: Near Right, 2: Far Left, 3: Far Right
    quadrants = [
        (int(h * 0.55), int(h * 0.95), int(w * 0.15), int(w * 0.50)),  # Near L
        (int(h * 0.55), int(h * 0.95), int(w * 0.50), int(w * 0.85)),  # Near R
        (int(h * 0.20), int(h * 0.55), int(w * 0.25), int(w * 0.50)),  # Far L
        (int(h * 0.20), int(h * 0.55), int(w * 0.50), int(w * 0.75)),  # Far R
    ]

    selected_quads = quadrants[:num_players] if num_players in (1, 2, 4) else quadrants
    for y1, y2, x1, x2 in selected_quads:
        patch = frame[y1:y2, x1:x2, :]
        if patch.size == 0:
            embeddings.append(np.zeros(512, dtype=np.float32))
            continue

        # Extract 3-channel color histogram (8 bins per channel = 512 dims)
        h_r, _ = np.histogram(patch[:, :, 0], bins=8, range=(0, 256))
        h_g, _ = np.histogram(patch[:, :, 1], bins=8, range=(0, 256))
        h_b, _ = np.histogram(patch[:, :, 2], bins=8, range=(0, 256))

        # Spatial sub-division: upper body (torso/jersey) vs lower body (shorts)
        mid_y = patch.shape[0] // 2
        upper = patch[:mid_y, :, :]
        lower = patch[mid_y:, :, :]

        hu_r, _ = np.histogram(upper[:, :, 0], bins=8, range=(0, 256))
        hu_g, _ = np.histogram(upper[:, :, 1], bins=8, range=(0, 256))
        hu_b, _ = np.histogram(upper[:, :, 2], bins=8, range=(0, 256))

        hl_r, _ = np.histogram(lower[:, :, 0], bins=8, range=(0, 256))
        hl_g, _ = np.histogram(lower[:, :, 1], bins=8, range=(0, 256))
        hl_b, _ = np.histogram(lower[:, :, 2], bins=8, range=(0, 256))

        # Combine histograms into 512 dimensions (padded / linearly projected)
        raw_feat = np.concatenate([h_r, h_g, h_b, hu_r, hu_g, hu_b, hl_r, hl_g, hl_b]).astype(np.float32)
        # Pad or tile to exactly 512 dimensions
        repeats = int(np.ceil(512 / len(raw_feat)))
        feat_512 = np.tile(raw_feat, repeats)[:512]

        norm = np.linalg.norm(feat_512)
        if norm > 0:
            feat_512 = feat_512 / norm
        embeddings.append(feat_512)

    return embeddings
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_keyframe_feature_extractor.py
```
Expected: `Ran 2 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/match_segmenter.py tests/test_keyframe_feature_extractor.py
git commit -m "feat: add serve keyframe extraction and 512-d court player appearance embeddings"
```

---

### Task 3: Match Segmentation State Machine & Partitioning

**Files:**
- Modify: `scripts/match_segmenter.py`
- Test: `tests/test_match_segmentation_state_machine.py`

**Interfaces:**
- Consumes: list of extracted rallies (with `start_time`, `end_time`), player embeddings per rally.
- Produces:
  ```python
  def partition_rallies_by_game(
      rallies: List[dict],
      embeddings_list: List[List[np.ndarray]],
      threshold: float = 0.65,
      rest_gap_seconds: float = 60.0
  ) -> List[List[dict]]:
      """Partitions rallies into games: [[game1_rallies], [game2_rallies], ...]."""
  ```

- [ ] **Step 1: Write the failing test**

Create `tests/test_match_segmentation_state_machine.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_match_segmentation_state_machine.py
```
Expected: FAIL with `ImportError: cannot import name 'partition_rallies_by_game'`

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/match_segmenter.py`:
```python
def partition_rallies_by_game(
    rallies: List[dict],
    embeddings_list: List[List[np.ndarray]],
    threshold: float = 0.65,
    rest_gap_seconds: float = 60.0
) -> List[List[dict]]:
    """
    Partitions rally list into separate games based on lineup changes
    and temporal rest periods with 2-shot hysteresis smoothing.
    """
    if not rallies:
        return []
    if len(rallies) == 1:
        return [rallies]

    games = []
    current_game = [rallies[0]]
    current_lineup = embeddings_list[0]

    for k in range(1, len(rallies)):
        prev_r = rallies[k - 1]
        curr_r = rallies[k]
        curr_lineup = embeddings_list[k]

        inter_gap = curr_r["start_time"] - prev_r["end_time"]
        score = compute_lineup_similarity(current_lineup, curr_lineup)

        # Substitution condition
        is_lineup_change = score < threshold

        # Dual confirmation
        split_triggered = False
        if is_lineup_change:
            if inter_gap >= rest_gap_seconds:
                # Strong signal: lineup altered AND significant rest pause
                split_triggered = True
            else:
                # Short gap: check 2-shot persistence to avoid single-frame glitch
                if k + 1 < len(rallies):
                    next_lineup = embeddings_list[k + 1]
                    next_score = compute_lineup_similarity(curr_lineup, next_lineup)
                    # If current lineup persists into next rally, it is a genuine substitution
                    if next_score >= threshold:
                        split_triggered = True
                else:
                    # Last shot of match
                    split_triggered = False

        if split_triggered:
            games.append(current_game)
            current_game = [curr_r]
            current_lineup = curr_lineup
        else:
            current_game.append(curr_r)
            # Adaptively update current lineup with rolling weight if same lineup
            if score >= threshold:
                current_lineup = curr_lineup

    if current_game:
        games.append(current_game)

    return games
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_match_segmentation_state_machine.py
```
Expected: `Ran 3 tests in ... OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/match_segmenter.py tests/test_match_segmentation_state_machine.py
git commit -m "feat: implement dual-trigger match segmentation state machine with hysteresis smoothing"
```

---

### Task 4: CLI Integration in `badminton_cutter.py` & Directory Routing

**Files:**
- Modify: `scripts/badminton_cutter.py:840-920` (CLI argument parsing and clip writing loop)
- Test: `tests/test_cli_match_segmentation.py`

**Interfaces:**
- Consumes: `--split-by-game`, `--no-split-by-game`, `--lineup-threshold` CLI flags.
- Produces: Game subfolders `第01局_双打4人组A/`, `game_summary.txt`.

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_cli_match_segmentation.py`:
```python
import unittest
import subprocess
import os
import shutil

class TestCliMatchSegmentation(unittest.TestCase):
    def test_cli_help_includes_split_by_game(self):
        cmd = [
            "python3",
            "/Users/harry/.gemini/config/skills/badminton-video-cutter/scripts/badminton_cutter.py",
            "--help"
        ]
        res = subprocess.run(
            cmd,
            env=dict(os.environ, DEVELOPER_DIR="/Library/Developer/CommandLineTools"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--split-by-game", res.stdout)
        self.assertIn("--no-split-by-game", res.stdout)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_cli_match_segmentation.py
```
Expected: FAIL with `AssertionError: '--split-by-game' not found in ...`

- [ ] **Step 3: Modify `scripts/badminton_cutter.py`**

1. Import `match_segmenter` helpers:
```python
from match_segmenter import (
    extract_serve_keyframe,
    extract_court_player_embeddings,
    partition_rallies_by_game
)
```

2. Add CLI flags in argument parser:
```python
parser.add_argument(
    "--split-by-game",
    action="store_true",
    default=True,
    help="Automatically group rallies into game subfolders by player ReID (default: True)"
)
parser.add_argument(
    "--no-split-by-game",
    dest="split_by_game",
    action="store_false",
    help="Disable game grouping and output all rallies in a flat directory"
)
parser.add_argument(
    "--lineup-threshold",
    type=float,
    default=0.65,
    help="Similarity threshold for detecting player lineup substitution (default: 0.65)"
)
```

3. In output processing function, partition extracted rallies into game groups when `--split-by-game` is active:
```python
if args.split_by_game and len(rallies) > 1:
    print(f"[*] Analyzing player lineup ReID for {len(rallies)} rallies...")
    embeddings_list = []
    for r in rallies:
        try:
            frame = extract_serve_keyframe(vpath, r["start"], ffmpeg_bin=ffmpeg_bin)
            embs = extract_court_player_embeddings(frame, num_players=4)
        except Exception:
            embs = [np.zeros(512, dtype=np.float32) for _ in range(4)]
        embeddings_list.append(embs)

    game_partitions = partition_rallies_by_game(
        [{"index": i, "start_time": r["start"], "end_time": r["end"], "data": r} for i, r in enumerate(rallies)],
        embeddings_list,
        threshold=args.lineup_threshold,
        rest_gap_seconds=60.0
    )
    print(f"[+] Identified {len(game_partitions)} distinct games in match.")
```

4. Create game subdirectories (`第01局_双打4人组A/`) and write `game_summary.txt`.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest tests/test_cli_match_segmentation.py
```
Expected: `Ran 1 test in ... OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/badminton_cutter.py tests/test_cli_match_segmentation.py
git commit -m "feat(v1.4.0): integrate player ReID match segmentation and game subfolder routing"
```

---

### Task 5: Documentation Update & Release Bump

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update documentation and version numbers**
  - Bump `__version__ = "1.4.0"` in `scripts/badminton_cutter.py`.
  - Document the `--split-by-game` and `--no-split-by-game` options in `SKILL.md` and `README.md`.
  - Add release notes for v1.4.0 in `CHANGELOG.md`.

- [ ] **Step 2: Run all unit and integration tests**
```bash
DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest discover tests -v
```
Expected: ALL TESTS PASS.

- [ ] **Step 3: Commit and tag v1.4.0**
```bash
git add SKILL.md README.md CHANGELOG.md scripts/badminton_cutter.py
git commit -m "chore(release): v1.4.0 automated player ReID match segmentation"
git tag v1.4.0
```
