"""Every ranking method behind one interface, and comparisons between them.

Adding a method means writing one function `(graph, settings) -> Scores` and listing
it in METHODS; the comparison, the command line and the application pick it up.
"""

import csv
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import numpy as np

from exploreit.options import Dangling, Normalization
from exploreit.ranking.bridges import betweenness
from exploreit.ranking.eigen import leading_eigenvector
from exploreit.ranking.graph import LinkGraph
from exploreit.ranking.matrix import adjacency_matrix, short_labels, trusted_matrix
from exploreit.ranking.prestige import prestige
from exploreit.ranking.query import query_match, query_words
from exploreit.ranking.words import word_cascade


@dataclass(frozen=True)
class Settings:
    """Options shared by the iterative methods."""

    normalization: Normalization = Normalization.SUM
    dangling: Dangling = Dangling.LOST
    smoothing: float = 0.0
    jump: float = 0.0  # random jump to any page; 0 keeps the plain formula
    tolerance: float = 1e-6
    max_iterations: int = 200
    cascade_words: int = 10  # words in the first round of the word cascade
    weight_links: float = 0.5  # parts of ExploreIT rank
    weight_text: float = 0.3
    weight_bridges: float = 0.2
    weight_query: float = 0.5  # used only with a query
    query: str = ""  # search words; when set, ExploreIT rank answers this query


DEFAULT_SETTINGS = Settings()


@dataclass(frozen=True)
class Scores:
    """What a method computes: one score per page, in graph order."""

    values: np.ndarray
    iterations: int = 0
    converged: bool = True
    history: list[np.ndarray] = field(default_factory=list)  # for iterative methods
    eigenvalue: float = float("nan")  # only the eigenvector method has one


@dataclass(frozen=True)
class Method:
    name: str
    description: str
    compute: Callable[[LinkGraph, Settings], Scores]


@dataclass(frozen=True)
class MethodResult:
    method: Method
    scores: Scores
    seconds: float

    def places(self) -> list[int]:
        return places(self.scores.values)


@dataclass(frozen=True)
class Comparison:
    graph: LinkGraph
    results: list[MethodResult]

    def table(self) -> list[tuple[str, list[int], list[float]]]:
        """(page, places, scores) with one place and score per method, best first.

        Rows are ordered by the first method, ties broken by the following ones.
        """
        all_places = [result.places() for result in self.results]
        rows = [
            (
                page,
                [places_[index] for places_ in all_places],
                [float(result.scores.values[index]) for result in self.results],
            )
            for index, page in enumerate(self.graph.pages)
        ]
        return sorted(rows, key=lambda row: (row[1], row[0]))

    def agreement(self) -> list[tuple[str, str, float]]:
        """Kendall's tau for every pair of methods: 1 = same order, -1 = reversed."""
        taus = kendall_taus([result.scores.values for result in self.results])
        return [
            (self.results[i].method.name, self.results[j].method.name, taus[i, j])
            for i, j in combinations(range(len(self.results)), 2)
        ]


def _links_in(graph: LinkGraph, _: Settings) -> Scores:
    return Scores(adjacency_matrix(graph).sum(axis=0))


def _prestige(weighted: bool) -> Callable[[LinkGraph, Settings], Scores]:
    def compute(graph: LinkGraph, settings: Settings) -> Scores:
        result = prestige(
            adjacency_matrix(graph, weighted=weighted),
            graph.pages,
            normalization=settings.normalization,
            dangling=settings.dangling,
            smoothing=settings.smoothing,
            jump=settings.jump,
            tolerance=settings.tolerance,
            max_iterations=settings.max_iterations,
        )
        return Scores(result.scores, result.iterations, result.converged, result.history)

    return compute


def _eigenvector(graph: LinkGraph, settings: Settings) -> Scores:
    result = leading_eigenvector(adjacency_matrix(graph), tolerance=min(settings.tolerance, 1e-8))
    return Scores(result.vector, result.iterations, result.converged, eigenvalue=result.value)


TRUSTED_JUMP = 0.15


def _trusted_prestige(graph: LinkGraph, settings: Settings) -> Scores:
    result = prestige(
        trusted_matrix(graph),
        graph.pages,
        normalization=settings.normalization,
        dangling=Dangling.SPREAD,  # a page without links out shares its vote with everyone
        smoothing=max(settings.smoothing, 0.15),  # never swap back and forth
        jump=max(settings.jump, TRUSTED_JUMP),  # never fall into a trap of linked pages
        tolerance=settings.tolerance,
        max_iterations=settings.max_iterations,
    )
    return Scores(result.scores, result.iterations, result.converged, result.history)


def _word_cascade(graph: LinkGraph, settings: Settings) -> Scores:
    return Scores(word_cascade(graph.pages, graph.texts, settings.cascade_words).scores)


def _bridges(graph: LinkGraph, _: Settings) -> Scores:
    return Scores(betweenness(graph))


def _query_match(graph: LinkGraph, settings: Settings) -> Scores:
    return Scores(query_match(graph.pages, graph.texts, settings.query))


def _explore_rank(graph: LinkGraph, settings: Settings) -> Scores:
    """Trusted links, the word cascade, bridges and the query match, mixed by weight.

    Each part is scaled to 0..1 first. The links part already counts menu and footer
    links less (see `trusted_matrix`), and on a graph with merged duplicates no page is
    counted twice. With a query, its match joins the mix and, like a search engine,
    only the pages that match keep a score.
    """
    links = _trusted_prestige(graph, settings)
    query = _query_match(graph, settings).values
    searching = bool(query_words(settings.query))
    parts = [
        (settings.weight_links, links.values),
        (settings.weight_text, _word_cascade(graph, settings).values),
        (settings.weight_bridges, betweenness(graph)),
        (settings.weight_query, query),
    ]
    # A part that is all zeros (no stored content, no query) leaves its weight unused.
    used = [(weight, values) for weight, values in parts if weight > 0 and values.max() > 0]
    total = sum(weight for weight, _ in used) or 1.0
    combined = sum(weight / total * values / values.max() for weight, values in used)
    values = np.asarray(combined, dtype=float) if used else np.zeros(len(graph.pages))
    if searching:
        values = np.where(query > 0, values, 0.0)
    return Scores(values, links.iterations, links.converged, links.history)


METHODS = [
    Method("links in", "Number of pages linking to the page (a simple baseline).", _links_in),
    Method("prestige", "p(u) = sum of A(v,u) p(v) on the adjacency matrix.", _prestige(False)),
    Method(
        "weighted prestige",
        "The same on A(v,u) = 1/Nv: every page shares one vote among its links.",
        _prestige(True),
    ),
    Method(
        "eigenvector",
        "Eigenvector of the largest eigenvalue of the adjacency matrix (power method).",
        _eigenvector,
    ),
    Method(
        "trusted prestige",
        "Weighted prestige where mutual links and menu links count less (spam resistance).",
        _trusted_prestige,
    ),
    Method(
        "word cascade",
        "Pages using most of the site's most repeated words, round by round (needs content).",
        _word_cascade,
    ),
    Method("bridges", "Share of shortest paths between other pages passing through.", _bridges),
    Method(
        "ExploreIT rank",
        "Trusted links + word cascade + bridges (+ query match), mixed by the weights.",
        _explore_rank,
    ),
]
QUERY_METHOD = Method(
    "query match",
    "TF-IDF of the query words in the page text: frequent here, rare elsewhere.",
    _query_match,
)


def methods_for(settings: Settings) -> list[Method]:
    """Every method; the query match joins, before ExploreIT rank, when there is a query."""
    if not query_words(settings.query):
        return list(METHODS)
    return [*METHODS[:-1], QUERY_METHOD, METHODS[-1]]


def format_tau(tau: float) -> str:
    return "n/a" if np.isnan(tau) else f"{tau:.3f}"


def format_eigenvalue(value: float) -> str:
    return "" if np.isnan(value) else f"{value:.4f}"


def write_ranking_csv(comparison: Comparison, path: Path) -> None:
    """Save the place and score of every page under every method, best first."""
    labels = dict(zip(comparison.graph.pages, short_labels(comparison.graph), strict=True))
    names = [result.method.name for result in comparison.results]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["label", "url", *(f"{name} {kind}" for name in names for kind in ("place", "score"))]
        )
        for page, page_places, scores in comparison.table():
            values = (
                value
                for place, score in zip(page_places, scores, strict=True)
                for value in (place, f"{score:.6g}")
            )
            writer.writerow([labels[page], page, *values])


def run_method(method: Method, graph: LinkGraph, settings: Settings) -> MethodResult:
    started = time.perf_counter()
    scores = method.compute(graph, settings)
    return MethodResult(method, scores, time.perf_counter() - started)


def compare(
    graph: LinkGraph,
    settings: Settings = DEFAULT_SETTINGS,
    methods: Sequence[Method] = (),
) -> Comparison:
    """Run `methods`, by default every method that fits the settings (`methods_for`)."""
    chosen = methods or methods_for(settings)
    return Comparison(graph, [run_method(method, graph, settings) for method in chosen])


def places(scores: np.ndarray) -> list[int]:
    """Place of every page, 1 = highest score; equal scores share the better place."""
    order = np.argsort(-scores, kind="stable")
    result = [0] * len(scores)
    for position, index in enumerate(order.tolist(), start=1):
        previous = int(order[position - 2]) if position > 1 else -1
        tied = previous >= 0 and _close(scores[previous], scores[index])
        result[index] = result[previous] if tied else position
    return result


def kendall_tau(first: np.ndarray, second: np.ndarray) -> float:
    """Kendall's tau-b: how often two rankings put a pair of pages in the same order.

    Counts concordant and discordant pairs and corrects for ties, so methods that give
    many pages the same score are not penalised for it. When one method gives every page
    the same score there is no order to compare and the result is NaN.
    """
    return float(kendall_taus([first, second])[0, 1])


ROWS_AT_ONCE = 256  # pages compared with all others in one step; bounds the memory used


def kendall_taus(rankings: Sequence[np.ndarray]) -> np.ndarray:
    """Kendall's tau-b of every pair of rankings, as a symmetric matrix.

    For a block of pages at a time, the order of each page against every later page is
    worked out once per ranking and then reused for all pairs of rankings.
    """
    scores = [np.asarray(values, dtype=float) for values in rankings]
    count, size = len(scores), len(scores[0]) if scores else 0
    concordant, discordant, untied = (np.zeros((count, count)) for _ in range(3))
    columns = np.arange(size)
    for start in range(0, size, ROWS_AT_ONCE):
        rows = np.arange(start, min(start + ROWS_AT_ONCE, size))
        later = columns[None, :] > rows[:, None]  # each pair of pages once
        orders = []
        for values in scores:
            here, there = values[rows][:, None], values[None, :]
            order = np.where(np.isclose(here, there), 0, np.sign(here - there)).astype(np.int8)
            orders.append(np.where(later, order, 0))
        for i, j in combinations(range(count), 2):
            product = orders[i] * orders[j]
            concordant[i, j] += np.count_nonzero(product > 0)
            discordant[i, j] += np.count_nonzero(product < 0)
        for i in range(count):
            untied[i, i] += np.count_nonzero(orders[i])
    taus = np.eye(count)
    for i, j in combinations(range(count), 2):
        # tau-b = (C - D) / sqrt(pairs untied in the first * pairs untied in the second)
        denominator = np.sqrt(untied[i, i] * untied[j, j])
        taus[i, j] = taus[j, i] = (
            (concordant[i, j] - discordant[i, j]) / denominator if denominator else np.nan
        )
    return taus


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-8 + 1e-5 * abs(b)  # np.isclose, without its overhead
