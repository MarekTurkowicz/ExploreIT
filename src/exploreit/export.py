"""Link graph export: interactive HTML (pyvis) and GEXF for Gephi."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import networkx as nx
from pyvis.network import Network

from exploreit.crawler import CrawlResult
from exploreit.graph import shortest_levels

LEVEL_COLOURS = ["#e4572e", "#f3a712", "#29335c", "#669bbc", "#a8c686", "#8e7dbe"]
ERROR_COLOUR = "#d00000"
UNVISITED_COLOUR = "#c0c0c0"
EDGE_COLOURS = {"anchor": "#9aa5b1", "image": "#2a9d8f", "resource": "#e9c46a"}


def build_graph(result: CrawlResult, visited_only: bool = True) -> nx.DiGraph[str]:
    """Build a directed graph of pages and links.

    Nodes carry `level`, `status_code`, `content_type` and `visited`; edges carry `kind`.
    With visited_only, links to pages that were never fetched are left out.
    """
    levels = shortest_levels(result)
    graph: nx.DiGraph[str] = nx.DiGraph()
    for page in result.pages:
        graph.add_node(
            page.url,
            level=levels.get(page.url, -1),
            status_code=page.status_code,
            content_type=page.content_type,
            visited=True,
        )
    for edge in result.edges:
        if edge.target not in graph:
            if visited_only:
                continue
            graph.add_node(edge.target, level=-1, status_code=0, content_type="", visited=False)
        graph.add_edge(edge.source, edge.target, kind=edge.kind.value)
    return graph


def write_gexf(result: CrawlResult, path: Path) -> None:
    """Save the full link graph, including unvisited targets, for Gephi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(build_graph(result, visited_only=False), path)


def write_html(result: CrawlResult, path: Path, visited_only: bool = True) -> None:
    """Save an interactive, self-contained HTML view of the link graph."""
    graph = build_graph(result, visited_only=visited_only)
    in_degree = Counter(target for _, target in graph.edges)
    start_host = urlsplit(result.config.start_url).netloc

    network = Network(height="95vh", directed=True, select_menu=True, cdn_resources="in_line")
    for url, data in graph.nodes(data=True):
        parts = urlsplit(url)
        label = parts.path if parts.netloc == start_host else parts.netloc + parts.path
        network.add_node(
            url,
            label=label,
            title=_tooltip(url, data),
            color=_node_colour(data),
            size=10 + 3 * min(in_degree[url], 10),
        )
    for source, target, data in graph.edges(data=True):
        network.add_edge(source, target, color=EDGE_COLOURS[data["kind"]])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(network.generate_html(), encoding="utf-8")


def _node_colour(data: dict[str, Any]) -> str:
    if not data["visited"]:
        return UNVISITED_COLOUR
    if data["status_code"] >= 400:
        return ERROR_COLOUR
    level: int = data["level"]
    return LEVEL_COLOURS[min(level, len(LEVEL_COLOURS) - 1)]


def _tooltip(url: str, data: dict[str, Any]) -> str:
    if not data["visited"]:
        return f"{url}\nnot visited"
    return f"{url}\nlevel {data['level']} · {data['status_code']} · {data['content_type']}"
