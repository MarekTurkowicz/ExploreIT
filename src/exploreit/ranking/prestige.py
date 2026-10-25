"""Prestige of pages computed iteratively: p(u) = sum over v of A(v, u) * p(v).

A page is as prestigious as the pages linking to it. Starting from the same prestige
for every page, the formula is applied again and again until the values settle.

Strategy for cycles. In a cycle prestige keeps flowing round, so the raw values either
grow without limit (each step multiplies them by the largest eigenvalue of A) or swap
back and forth forever (for example in a graph that splits into two alternating
halves). Three rules keep the computation meaningful:

1. Normalise after every step, so only the proportions between pages matter and the
   values cannot explode or vanish.
2. Stop when no page changes by more than `tolerance`, or after `max_iterations` steps,
   and report whether the values really settled.
3. Optionally smooth each step, p = (1 - s) * A^T p + s * p. Keeping part of the old
   value removes the back-and-forth swapping without changing where the values settle.
"""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from exploreit.ranking.matrix import Matrix


class Normalization(StrEnum):
    """How prestige is rescaled after every step."""

    SUM = "sum"  # values add up to the number of pages, so the average stays 1
    MAX = "max"  # the best page has prestige 1
    NONE = "none"  # raw values, to show why normalisation is needed


class Dangling(StrEnum):
    """What happens to the prestige of a page without outgoing links."""

    LOST = "lost"  # its vote goes nowhere, as the plain formula says
    SPREAD = "spread"  # its vote is shared equally by all pages


@dataclass(frozen=True)
class PrestigeResult:
    pages: tuple[str, ...]
    scores: np.ndarray  # final prestige, in `pages` order
    history: list[np.ndarray]  # prestige before the first step and after every step
    converged: bool

    @property
    def iterations(self) -> int:
        return len(self.history) - 1

    def ranking(self) -> list[tuple[int, str, float]]:
        """(place, page, prestige), best first; equal prestige shares a place."""
        order = sorted(range(len(self.pages)), key=lambda i: -self.scores[i])
        places: list[tuple[int, str, float]] = []
        for position, index in enumerate(order, start=1):
            score = float(self.scores[index])
            tied = places and np.isclose(places[-1][2], score)
            places.append((places[-1][0] if tied else position, self.pages[index], score))
        return places


def prestige(
    matrix: Matrix,
    pages: tuple[str, ...],
    *,
    initial: float = 1.0,
    normalization: Normalization = Normalization.SUM,
    dangling: Dangling = Dangling.LOST,
    smoothing: float = 0.0,
    tolerance: float = 1e-6,
    max_iterations: int = 100,
) -> PrestigeResult:
    """Iterate p(u) = sum_v A(v, u) p(v), starting with `initial` prestige for every page."""
    if not 0 <= smoothing < 1:
        raise ValueError("smoothing must be at least 0 and less than 1")
    size = len(pages)
    current = np.full(size, float(initial))
    history = [current]
    no_links_out = matrix.sum(axis=1) == 0
    converged = False

    for _ in range(max_iterations):
        following = matrix.T @ current
        if dangling is Dangling.SPREAD and size:
            following = following + current[no_links_out].sum() / size
        following = (1 - smoothing) * following + smoothing * current
        following = _normalise(following, normalization, size)
        change = float(np.abs(following - current).max()) if size else 0.0
        current = following
        history.append(current)
        if change <= tolerance:
            converged = True
            break
    return PrestigeResult(pages, current, history, converged)


def _normalise(values: np.ndarray, normalization: Normalization, size: int) -> np.ndarray:
    scale = 1.0
    if normalization is Normalization.SUM and values.sum() > 0:
        scale = size / float(values.sum())
    elif normalization is Normalization.MAX and values.max(initial=0) > 0:
        scale = 1 / float(values.max())
    return values * scale
