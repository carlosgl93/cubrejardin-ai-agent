"""Minimal FAISS stub."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import numpy as np


class IndexFlatIP:
    """Simplified index using numpy."""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.vectors: List[np.ndarray] = []

    @property
    def ntotal(self) -> int:
        return len(self.vectors)

    def add(self, vectors: np.ndarray) -> None:
        for vector in vectors:
            self.vectors.append(vector)

    def search(self, vector: np.ndarray, top_k: int):  # type: ignore[no-untyped-def]
        scores = []
        for idx, stored in enumerate(self.vectors):
            score = float(np.dot(vector[0], stored))
            scores.append((score, idx))
        scores.sort(reverse=True)
        top_scores = [s for s, _ in scores[:top_k]] + [-1] * max(0, top_k - len(scores))
        top_indices = [i for _, i in scores[:top_k]] + [-1] * max(0, top_k - len(scores))
        return np.array([top_scores]), np.array([top_indices])


def normalize_L2(vectors: np.ndarray) -> None:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    vectors /= norms


def write_index(index: IndexFlatIP, path: str) -> None:
    data = [vector.tolist() for vector in index.vectors]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data))


def read_index(path: str) -> IndexFlatIP:
    data = json.loads(Path(path).read_text())
    index = IndexFlatIP(len(data[0]) if data else 1536)
    index.vectors = [np.array(vec, dtype="float32") for vec in data]
    return index
