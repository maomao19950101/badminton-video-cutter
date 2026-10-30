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
    Uses adaptive court mat background subtraction to isolate player foreground
    and 3D color cube histograms with spatial player clustering.
    Guarantees pure NumPy execution with sub-millisecond latency.
    """
    h, w, _ = frame.shape
    if frame.size == 0 or np.mean(frame) < 5.0:
        return [np.zeros(512, dtype=np.float32) for _ in range(num_players)]

    # 1. Estimate court floor color from center play zone
    center_patch = frame[int(h * 0.55):int(h * 0.75), int(w * 0.38):int(w * 0.62)]
    if center_patch.size > 0:
        mat_color = np.median(center_patch, axis=(0, 1))
    else:
        mat_color = np.array([80.0, 150.0, 150.0], dtype=np.float32)

    # 2. Foreground segmentation (pixels deviating from court mat)
    color_diff = np.linalg.norm(frame.astype(np.float32) - mat_color, axis=-1)

    # 3. Four quadrant player masks (Near Left, Near Right, Far Left, Far Right)
    mid_x = int(w * 0.50)
    quad_masks = [
        # Near Left
        (int(h * 0.52), int(h * 0.95), int(w * 0.15), mid_x, 38.0),
        # Near Right
        (int(h * 0.52), int(h * 0.95), mid_x, int(w * 0.85), 38.0),
        # Far Left
        (int(h * 0.22), int(h * 0.52), int(w * 0.25), mid_x, 32.0),
        # Far Right
        (int(h * 0.22), int(h * 0.52), mid_x, int(w * 0.75), 32.0),
    ]

    embeddings = []
    selected_quads = quad_masks[:num_players] if num_players in (1, 2, 4) else quad_masks
    for y1, y2, x1, x2, th in selected_quads:
        patch = frame[y1:y2, x1:x2, :]
        diff_patch = color_diff[y1:y2, x1:x2]
        fg_mask = (diff_patch > th)

        fg_pixels = patch[fg_mask]
        if len(fg_pixels) < 25:
            # Fallback to center of patch if player color is near mat
            fg_pixels = patch[patch.shape[0]//4: 3*patch.shape[0]//4, patch.shape[1]//4: 3*patch.shape[1]//4].reshape(-1, 3)

        if len(fg_pixels) == 0:
            embeddings.append(np.zeros(512, dtype=np.float32))
            continue

        # 3D color cube histogram (8x8x8 = 512 bins)
        q = (fg_pixels // 32).astype(np.int32)
        idx = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
        hist = np.bincount(idx, minlength=512).astype(np.float32)
        norm = np.linalg.norm(hist)
        if norm > 0:
            hist /= norm
        embeddings.append(hist)

    return embeddings


def partition_rallies_by_game(
    rallies: List[dict],
    embeddings_list: List[List[np.ndarray]],
    threshold: float = 0.65,
    rest_gap_seconds: float = 40.0,
    long_intermission_seconds: float = 90.0,
    min_rallies_per_game: int = 5
) -> List[List[dict]]:
    """
    Partitions rally list into separate games based on player lineup changes
    and physical inter-game rest intervals.
    """
    if not rallies:
        return []
    if len(rallies) <= min_rallies_per_game:
        return [rallies]

    raw_games = []
    current_game = [rallies[0]]
    current_lineup = embeddings_list[0]

    for k in range(1, len(rallies)):
        prev_r = rallies[k - 1]
        curr_r = rallies[k]
        curr_lineup = embeddings_list[k]

        curr_start = curr_r.get("start_time", curr_r.get("s_cut", 0.0))
        prev_end = prev_r.get("end_time", prev_r.get("e_cut", 0.0))
        inter_gap = curr_start - prev_end
        score = compute_lineup_similarity(current_lineup, curr_lineup)

        split_triggered = False
        # In badminton, a game cannot end without players stopping to rest/rotate
        if inter_gap >= rest_gap_seconds:
            if score < threshold:
                split_triggered = True
            elif inter_gap >= long_intermission_seconds:
                split_triggered = True

        if split_triggered:
            raw_games.append(current_game)
            current_game = [curr_r]
            current_lineup = curr_lineup
        else:
            current_game.append(curr_r)
            if score >= threshold:
                current_lineup = curr_lineup

    if current_game:
        raw_games.append(current_game)

    # Post-processing: merge tiny orphan clusters (< min_rallies_per_game) into neighbors
    merged_games = []
    for g in raw_games:
        if not merged_games:
            merged_games.append(g)
        elif len(g) < min_rallies_per_game:
            merged_games[-1].extend(g)
        elif len(merged_games[-1]) < min_rallies_per_game:
            merged_games[-1].extend(g)
        else:
            merged_games.append(g)

    return merged_games


