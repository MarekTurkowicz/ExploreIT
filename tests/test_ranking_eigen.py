import numpy as np
import pytest

from exploreit.ranking.eigen import leading_eigenvector, numpy_eigenvector
from exploreit.ranking.graph import LinkGraph
from exploreit.ranking.matrix import adjacency_matrix
from exploreit.ranking.prestige import prestige


def graph(*links: str) -> LinkGraph:
    pairs = tuple(tuple(link.split(">")) for link in links)
    pages = tuple(dict.fromkeys(page for pair in pairs for page in pair))
    return LinkGraph(pages, pairs)  # type: ignore[arg-type]


GRAPH = graph("a>b", "b>c", "c>a", "a>c", "c>d", "d>a", "b>d")


def test_power_method_matches_numpy() -> None:
    matrix = adjacency_matrix(GRAPH)

    ours = leading_eigenvector(matrix)
    reference = numpy_eigenvector(matrix)

    assert ours.converged
    assert ours.value == pytest.approx(reference.value)
    assert np.allclose(ours.vector, reference.vector, atol=1e-8)
    assert ours.vector.sum() == pytest.approx(1)


def test_eigenvalue_of_a_cycle_is_one() -> None:
    result = leading_eigenvector(adjacency_matrix(graph("a>b", "b>c", "c>a")))

    assert result.value == pytest.approx(1)
    assert np.allclose(result.vector, [1 / 3] * 3)


def test_shift_lets_alternating_graphs_converge() -> None:
    # Pages split into {b} and {a, c} that point at each other: eigenvalues +-sqrt(2).
    matrix = adjacency_matrix(graph("a>b", "b>a", "b>c", "c>b"))

    plain = leading_eigenvector(matrix, shift=0.0, max_iterations=200)
    shifted = leading_eigenvector(matrix)

    assert not plain.converged
    assert shifted.converged
    assert shifted.value == pytest.approx(np.sqrt(2))


def test_converged_prestige_ranks_like_the_eigenvector() -> None:
    matrix = adjacency_matrix(GRAPH)

    iterated = prestige(matrix, GRAPH.pages, smoothing=0.3, tolerance=1e-12, max_iterations=5000)
    eigen = leading_eigenvector(matrix)

    assert np.allclose(iterated.scores / iterated.scores.sum(), eigen.vector, atol=1e-8)


def test_empty_matrix() -> None:
    assert leading_eigenvector(np.zeros((0, 0))).vector.size == 0
    assert numpy_eigenvector(np.zeros((0, 0))).vector.size == 0
