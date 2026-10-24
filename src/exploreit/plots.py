"""Static charts (PNG) of crawl results."""

from collections import Counter
from pathlib import Path
from typing import Literal

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from exploreit.crawler import CrawlResult
from exploreit.graph import compute_stats

SERIES = ["#2a78d6", "#eb6834"]  # categorical slots 1-2: blue, orange
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


def plot_levels(result: CrawlResult, path: Path) -> None:
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
    ax.set_title(f"Pages per level · {result.config.start_url}", loc="left", fontsize=11, color=INK)
    _save(figure, path)


def plot_out_links(result: CrawlResult, path: Path) -> None:
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
    _save(figure, path)


def plot_comparison(table: pd.DataFrame, path: Path) -> None:
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
    _save(figure, path)


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


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150)
