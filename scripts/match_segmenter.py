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
