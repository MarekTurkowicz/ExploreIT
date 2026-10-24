"""Charts of crawl results. Each function returns a matplotlib Figure that can be saved
as PNG or shown inside the application window."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from exploreit.crawler import CrawlResult
from exploreit.export import build_graph, node_colour
from exploreit.graph import compute_stats

SERIES = ["#2a78d6", "#eb6834"]  # categorical slots 1-2: blue, orange
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
LABELLED_NODES_LIMIT = 60
ARROWS_EDGES_LIMIT = 400  # arrow heads are slow to draw on big graphs

COMPARED_METRICS = {
    "pages": "Pages visited",
    "links": "Links found",
    "depth": "Graph depth",
    "subpage_links_mean": "Mean links per subpage",
}

Layout = Literal["levels", "spring"]


@dataclass(frozen=True)
class GraphDrawing:
    """A drawn link graph and where each page ended up, for hover and click handling."""

    figure: Figure
    axes: Axes
    urls: list[str]
    positions: np.ndarray


def levels_figure(result: CrawlResult) -> Figure:
    """Bar chart of how many pages sit on each level of the graph."""
    levels = compute_stats(result).pages_per_level
    figure, ax = _figure(width=6, height=3.6)
    bars = ax.bar(
        [str(level) for level in levels], list(levels.values()), color=SERIES[0], width=0.6
    )
    ax.bar_label(bars, padding=3, color=INK_SECONDARY, fontsize=9)
    _style(ax, grid_axis="y")
    ax.set_xlabel("Level (clicks from the start page)")
    ax.set_ylabel("Pages")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Pages per level", loc="left", fontsize=11, color=INK)
    return figure


def out_links_figure(result: CrawlResult) -> Figure:
    """Histogram of the number of outgoing links on visited HTML pages."""
    out_links = Counter(edge.source for edge in result.edges)
    counts = [out_links[page.url] for page in result.pages if page.is_html]
    figure, ax = _figure(width=6, height=3.6)
    ax.hist(counts, bins=min(20, max(1, len(set(counts)))), color=SERIES[0], edgecolor=SURFACE)
    _style(ax, grid_axis="y")
    ax.set_xlabel("Links on the page")
    ax.set_ylabel("Pages")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("Outgoing links per page", loc="left", fontsize=11, color=INK)
    return figure


def comparison_figure(table: pd.DataFrame) -> Figure:
    """Small multiples comparing crawl statistics across parameter combinations."""
    table = table.assign(setup=table["scope"] + " · " + table["link_mode"])
    setups = list(dict.fromkeys(table["setup"]))
    strategies = list(dict.fromkeys(table["strategy"]))
    height = 0.8 / len(strategies)

    figure = Figure(figsize=(12, 1.2 + 0.42 * len(setups)), facecolor=SURFACE, layout="constrained")
    axes = figure.subplots(1, len(COMPARED_METRICS), sharey=True)
    for ax, (metric, label) in zip(axes, COMPARED_METRICS.items(), strict=True):
        for index, strategy in enumerate(strategies):
            rows = table[table["strategy"] == strategy].set_index("setup").reindex(setups)
            positions = [row + index * height for row in range(len(setups))]
            ax.barh(
                positions, rows[metric], height=height * 0.9, color=SERIES[index], label=strategy
            )
        _style(ax, grid_axis="x")
        ax.set_title(label, loc="left", fontsize=10, color=INK)

    axes[0].set_yticks([row + height * (len(strategies) - 1) / 2 for row in range(len(setups))])
    axes[0].set_yticklabels(setups)
    axes[0].invert_yaxis()
    figure.legend(*axes[0].get_legend_handles_labels(), loc="outside upper right", frameon=False)
    figure.suptitle("Crawl parameters compared", x=0.01, ha="left", fontsize=12, color=INK)
    return figure


def graph_figure(
    result: CrawlResult, layout: Layout = "levels", visited_only: bool = True
) -> GraphDrawing:
    """Draw the link graph: colour shows the level, size the number of incoming links.

    The "levels" layout reads like a site map: the start page on the left and every
    level in its own column. The "spring" layout lets linked pages pull together.
    """
    graph = build_graph(result, visited_only=visited_only)
    figure = Figure(figsize=(10, 7), facecolor=SURFACE, layout="constrained")
    ax = figure.subplots()
    ax.set_facecolor(SURFACE)
    ax.set_axis_off()
    urls = list(graph.nodes)
    if not urls:
        ax.text(0.5, 0.5, "No pages to draw", ha="center", color=MUTED, transform=ax.transAxes)
        return GraphDrawing(figure, ax, [], np.empty((0, 2)))

    positions = _layout(graph, layout)
    in_degree = Counter(target for _, target in graph.edges)
    if graph.number_of_edges() <= ARROWS_EDGES_LIMIT:
        nx.draw_networkx_edges(
            graph, positions, ax=ax, edge_color=MUTED, alpha=0.35, width=0.6, arrowsize=6
        )
    else:
        nx.draw_networkx_edges(
            graph, positions, ax=ax, edge_color=MUTED, alpha=0.25, width=0.4, arrows=False
        )
    nx.draw_networkx_nodes(
        graph,
        positions,
        ax=ax,
        node_color=[node_colour(graph.nodes[url]) for url in urls],
        node_size=[30 + 12 * min(in_degree[url], 20) for url in urls],
        edgecolors=SURFACE,
        linewidths=0.8,
    )
    if len(urls) <= LABELLED_NODES_LIMIT:
        xs = [x for x, _ in positions.values()]
        gap = (max(xs) - min(xs) or 1) * 0.012
        for url in urls:
            x, y = positions[url]
            label = _short_label(url, result.config.start_url)
            ax.text(x + gap, y, label, fontsize=7, color=INK_SECONDARY, va="center")
    ax.set_title(
        f"{result.config.start_url} · {graph.number_of_nodes()} pages · "
        f"{graph.number_of_edges()} links",
        loc="left",
        fontsize=10,
        color=INK,
    )
    return GraphDrawing(figure, ax, urls, np.array([positions[url] for url in urls]))


def save_figure(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)


def _layout(graph: nx.DiGraph[str], layout: Layout) -> dict[str, tuple[float, float]]:
    if layout == "spring":
        return {node: (x, y) for node, (x, y) in nx.spring_layout(graph, seed=1).items()}
    levels = {node: int(graph.nodes[node]["level"]) for node in graph}
    deepest = max(levels.values(), default=0)
    for node, level in levels.items():
        # Pages that were linked but never visited go on an extra row at the bottom.
        graph.nodes[node]["row"] = level if level >= 0 else deepest + 1
    positions = nx.multipartite_layout(graph, subset_key="row", align="vertical")
    return {node: (x, y) for node, (x, y) in positions.items()}


def _short_label(url: str, start_url: str) -> str:
    """The path for pages under the start page's address, the whole URL otherwise."""
    parts, start = urlsplit(url), urlsplit(start_url)
    if (parts.scheme, parts.netloc) != (start.scheme, start.netloc):
        return url
    return parts.path + (f"?{parts.query}" if parts.query else "")


def _figure(width: float, height: float) -> tuple[Figure, Axes]:
    figure = Figure(figsize=(width, height), facecolor=SURFACE, layout="constrained")
    return figure, figure.subplots()


def _style(ax: Axes, grid_axis: Literal["x", "y"]) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelcolor=INK_SECONDARY, labelsize=9, length=0)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK_SECONDARY)
    ax.yaxis.label.set_color(INK_SECONDARY)
