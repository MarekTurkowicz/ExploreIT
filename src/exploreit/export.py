"""Link graph export: a networkx graph, GEXF for Gephi and an interactive HTML page."""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING

from exploreit.crawler import CrawlResult
from exploreit.graph import shortest_levels

if TYPE_CHECKING:
    import networkx as nx

# Pinned so the page keeps working the same way; loaded from a CDN when the page opens.
VIS_NETWORK = "https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"
LEVEL_COLOURS = ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4"]
ERROR_COLOUR = "#d03b3b"
UNVISITED_COLOUR = "#c3c2b7"
EDGE_COLOURS = {"anchor": "#898781", "image": "#1baf7a", "resource": "#eda100"}

HTML_PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>$title</title>
<script src="$vis_network"></script>
<style>
  html, body { margin: 0; height: 100%; font: 13px system-ui, sans-serif; background: #fcfcfb; }
  #graph { position: absolute; inset: 0; }
  #info { position: absolute; top: 8px; left: 8px; z-index: 1; padding: 6px 10px;
          background: #ffffffe6; border: 1px solid #e1e0d9; border-radius: 6px; }
</style>
</head>
<body>
<div id="info">$title · $pages pages · $links links · double-click a page to open it</div>
<div id="graph"></div>
<script>
const data = $data;
const network = new vis.Network(
  document.getElementById("graph"),
  { nodes: new vis.DataSet(data.nodes), edges: new vis.DataSet(data.edges) },
  {
    nodes: { shape: "dot", font: { size: 11, color: "#52514e" } },
    edges: { arrows: { to: { scaleFactor: 0.4 } }, width: 0.6, smooth: false },
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 300 } },
    interaction: { hover: true, tooltipDelay: 80 },
  },
);
network.once("stabilizationIterationsDone", () => network.setOptions({ physics: false }));
network.on("doubleClick", (event) => {
  if (event.nodes.length) window.open(event.nodes[0], "_blank");
});
</script>
</body>
</html>
""")


def build_graph(result: CrawlResult, visited_only: bool = True) -> nx.DiGraph[str]:
    """Build a directed graph of pages and links.

    Nodes carry `level`, `status_code`, `content_type` and `visited`; edges carry `kind`.
    With visited_only, links to pages that were never fetched are left out.
    """
    import networkx as nx  # imported here: it is slow to load and only needed now

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
        if edge.source == edge.target:
            continue  # older crawls kept links from a page to itself
        if edge.target not in graph:
            if visited_only:
                continue
            graph.add_node(edge.target, level=-1, status_code=0, content_type="", visited=False)
        graph.add_edge(edge.source, edge.target, kind=edge.kind.value)
    return graph


def write_gexf(result: CrawlResult, path: Path) -> None:
    """Save the full link graph, including unvisited targets, for Gephi."""
    import networkx as nx

    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(build_graph(result, visited_only=False), path)


def write_html(result: CrawlResult, path: Path, visited_only: bool = True) -> None:
    """Save an interactive HTML view of the link graph (vis-network, needs internet)."""
    graph = build_graph(result, visited_only=visited_only)
    in_degree = Counter(target for _, target in graph.edges)
    nodes = [
        {
            "id": url,
            "label": _label(url, result.config.start_url),
            "title": _tooltip(url, data),
            "color": node_colour(data),
            "size": 6 + 2 * min(in_degree[url], 15),
        }
        for url, data in graph.nodes(data=True)
    ]
    edges = [
        {"from": source, "to": target, "color": EDGE_COLOURS[data["kind"]]}
        for source, target, data in graph.edges(data=True)
    ]
    # "</" inside a <script> block would end it early, so escape it in the JSON.
    payload = json.dumps({"nodes": nodes, "edges": edges}).replace("</", "<\\/")
    page = HTML_PAGE.substitute(
        title=html.escape(result.config.start_url),
        vis_network=VIS_NETWORK,
        pages=graph.number_of_nodes(),
        links=graph.number_of_edges(),
        data=payload,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


def _label(url: str, start_url: str) -> str:
    return url.removeprefix(start_url.rstrip("/")) or "/"


def node_colour(data: dict[str, object]) -> str:
    """Colour of a page: its level for visited pages, red for errors, grey if not visited."""
    level, status = data["level"], data["status_code"]
    if not data["visited"] or not isinstance(level, int) or not isinstance(status, int):
        return UNVISITED_COLOUR
    if status >= 400:
        return ERROR_COLOUR
    return LEVEL_COLOURS[min(max(level, 0), len(LEVEL_COLOURS) - 1)]


def _tooltip(url: str, data: dict[str, object]) -> str:
    if not data["visited"]:
        return f"{url}\nnot visited"
    return f"{url}\nlevel {data['level']} · {data['status_code']} · {data['content_type']}"
