import pytest

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.graph import GraphStats, click_tree, compute_stats, shortest_levels
from exploreit.models import CrawledPage, Edge, LinkKind

SITE = "https://example.com"


def url(path: str) -> str:
    return path if path.startswith("http") else SITE + path


def page(path: str, depth: int, status: int = 200, content_type: str = "text/html") -> CrawledPage:
    return CrawledPage(url=url(path), depth=depth, status_code=status, content_type=content_type)


def edge(source: str, target: str, kind: LinkKind = LinkKind.ANCHOR) -> Edge:
    return Edge(source=url(source), target=url(target), kind=kind)


#   /      -> /a, /b, https://other.org/x
#   /a     -> /, /a/1, /logo.png, /missing
#   /a/1   -> /b
#   /b     -> (no links)
# /b was found by a depth-first crawl through /a/1, so its recorded depth is 3,
# but it is one click away from the start page.
RESULT = CrawlResult(
    config=CrawlConfig(start_url=SITE),
    pages=[
        page("/", 0),
        page("/a", 1),
        page("/a/1", 2),
        page("/b", 3),
        page("/logo.png", 2, content_type="image/png"),
        page("/missing", 2, status=404),
    ],
    edges=[
        edge("/", "/a"),
        edge("/", "/b"),
        edge("/", "https://other.org/x"),
        edge("/a", "/"),
        edge("/a", "/a/1"),
        edge("/a", "/logo.png", LinkKind.IMAGE),
        edge("/a", "/missing"),
        edge("/a/1", "/b"),
    ],
    failed={},
)


@pytest.fixture
def stats() -> GraphStats:
    return compute_stats(RESULT)


def test_page_counts(stats: GraphStats) -> None:
    assert stats.pages == 6
    assert stats.html_pages == 4
    assert stats.error_pages == 1
    assert stats.unvisited_targets == 1


def test_link_counts(stats: GraphStats) -> None:
    assert stats.links == 8
    assert stats.internal_links == 7
    assert stats.external_links == 1


def test_levels_use_shortest_click_distance(stats: GraphStats) -> None:
    assert shortest_levels(RESULT)[url("/b")] == 1
    assert stats.depth == 2
    assert stats.pages_per_level == {0: 1, 1: 2, 2: 3}


def test_links_on_start_page_and_subpages(stats: GraphStats) -> None:
    assert stats.start_page_links == 3
    assert stats.subpage_links_mean == pytest.approx(5 / 3)
    assert stats.subpage_links_max == 4


def test_dead_ends_and_most_linked(stats: GraphStats) -> None:
    assert stats.dead_ends == 1
    assert stats.most_linked[0] == (url("/b"), 2)


def test_click_tree_keeps_shortest_paths() -> None:
    tree = click_tree(RESULT)

    assert tree[url("/")] == [url("/a"), url("/b")]
    assert tree[url("/a")] == [url("/a/1"), url("/logo.png"), url("/missing")]
    assert tree[url("/a/1")] == []


def test_empty_crawl() -> None:
    result = CrawlResult(
        config=CrawlConfig(start_url=SITE), pages=[], edges=[], failed={url("/"): "refused"}
    )

    stats = compute_stats(result)

    assert stats.depth == 0
    assert stats.pages_per_level == {}
    assert stats.subpage_links_mean == 0.0
    assert stats.failed == 1
    assert click_tree(result) == {}
