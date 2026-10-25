from typing import Any

import numpy as np
import pytest

from exploreit.ranking.graph import LinkGraph
from exploreit.ranking.matrix import adjacency_matrix
from exploreit.ranking.prestige import Dangling, Normalization, PrestigeResult, prestige


def graph(*links: str) -> LinkGraph:
    pairs = tuple(tuple(link.split(">")) for link in links)
    pages = tuple(dict.fromkeys(page for pair in pairs for page in pair))
    return LinkGraph(pages, pairs)  # type: ignore[arg-type]


def run(g: LinkGraph, weighted: bool = False, **options: Any) -> PrestigeResult:
    return prestige(adjacency_matrix(g, weighted=weighted), g.pages, **options)


def test_every_page_starts_with_the_same_prestige() -> None:
    result = run(graph("a>b", "b>c", "c>a"), initial=1.0)

    assert result.history[0].tolist() == [1, 1, 1]


def test_symmetric_cycle_is_already_stable() -> None:
    result = run(graph("a>b", "b>c", "c>a"))

    assert result.converged
    assert result.iterations == 1
    assert result.scores.tolist() == [1, 1, 1]


def test_page_with_more_links_in_ranks_higher() -> None:
    # a, b and c all link to hub; hub links back to a.
    result = run(graph("a>hub", "b>hub", "c>hub", "hub>a", "a>b"), max_iterations=500)

    assert result.ranking()[0][1] == "hub"


def test_normalisation_keeps_the_average_at_one() -> None:
    result = run(graph("a>b", "b>a", "a>c", "c>a"), max_iterations=200, smoothing=0.5)

    assert result.scores.sum() == pytest.approx(3)


def test_without_normalisation_values_grow_in_cycles() -> None:
    result = run(
        graph("a>b", "b>a", "a>c", "c>a"), normalization=Normalization.NONE, max_iterations=10
    )

    assert not result.converged
    assert result.scores.max() > 10


def test_alternating_graph_never_settles_without_smoothing() -> None:
    # b is linked from a and c, and links to both: prestige swaps between b and {a, c}.
    g = graph("a>b", "b>a", "b>c", "c>b")

    plain = run(g, max_iterations=50)
    smoothed = run(g, max_iterations=200, smoothing=0.5)

    assert not plain.converged
    assert smoothed.converged
    assert smoothed.ranking()[0][1] == "b"


def test_converged_unweighted_prestige_is_the_leading_eigenvector() -> None:
    g = graph("a>b", "b>c", "c>a", "a>c", "c>d", "d>a")
    matrix = adjacency_matrix(g)

    result = prestige(matrix, g.pages, max_iterations=1000, tolerance=1e-12, smoothing=0.3)

    values, vectors = np.linalg.eig(matrix.T)
    leading = np.abs(vectors[:, np.argmax(values.real)].real)
    assert result.converged
    assert np.allclose(result.scores / result.scores.sum(), leading / leading.sum())


def test_weighted_prestige_matches_pagerank_without_damping() -> None:
    nx = pytest.importorskip("networkx")
    g = graph("a>b", "a>c", "b>c", "c>a", "d>c", "c>d")

    result = run(
        g,
        weighted=True,
        dangling=Dangling.SPREAD,
        tolerance=1e-12,
        max_iterations=2000,
        smoothing=0.2,
    )

    reference = nx.pagerank(nx.DiGraph(list(g.links)), alpha=1.0, tol=1e-12, max_iter=10_000)
    expected = np.array([reference[page] for page in g.pages])
    assert np.allclose(result.scores / result.scores.sum(), expected, atol=1e-6)


def test_dangling_prestige_is_lost_or_shared() -> None:
    g = graph("a>b", "b>c")  # c links nowhere

    lost = run(g, weighted=True, normalization=Normalization.NONE, max_iterations=1)
    shared = run(
        g,
        weighted=True,
        normalization=Normalization.NONE,
        max_iterations=1,
        dangling=Dangling.SPREAD,
    )

    assert lost.scores.sum() == pytest.approx(2)  # c's vote vanished
    assert shared.scores.sum() == pytest.approx(3)


def test_ranking_shares_places_for_equal_prestige() -> None:
    result = run(graph("a>b", "b>c", "c>a"))

    assert [place for place, _, _ in result.ranking()] == [1, 1, 1]


def test_smoothing_must_be_below_one() -> None:
    with pytest.raises(ValueError, match="smoothing"):
        run(graph("a>b"), smoothing=1.0)
