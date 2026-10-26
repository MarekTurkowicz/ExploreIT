"""The ExploreIT rank and its parts: word cascade, bridges and trusted links."""

import numpy as np
import pytest

from exploreit.ranking.bridges import betweenness
from exploreit.ranking.graph import LinkGraph
from exploreit.ranking.matrix import adjacency_matrix, trusted_matrix
from exploreit.ranking.methods import METHODS, Settings, compare
from exploreit.ranking.words import word_cascade, words


def graph(*links: str, texts: dict[str, str] | None = None) -> LinkGraph:
    pairs = tuple(tuple(link.split(">")) for link in links)
    pages = tuple(dict.fromkeys(page for pair in pairs for page in pair))
    return LinkGraph(pages, pairs, texts or {})  # type: ignore[arg-type]


def test_words_skip_short_words_numbers_and_stopwords() -> None:
    assert words("The Love of BOOKS, 2026 books and życie!") == {"love", "books", "życie"}


def test_word_cascade_rounds_shrink_by_one() -> None:
    texts = {f"p{i}": " ".join(f"word{chr(97 + j)}" for j in range(i + 1)) for i in range(10)}

    cascade = word_cascade(list(texts), texts, start=4, template_share=1.0)

    assert [len(round_) for round_ in cascade.rounds] == [4, 3, 2, 1]
    assert cascade.rounds[0] == ["worda", "wordb", "wordc", "wordd"]  # on most pages


def test_first_round_decides_and_later_rounds_break_ties() -> None:
    texts = {
        "rich": "alpha beta gamma delta",
        "tied_more": "alpha beta gamma epsilon",
        "tied_less": "alpha beta gamma",
        "poor": "zeta",
        "filler": "alpha beta gamma delta epsilon",
    }

    cascade = word_cascade(list(texts), texts, start=4)
    order = sorted(texts, key=lambda page: -cascade.scores[list(texts).index(page)])

    assert order[0] == "filler"
    assert order.index("rich") < order.index("tied_more") < order.index("tied_less")
    assert order[-1] == "poor"


def test_word_cascade_without_text() -> None:
    cascade = word_cascade(["a", "b"], {}, start=5)

    assert cascade.rounds == []
    assert cascade.scores.tolist() == [0, 0]


def test_betweenness_matches_networkx() -> None:
    nx = pytest.importorskip("networkx")
    g = graph("a>b", "b>c", "c>d", "d>a", "b>e", "e>f", "f>b", "c>a", "e>a")

    ours = betweenness(g)

    reference = nx.betweenness_centrality(nx.DiGraph(list(g.links)), normalized=True)
    assert np.allclose(ours, [reference[page] for page in g.pages])


def test_bridge_page_scores_highest() -> None:
    # Two triangles joined only through "bridge".
    g = graph(
        "a>b", "b>c", "c>a", "c>bridge", "bridge>d", "d>e", "e>f", "f>d", "f>bridge", "bridge>c"
    )

    scores = dict(zip(g.pages, betweenness(g), strict=True))

    assert max(scores, key=scores.__getitem__) == "bridge"


def share_of(g: LinkGraph, source: str, target: str) -> float:
    return float(trusted_matrix(g)[g.pages.index(source), g.pages.index(target)])


def test_trusted_matrix_rows_still_share_one_vote() -> None:
    g = graph("a>menu", "b>menu", "c>menu", "a>b", "b>a", "c>a", "menu>c")

    assert np.allclose(trusted_matrix(g).sum(axis=1), 1)


def test_mutual_link_counts_less() -> None:
    one_way = graph("a>b", "a>c", "b>d", "c>d", "d>a")
    both_ways = graph("a>b", "a>c", "b>d", "c>d", "d>a", "b>a")

    assert share_of(both_ways, "a", "b") < share_of(one_way, "a", "b")


def test_menu_link_counts_less() -> None:
    # Every page links to "menu"; "a" also links to "x", which only it links to.
    g = graph("a>menu", "b>menu", "c>menu", "x>menu", "a>x", "menu>b", "b>c", "c>a")

    assert share_of(g, "a", "menu") < share_of(g, "a", "x")
    assert adjacency_matrix(g, weighted=True)[g.pages.index("a"), g.pages.index("menu")] == 0.5


def test_explore_rank_combines_its_parts() -> None:
    texts = {"hub": "love life books", "a": "love life", "b": "love", "c": "spam spam", "d": ""}
    g = graph("a>hub", "b>hub", "c>hub", "hub>a", "a>b", "b>c", "c>d", "d>c", texts=texts)

    comparison = compare(g, Settings(cascade_words=3))
    names = [method.name for method in METHODS]

    explore = comparison.results[names.index("ExploreIT rank")].scores.values
    assert explore.max() == pytest.approx(explore[g.pages.index("hub")])
    assert explore.min() >= 0 and explore.max() <= 1


def test_explore_rank_without_content_uses_links_and_bridges() -> None:
    g = graph("a>b", "b>c", "c>a", "c>d", "d>a")

    result = compare(g, methods=[METHODS[-1]]).results[0]

    assert result.scores.values.max() > 0


def test_template_words_on_every_page_are_skipped() -> None:
    topics = ["apple", "berry", "cherry"]
    texts = {f"p{i}": f"footer made zyte {topics[i % 3]}" for i in range(10)}

    cascade = word_cascade(list(texts), texts, start=3)

    assert cascade.rounds[0] == ["apple", "berry", "cherry"]  # footer words are gone
