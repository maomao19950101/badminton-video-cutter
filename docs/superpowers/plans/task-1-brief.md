# Task 1 Brief: Bipartite Lineup Matching & Permutation-Invariant Similarity

## Files:
- Create: `scripts/match_segmenter.py`
- Test: `tests/test_bipartite_matching.py`

## Working Directory:
`/Users/harry/.gemini/config/skills/badminton-video-cutter`

## Environment Notes:
Use `DEVELOPER_DIR=/Library/Developer/CommandLineTools python3` for running python commands and tests, or uv standalone python.
Do not use raw `/usr/bin/python3` without `DEVELOPER_DIR=/Library/Developer/CommandLineTools` to avoid Xcode license prompts.

## Global Constraints:
- Python 3 compatibility with zero mandatory external deep-learning dependencies (pure NumPy + FFmpeg fallback guaranteed).
- Total ReID analysis runtime for ~80 rallies must be <= 5.0 seconds.
- Code must pass all unit tests via `DEVELOPER_DIR=/Library/Developer/CommandLineTools python3 -m unittest`.

## Task Specification:
- Implement `cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float`
- Implement `solve_bipartite_matching(cost_matrix: np.ndarray) -> List[Tuple[int, int]]` (exact permutation solver for N <= 4, greedy for N > 4)
- Implement `compute_lineup_similarity(lineup_a: List[np.ndarray], lineup_b: List[np.ndarray]) -> float` (returns [0.0, 1.0])
- Write unit tests in `tests/test_bipartite_matching.py` covering:
  - Identical lineups (Score == 1.0)
  - Permutation invariance (swapped positions, Score == 1.0)
  - One substitution (Score == 0.75)
  - Complete team change (Score == 0.0)
- Follow TDD:
  1. Write failing test
  2. Run test to verify it fails
  3. Implement code
  4. Run test to verify it passes
  5. Commit: `git add scripts/match_segmenter.py tests/test_bipartite_matching.py && git commit -m "feat: add bipartite lineup matching and cosine similarity module"`
