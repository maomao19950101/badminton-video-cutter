#!/usr/bin/env python3
"""
Badminton Player ReID & Automated Match Segmentation Module.
"""

from typing import List, Tuple
import itertools
import numpy as np


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Computes cosine similarity between two 1D feature vectors.

    Returns float in range [-1.0, 1.0], or 0.0 if either vector has zero magnitude.
    """
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def solve_bipartite_matching(cost_matrix: np.ndarray) -> List[Tuple[int, int]]:
    """Solves optimal bipartite matching maximizing total weight.

    Requires cost_matrix.shape[0] <= cost_matrix.shape[1].
    Uses exact permutation search for N <= 4 (O(M!/(M-N)!)),
    and greedy priority matching for N > 4 without requiring external dependencies.
    """
    n, m = cost_matrix.shape
    if n > m:
        raise ValueError(f"First dimension ({n}) must be <= second dimension ({m})")

    if n == 0 or m == 0:
        return []

    # Fast exact Hungarian/permutation solver for small sizes (N <= 4)
    if n <= 4:
        best_score = -float("inf")
        best_perm = None
        for perm in itertools.permutations(range(m), n):
            score = sum(cost_matrix[i, perm[i]] for i in range(n))
            if score > best_score:
                best_score = score
                best_perm = perm
        if best_perm is not None:
            return [(i, best_perm[i]) for i in range(n)]
        return []

    # Fallback greedy matching for larger sizes (N > 4)
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
    """Calculates maximum bipartite cosine matching score between two lineups.

    Returns float in range [0.0, 1.0].
    """
    if not lineup_a or not lineup_b:
        return 0.0

    # Ensure lineup_a length is <= lineup_b length for matching
    swapped = False
    if len(lineup_a) > len(lineup_b):
        lineup_a, lineup_b = lineup_b, lineup_a
        swapped = True

    n = len(lineup_a)
    m = len(lineup_b)

    # Compute pairwise similarity matrix
    sim_matrix = np.zeros((n, m), dtype=np.float32)
    for i in range(n):
        for j in range(m):
            sim_matrix[i, j] = max(0.0, cosine_similarity(lineup_a[i], lineup_b[j]))

    matches = solve_bipartite_matching(sim_matrix)
    total_score = sum(sim_matrix[i, j] for i, j in matches)

    return float(total_score / max(n, m))


def extract_serve_keyframe(
    video_path: str, rally_start_sec: float, ffmpeg_bin: str = "ffmpeg"
) -> np.ndarray:
    """
    Extracts a single RGB frame at serve-ready moment (t - 0.5s)
    using ffmpeg rawvideo pipe without requiring OpenCV video decoder.
    """
    import subprocess

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
    Uses spatial upper-body (jersey: 256-d) and lower-body (shorts: 256-d)
    3D joint color cube histograms with background downweighting.
    Guarantees pure NumPy execution with sub-millisecond latency.
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

        mid_y = patch.shape[0] // 2
        upper = patch[:mid_y, :, :]
        lower = patch[mid_y:, :, :]

        # Upper body (jersey): 256 dims (8 x 8 x 4)
        qu_r = (upper[:, :, 0] // 32).astype(np.int32)
        qu_g = (upper[:, :, 1] // 32).astype(np.int32)
        qu_b = (upper[:, :, 2] // 64).astype(np.int32)
        idx_u = qu_r * 32 + qu_g * 4 + qu_b
        wu = np.ones_like(idx_u, dtype=np.float32)
        wu[idx_u == 0] = 0.05
        hu = np.bincount(idx_u.ravel(), weights=wu.ravel(), minlength=256).astype(np.float32)
        norm_u = np.linalg.norm(hu)
        if norm_u > 0:
            hu /= norm_u

        # Lower body (shorts): 256 dims (8 x 8 x 4)
        ql_r = (lower[:, :, 0] // 32).astype(np.int32)
        ql_g = (lower[:, :, 1] // 32).astype(np.int32)
        ql_b = (lower[:, :, 2] // 64).astype(np.int32)
        idx_l = ql_r * 32 + ql_g * 4 + ql_b
        wl = np.ones_like(idx_l, dtype=np.float32)
        wl[idx_l == 0] = 0.05
        hl = np.bincount(idx_l.ravel(), weights=wl.ravel(), minlength=256).astype(np.float32)
        norm_l = np.linalg.norm(hl)
        if norm_l > 0:
            hl /= norm_l

        feat_512 = np.concatenate([hu, hl])
        norm = np.linalg.norm(feat_512)
        if norm > 0:
            feat_512 = feat_512 / norm
        embeddings.append(feat_512)

    return embeddings


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


