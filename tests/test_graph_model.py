import pytest

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.gui.graph_model import (
    ColourBy,
    Layout,
    SizeBy,
    category,
    graph_data,
    hosts_by_frequency,
    legend,
    positions,
    radius,
    short_label,
)
from exploreit.models import CrawledPage, Edge, LinkKind

START = "https://example.com/"


def page(path: str, depth: int, status: int = 200, kind: str = "text/html") -> CrawledPage:
    return CrawledPage(url=START + path, depth=depth, status_code=status, content_type=kind)


RESULT = CrawlResult(
    config=CrawlConfig(start_url=START),
    pages=[
        page("", 0),
        page("a", 1),
        page("b", 1, status=404),
        page("logo.png", 2, kind="image/png"),
    ],
    edges=[
        Edge(source=START, target=f"{START}a", kind=LinkKind.ANCHOR),
        Edge(source=START, target=f"{START}b", kind=LinkKind.ANCHOR),
        Edge(source=f"{START}a", target=f"{START}logo.png", kind=LinkKind.IMAGE),
        Edge(source=f"{START}a", target="https://other.org/", kind=LinkKind.ANCHOR),
    ],
    failed={},
)


def test_nodes_know_their_links() -> None:
    data = graph_data(RESULT)

    assert len(data.nodes) == 4
    assert data.nodes[START].links_out == 2
    assert data.nodes[f"{START}a"].links_in == 1
    assert "https://other.org/" in graph_data(RESULT, visited_only=False).nodes


@pytest.mark.parametrize("layout", list(Layout))
def test_every_layout_fits_the_unit_square(layout: Layout) -> None:
    placed = positions(graph_data(RESULT, visited_only=False), layout)

    assert len(placed) == 5
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in placed.values())


def test_levels_layout_gives_every_level_a_column() -> None:
    placed = positions(graph_data(RESULT), Layout.LEVELS)

    assert placed[START][0] < placed[f"{START}a"][0] == placed[f"{START}b"][0]
    assert placed[f"{START}a"][0] < placed[f"{START}logo.png"][0]
    assert placed[f"{START}a"][1] != placed[f"{START}b"][1]


def test_colour_groups() -> None:
    data = graph_data(RESULT, visited_only=False)
    hosts = hosts_by_frequency(data)
    group = {url: category(node, ColourBy.LEVEL, hosts).label for url, node in data.nodes.items()}

    assert group[START] == "level 0"
    assert group[f"{START}b"] == "error page"
    assert group["https://other.org/"] == "not visited"
    assert category(data.nodes[f"{START}logo.png"], ColourBy.TYPE, hosts).label == "image"
    assert category(data.nodes[f"{START}b"], ColourBy.STATUS, hosts).label == "4xx"
    assert category(data.nodes["https://other.org/"], ColourBy.HOST, hosts).label == "other.org"


def test_legend_counts_pages_in_order() -> None:
    rows = [(group.label, count) for group, count in legend(graph_data(RESULT), ColourBy.LEVEL)]

    assert rows == [("level 0", 1), ("level 1", 1), ("level 2", 1), ("error page", 1)]


def test_radius_grows_with_links() -> None:
    data = graph_data(RESULT)

    assert radius(data.nodes[START], SizeBy.LINKS_OUT) > radius(
        data.nodes[f"{START}b"], SizeBy.LINKS_OUT
    )
    assert radius(data.nodes[START], SizeBy.EQUAL) == radius(data.nodes[f"{START}b"], SizeBy.EQUAL)


def test_short_label() -> None:
    assert short_label(f"{START}a?x=1", START) == "/a?x=1"
    assert short_label("http://example.com/a", START) == "http://example.com/a"
