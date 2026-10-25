"""Charts of crawl results. Each function returns a matplotlib Figure that can be saved
as PNG or shown inside the application window."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from exploreit.crawler import CrawlResult
from exploreit.graph import compute_stats

SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # categorical slots 1-3: blue, orange, aqua
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"

COMPARED_METRICS = {
    "pages": "Pages visited",
    "links": "Links found",
    "depth": "Graph depth",
    "subpage_links_mean": "Mean links per subpage",
}


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


def convergence_figure(histories: dict[str, list[np.ndarray]]) -> Figure:
    """How much prestige still changes after each iteration, per method (log scale).

    A line that keeps falling settles; a flat line means values swap back and forth.
    """
    figure, ax = _figure(width=7, height=3.8)
    drawn = 0
    for index, (name, history) in enumerate(histories.items()):
        if len(history) < 2:
            continue
        changes = [
            max(float(np.abs(after - before).max()), 1e-16) for before, after in pairwise(history)
        ]
        ax.plot(
            range(1, len(changes) + 1),
            changes,
            color=SERIES[index % len(SERIES)],
            linewidth=2,
            label=name,
        )
        drawn += 1
    ax.set_yscale("log")
    _style(ax, grid_axis="y")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Largest change")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_title("How fast prestige settles", loc="left", fontsize=11, color=INK)
    if drawn > 1:
        ax.legend(frameon=False, fontsize=9)
    return figure


def network_figure(
    edges: list[tuple[str, str]],
    positions: dict[str, tuple[float, float]],
    colours: dict[str, str],
    sizes: dict[str, float],
    labels: dict[str, str],
    title: str,
) -> Figure:
    """Draw a graph exactly as laid out on screen (y grows downwards) for saving as PNG."""
    figure = Figure(figsize=(12, 8), facecolor=SURFACE, layout="constrained")
    ax = figure.subplots()
    ax.set_facecolor(SURFACE)
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=10, color=INK)
    if not positions:
        return figure

    segments = [(positions[a], positions[b]) for a, b in edges]
    ax.add_collection(LineCollection(segments, colors=MUTED, linewidths=0.5, alpha=0.4))
    urls = list(positions)
    xs, ys = zip(*(positions[url] for url in urls), strict=True)
    ax.scatter(
        xs,
        ys,
        s=[sizes[url] ** 2 for url in urls],
        c=[colours[url] for url in urls],
        edgecolors=SURFACE,
        linewidths=0.6,
        zorder=2,
    )
    for url, text in labels.items():
        x, y = positions[url]
        ax.annotate(
            text,
            (x, y),
            xytext=(6, 0),
            textcoords="offset points",
            fontsize=7,
            color=INK_SECONDARY,
            va="center",
        )
    ax.invert_yaxis()
    ax.margins(0.04)
    return figure


def save_figure(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)


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
