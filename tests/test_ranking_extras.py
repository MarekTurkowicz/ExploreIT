"""Duplicate pages, where links stand on a page, and ranking for a search query."""

import numpy as np
import pytest
from scipy.stats import kendalltau

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.models import CrawledPage, Edge, LinkKind, PageContent, Region
from exploreit.parser import LinkMode, extract_links
from exploreit.ranking.graph import LinkGraph, duplicates, link_graph
from exploreit.ranking.matrix import trusted_matrix
from exploreit.ranking.methods import (
    METHODS,
    QUERY_METHOD,
    Settings,
    compare,
    kendall_tau,
    kendall_taus,
    methods_for,
)
from exploreit.ranking.query import query_match, query_words

SITE = "https://s.com/"


# Where a link stands


def regions(html: str) -> dict[str, Region]:
    return {
        link.url.removeprefix(SITE): link.region for link in extract_links(html, SITE, LinkMode.ALL)
    }


def test_link_region_comes_from_enclosing_elements() -> None:
    html = """
        <header><a href="/h">h</a></header>
        <nav><a href="/n">n</a></nav>
        <div class="main-menu"><a href="/m">m</a></div>
        <div role="navigation"><a href="/r">r</a></div>
        <article><p><a href="/a">a</a></p></article>
        <div class="canvas"><a href="/c">c</a></div>
        <footer><nav><a href="/f">f</a></nav></footer>
        <div id="site-footer"><a href="/g">g</a></div>
    """
    assert regions(html) == {
        "h": Region.NAVIGATION,
        "n": Region.NAVIGATION,
        "m": Region.NAVIGATION,
        "r": Region.NAVIGATION,
        "a": Region.CONTENT,
        "c": Region.CONTENT,  # "canvas" contains "nav" but is not navigation
        "f": Region.FOOTER,  # a menu inside a footer is still the footer
        "g": Region.FOOTER,
    }


def test_repeated_link_keeps_its_most_prominent_place() -> None:
    html = '<nav><a href="/x">x</a></nav><main><a href="/x">x again</a></main>'

    assert regions(html) == {"x": Region.CONTENT}


def test_trusted_matrix_counts_menu_and_footer_links_less() -> None:
    pages = ("a", "b", "c", "d")
    links = (("a", "b"), ("a", "c"), ("a", "d"))
    graph = LinkGraph(
        pages, links, regions={("a", "c"): Region.NAVIGATION, ("a", "d"): Region.FOOTER}
    )

    row = trusted_matrix(graph)[0]

    assert row.sum() == pytest.approx(1)
    assert row[1] == pytest.approx(2 * row[2]) == pytest.approx(4 * row[3])


# Duplicate pages


def test_duplicates_merge_scheme_www_and_same_text() -> None:
    pages = [
        "http://s.com/",
        "https://s.com/",
        "https://www.s.com/",
        "https://s.com/page/1/",
        "https://s.com/other",
    ]
    texts = {"https://s.com/": "front page", "https://s.com/page/1/": "front page"}

    assert duplicates(pages, texts) == {
        "http://s.com/": "https://s.com/",
        "https://www.s.com/": "https://s.com/",
        "https://s.com/page/1/": "https://s.com/",
    }


def test_link_graph_merges_duplicates_and_their_links() -> None:
    def page(url: str) -> CrawledPage:
        return CrawledPage(url=url, depth=0, status_code=200, content_type="text/html")

    def edge(source: str, target: str, region: Region = Region.CONTENT) -> Edge:
        return Edge(source=source, target=target, kind=LinkKind.ANCHOR, region=region)

    result = CrawlResult(
        config=CrawlConfig(start_url=SITE),
        pages=[page("http://s.com/"), page(SITE), page(SITE + "a")],
        edges=[
            edge("http://s.com/", SITE + "a", Region.FOOTER),
            edge(SITE, SITE + "a"),  # the same link from the other copy, more prominent
            edge("http://s.com/", SITE),  # becomes a link to itself
            edge(SITE + "a", "http://s.com/", Region.NAVIGATION),
        ],
        failed={},
        contents=[PageContent(url="http://s.com/", title="home")],
    )

    graph = link_graph(result, merge_duplicates=True)

    assert graph.pages == (SITE, SITE + "a")
    assert graph.merged == {"http://s.com/": SITE}
    assert graph.links == ((SITE, SITE + "a"), (SITE + "a", SITE))
    assert graph.regions[SITE, SITE + "a"] is Region.CONTENT
    assert graph.texts[SITE] == "home   "  # the copy's text moves to the kept page
    assert len(link_graph(result).pages) == 3  # merging is a choice


# Search query


TEXTS = {
    "a": "python python programming tutorial",
    "b": "python snakes in the zoo",
    "c": "cooking pasta recipes",
}


def test_query_words_drop_stopwords_and_repeats() -> None:
    assert query_words("The Python and python, tutorial") == ["python", "tutorial"]


def test_query_match_prefers_frequent_and_rare_words() -> None:
    scores = query_match(list(TEXTS), TEXTS, "python tutorial")

    assert scores[0] > scores[1] > 0
    assert scores[2] == 0


def test_query_word_matches_longer_words() -> None:
    assert query_match(list(TEXTS), TEXTS, "program")[0] > 0


def test_query_method_joins_only_with_a_query() -> None:
    assert methods_for(Settings()) == METHODS
    with_query = methods_for(Settings(query="python"))
    assert with_query[-2] is QUERY_METHOD
    assert with_query[-1] is METHODS[-1]


def test_explore_rank_with_query_keeps_only_matching_pages() -> None:
    links = (("a", "b"), ("b", "c"), ("c", "a"), ("a", "c"), ("b", "a"))
    graph = LinkGraph(("a", "b", "c"), links, TEXTS)

    result = compare(graph, Settings(query="python")).results[-1]

    assert result.method.name == "ExploreIT rank"
    assert result.scores.values[2] == 0
    assert result.scores.values[0] > 0
    assert result.scores.values[1] > 0


# Kendall tau


def test_kendall_tau_matches_scipy_with_ties() -> None:
    generator = np.random.default_rng(1)
    first = generator.integers(0, 5, 600).astype(float)  # more pages than one block
    second = first + generator.integers(0, 3, 600)

    assert kendall_tau(first, second) == pytest.approx(kendalltau(first, second).statistic)


def test_kendall_taus_is_symmetric_and_nan_without_order() -> None:
    values = np.array([3.0, 1.0, 2.0])
    taus = kendall_taus([values, -values, np.ones(3)])

    assert taus[0, 1] == taus[1, 0] == pytest.approx(-1)
    assert np.isnan(taus[0, 2])
