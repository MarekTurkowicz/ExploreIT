import numpy as np
import pytest

from exploreit.ranking.graph import LinkGraph
from exploreit.ranking.methods import (
    METHODS,
    Method,
    Scores,
    Settings,
    compare,
    kendall_tau,
    places,
)


def graph(*links: str) -> LinkGraph:
    pairs = tuple(tuple(link.split(">")) for link in links)
    pages = tuple(dict.fromkeys(page for pair in pairs for page in pair))
    return LinkGraph(pages, pairs)  # type: ignore[arg-type]


GRAPH = graph("a>hub", "b>hub", "c>hub", "hub>a", "a>b", "b>c", "c>a")


def test_every_method_ranks_every_page() -> None:
    comparison = compare(GRAPH, Settings(max_iterations=500, smoothing=0.3))

    assert [result.method.name for result in comparison.results] == [m.name for m in METHODS]
    for result in comparison.results:
        assert result.scores.values.shape == (len(GRAPH.pages),)
        assert result.seconds >= 0
    hub = next(row for row in comparison.table() if row[0] == "hub")
    # Every method but the weighted one puts hub first. In the weighted matrix hub gives
    # its whole vote to its only link, a, which therefore overtakes it.
    assert hub[1] == [1, 1, 2, 1]
    a = next(row for row in comparison.table() if row[0] == "a")
    assert a[1][2] == 1


def test_links_in_counts_incoming_links() -> None:
    result = compare(GRAPH, methods=[METHODS[0]]).results[0]

    assert dict(zip(GRAPH.pages, result.scores.values.tolist(), strict=True))["hub"] == 3


def test_a_new_method_plugs_in() -> None:
    alphabetical = Method(
        "alphabetical",
        "Earlier names rank higher.",
        lambda g, _: Scores(np.array([-ord(page[0]) for page in g.pages], dtype=float)),
    )

    comparison = compare(GRAPH, methods=[alphabetical])

    assert comparison.table()[0][0] == "a"


def test_places_share_ties() -> None:
    assert places(np.array([3.0, 1.0, 3.0, 2.0])) == [1, 4, 1, 3]


def test_kendall_tau_matches_scipy() -> None:
    stats = pytest.importorskip("scipy.stats")
    rng = np.random.default_rng(1)
    first = rng.integers(0, 5, 30).astype(float)  # many ties
    second = first + rng.normal(0, 1.5, 30)

    assert kendall_tau(first, second) == pytest.approx(stats.kendalltau(first, second).statistic)


def test_kendall_tau_extremes() -> None:
    values = np.array([1.0, 2.0, 3.0])

    assert kendall_tau(values, values) == pytest.approx(1)
    assert kendall_tau(values, -values) == pytest.approx(-1)


def test_agreement_lists_every_pair_of_methods() -> None:
    pairs = compare(GRAPH, Settings(smoothing=0.3, max_iterations=500)).agreement()

    assert len(pairs) == 6  # 4 methods
    assert all(-1 <= tau <= 1 for _, _, tau in pairs)
