"""What the interactive graph shows: pages as nodes, their colour, size and position.

Kept free of Tk so it can be tested and reused without a window.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from math import sqrt
from urllib.parse import urlsplit

from exploreit.crawler import CrawlResult
from exploreit.export import LEVEL_COLOURS, build_graph

UNVISITED = "#a8a69f"
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
STATUS_COLOURS = {"2xx": "#0ca30c", "3xx": "#2a78d6", "4xx": "#ec835a", "5xx": "#d03b3b"}
ERROR = "#d03b3b"


class Layout(StrEnum):
    LEVELS = "by level (tree)"
    SPRING = "spring (clusters)"
    KAMADA_KAWAI = "kamada-kawai (even)"
    SHELLS = "rings by level"
    CIRCLE = "circle"


class ColourBy(StrEnum):
    LEVEL = "level"
    STATUS = "HTTP status"
    TYPE = "content type"
    HOST = "host"


class SizeBy(StrEnum):
    LINKS_IN = "links in"
    LINKS_OUT = "links out"
    EQUAL = "equal"


@dataclass(frozen=True)
class Node:
    """A page in the graph, with everything the tooltip and the styling need."""

    url: str
    level: int
    status_code: int
    content_type: str
    visited: bool
    links_in: int
    links_out: int

    @property
    def host(self) -> str:
        return urlsplit(self.url).netloc


@dataclass(frozen=True)
class Category:
    """A colour group shown in the legend, e.g. "level 1" or "4xx"."""

    label: str
    colour: str


@dataclass(frozen=True)
class GraphData:
    nodes: dict[str, Node]
    edges: list[tuple[str, str]]


def graph_data(result: CrawlResult, visited_only: bool = True) -> GraphData:
    graph = build_graph(result, visited_only=visited_only)
    nodes = {
        url: Node(
            url=url,
            level=data["level"],
            status_code=data["status_code"],
            content_type=data["content_type"],
            visited=data["visited"],
            links_in=graph.in_degree(url),
            links_out=graph.out_degree(url),
        )
        for url, data in graph.nodes(data=True)
    }
    return GraphData(nodes, list(graph.edges))


def positions(data: GraphData, layout: Layout) -> dict[str, tuple[float, float]]:
    """Place every page inside the unit square, (0, 0) top left, y growing downwards."""
    if not data.nodes:
        return {}
    rows = _rows(data)
    if layout is Layout.LEVELS:
        return _columns_by_level(data, rows)
    import networkx as nx  # slow to load, so only when a layout is computed

    graph: nx.Graph[str] = nx.Graph()
    graph.add_nodes_from(data.nodes)
    graph.add_edges_from(data.edges)
    match layout:
        case Layout.SPRING:
            raw = nx.spring_layout(graph, seed=1)
        case Layout.KAMADA_KAWAI:
            raw = nx.kamada_kawai_layout(graph)
        case Layout.SHELLS:
            shells = [
                [url for url, row in rows.items() if row == r] for r in sorted(set(rows.values()))
            ]
            raw = nx.shell_layout(graph, nlist=shells)
        case _:
            raw = nx.circular_layout(graph)
    return _normalise({url: (float(x), float(y)) for url, (x, y) in raw.items()})


def category(node: Node, colour_by: ColourBy, hosts: list[str]) -> Category:
    """The colour group of a page. `hosts` lists the most common hosts first."""
    if not node.visited and colour_by is not ColourBy.HOST:
        return Category("not visited", UNVISITED)
    match colour_by:
        case ColourBy.LEVEL:
            if node.status_code >= 400:
                return Category("error page", ERROR)
            return Category(f"level {node.level}", LEVEL_COLOURS[min(node.level, 5)])
        case ColourBy.STATUS:
            group = f"{node.status_code // 100}xx"
            return Category(group, STATUS_COLOURS.get(group, UNVISITED))
        case ColourBy.TYPE:
            if node.content_type in ("text/html", "application/xhtml+xml"):
                return Category("HTML page", CATEGORICAL[0])
            if node.content_type.startswith("image/"):
                return Category("image", CATEGORICAL[2])
            return Category("other file", CATEGORICAL[3])
        case ColourBy.HOST:
            rank = hosts.index(node.host) if node.host in hosts else len(CATEGORICAL)
            if rank >= len(CATEGORICAL):
                return Category("other hosts", UNVISITED)
            return Category(node.host, CATEGORICAL[rank])


def hosts_by_frequency(data: GraphData) -> list[str]:
    return [host for host, _ in Counter(node.host for node in data.nodes.values()).most_common()]


def legend(data: GraphData, colour_by: ColourBy) -> list[tuple[Category, int]]:
    """Every colour group with the number of pages in it, in a natural order."""
    hosts = hosts_by_frequency(data)
    counts = Counter(category(node, colour_by, hosts) for node in data.nodes.values())
    return sorted(counts.items(), key=lambda item: _legend_order(item[0], colour_by, hosts))


def radius(node: Node, size_by: SizeBy, scale: float = 1.0) -> float:
    """Node radius in pixels: grows with the square root, so hubs do not swamp the view."""
    links = {SizeBy.LINKS_IN: node.links_in, SizeBy.LINKS_OUT: node.links_out}.get(size_by, 0)
    return (5 + 2.2 * sqrt(links)) * scale


def short_label(url: str, start_url: str) -> str:
    """The path for pages under the start page's address, the whole URL otherwise."""
    parts, start = urlsplit(url), urlsplit(start_url)
    if (parts.scheme, parts.netloc) != (start.scheme, start.netloc):
        return url
    return parts.path + (f"?{parts.query}" if parts.query else "")


def _rows(data: GraphData) -> dict[str, int]:
    """Level of every page; linked pages that were not visited go one row below the deepest."""
    deepest = max((node.level for node in data.nodes.values()), default=0)
    return {url: node.level if node.level >= 0 else deepest + 1 for url, node in data.nodes.items()}


def _columns_by_level(data: GraphData, rows: dict[str, int]) -> dict[str, tuple[float, float]]:
    """One column per level, each spread over the full height.

    Within a column, pages are ordered by the average height of the pages linking to them
    from earlier columns, which keeps lines between neighbouring columns from crossing.
    """
    parents: dict[str, list[str]] = {url: [] for url in data.nodes}
    for source, target in data.edges:
        if rows[source] < rows[target]:
            parents[target].append(source)

    deepest = max(rows.values())
    placed: dict[str, tuple[float, float]] = {}
    for row in range(deepest + 1):
        column = [url for url in data.nodes if rows[url] == row]

        def height(url: str) -> float:
            above = [placed[parent][1] for parent in parents[url] if parent in placed]
            return sum(above) / len(above) if above else 0.0

        column.sort(key=height)
        x = row / deepest if deepest else 0.5
        for index, url in enumerate(column):
            placed[url] = (x, (index + 0.5) / len(column))
    return placed


def _normalise(raw: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    xs = [x for x, _ in raw.values()]
    ys = [y for _, y in raw.values()]
    width = (max(xs) - min(xs)) or 1.0
    height = (max(ys) - min(ys)) or 1.0
    # A single column or row sits in the middle instead of on the edge.
    return {
        url: (
            (x - min(xs)) / width if max(xs) > min(xs) else 0.5,
            (max(ys) - y) / height if max(ys) > min(ys) else 0.5,
        )
        for url, (x, y) in raw.items()
    }


def _legend_order(group: Category, colour_by: ColourBy, hosts: list[str]) -> tuple[int, str]:
    if group.label in ("error page", "not visited", "other hosts"):
        return (10_000, group.label)
    if colour_by is ColourBy.LEVEL and group.label.startswith("level "):
        return (int(group.label.removeprefix("level ")), "")
    if colour_by is ColourBy.HOST:
        return (hosts.index(group.label), "")
    return (0, group.label)
