from pathlib import Path

import networkx as nx

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.export import build_graph, write_gexf, write_html
from exploreit.models import CrawledPage, Edge, LinkKind

SITE = "https://example.com"


def page(path: str, status: int = 200) -> CrawledPage:
    return CrawledPage(url=SITE + path, depth=0, status_code=status, content_type="text/html")


RESULT = CrawlResult(
    config=CrawlConfig(start_url=SITE),
    pages=[page("/"), page("/a"), page("/café", status=404)],
    edges=[
        Edge(source=f"{SITE}/", target=f"{SITE}/a", kind=LinkKind.ANCHOR),
        Edge(source=f"{SITE}/", target=f"{SITE}/café", kind=LinkKind.ANCHOR),
        Edge(source=f"{SITE}/a", target=f"{SITE}/", kind=LinkKind.ANCHOR),
        Edge(source=f"{SITE}/a", target="https://other.org/", kind=LinkKind.ANCHOR),
        Edge(source=f"{SITE}/a", target=f"{SITE}/logo.png", kind=LinkKind.IMAGE),
    ],
    failed={},
)


def test_graph_of_visited_pages() -> None:
    graph = build_graph(RESULT)

    assert set(graph.nodes) == {f"{SITE}/", f"{SITE}/a", f"{SITE}/café"}
    assert graph.number_of_edges() == 3
    assert graph.nodes[f"{SITE}/a"]["level"] == 1
    assert graph.edges[f"{SITE}/a", f"{SITE}/"]["kind"] == "anchor"


def test_graph_with_unvisited_targets() -> None:
    graph = build_graph(RESULT, visited_only=False)

    assert graph.number_of_nodes() == 5
    assert graph.number_of_edges() == 5
    assert not graph.nodes["https://other.org/"]["visited"]


def test_gexf_can_be_read_back(tmp_path: Path) -> None:
    path = tmp_path / "graph.gexf"

    write_gexf(RESULT, path)

    graph = nx.read_gexf(path)
    assert graph.number_of_nodes() == 5
    assert graph.number_of_edges() == 5


def test_html_is_self_contained(tmp_path: Path) -> None:
    path = tmp_path / "graph.html"

    write_html(RESULT, path)

    html = path.read_text(encoding="utf-8")
    assert "vis.Network" in html
    assert f"{SITE}/café" in html
    assert not (tmp_path / "lib").exists()
