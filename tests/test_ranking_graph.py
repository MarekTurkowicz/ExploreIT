from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.models import CrawledPage, Edge, LinkKind
from exploreit.ranking.graph import LinkGraph, check_requirements, link_graph, shortest_cycle

START = "https://example.com/"


def graph(*links: str) -> LinkGraph:
    """Build a graph from "a>b" strings."""
    pairs = tuple(tuple(link.split(">")) for link in links)
    pages = tuple(dict.fromkeys(page for pair in pairs for page in pair))
    return LinkGraph(pages, pairs)  # type: ignore[arg-type]


def page(path: str, kind: str = "text/html", status: int = 200) -> CrawledPage:
    return CrawledPage(url=START + path, depth=0, status_code=status, content_type=kind)


def edge(source: str, target: str) -> Edge:
    return Edge(
        source=START + source,
        target=target if "://" in target else START + target,
        kind=LinkKind.ANCHOR,
    )


def test_graph_keeps_visited_html_pages_and_links_between_them() -> None:
    result = CrawlResult(
        config=CrawlConfig(start_url=START),
        pages=[page(""), page("a"), page("logo.png", kind="image/png"), page("gone", status=404)],
        edges=[
            edge("", "a"),
            edge("", "a"),  # the same link twice counts once
            edge("a", "a"),  # a page does not vote for itself
            edge("a", ""),
            edge("a", "logo.png"),  # not an HTML page
            edge("a", "https://other.org/"),  # not visited
        ],
        failed={},
    )

    ranked = link_graph(result)

    assert ranked.pages == (START, f"{START}a")
    assert ranked.links == ((START, f"{START}a"), (f"{START}a", START))
    assert len(link_graph(result, html_only=False).pages) == 4


def test_shortest_cycle_of_three_or_more_pages() -> None:
    assert shortest_cycle(graph("a>b", "b>c", "c>a")) == ["a", "b", "c"]
    # A square with a two-way diagonal: the shortest 3+ cycle uses the diagonal once.
    assert len(shortest_cycle(graph("a>b", "b>c", "c>d", "d>a", "a>c", "c>a"))) == 3


def test_two_page_cycles_do_not_count() -> None:
    assert shortest_cycle(graph("a>b", "b>a", "b>c", "c>b")) == []


def test_cycle_hidden_behind_a_shortcut_is_found() -> None:
    # x -> y is a shortcut: a depth-first search reaching y first sees only x <-> y,
    # but x -> p -> y -> x is a real three-page cycle.
    assert sorted(shortest_cycle(graph("x>y", "y>x", "x>p", "p>y"))) == ["p", "x", "y"]


def test_shortest_cycle_is_preferred() -> None:
    cycle = shortest_cycle(graph("a>b", "b>c", "c>d", "d>a", "b>e", "e>f", "f>b"))

    assert len(cycle) == 3
    assert set(cycle) == {"b", "e", "f"}


def test_requirements() -> None:
    # 20 pages in a ring (a cycle of 20) plus extra links into p0, p1 and p2.
    ring = [f"p{i}>p{(i + 1) % 20}" for i in range(20)]
    extra = ["p5>p0", "p6>p0", "p7>p1", "p8>p2"]

    checks = {check.description: check for check in check_requirements(graph(*ring, *extra))}

    assert all(check.met for check in checks.values())
    assert checks["pages (at least 20)"].actual == 20
    assert checks["pages with at least 2 incoming links"].actual == 3
    assert checks["pages with at least 3 incoming links"].actual == 1


def test_requirements_not_met() -> None:
    checks = check_requirements(graph("a>b", "b>a"))

    assert [check.met for check in checks] == [False, False, False, False]
    assert checks[-1].actual == 0
