"""Graph tab: the interactive link graph with style controls, a legend and page details."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from exploreit.crawler import CrawlResult
from exploreit.gui.graph_canvas import GraphCanvas, Style, describe
from exploreit.gui.graph_model import (
    ColourBy,
    GraphData,
    Layout,
    Node,
    SizeBy,
    category,
    graph_data,
    hosts_by_frequency,
    legend,
    positions,
    radius,
    short_label,
)
from exploreit.plots import network_figure, save_figure

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp

LABELS_BY_DEFAULT_UP_TO = 80  # more labels than this turn into an unreadable carpet


class GraphTab(ttk.Frame):
    """Drag pages, zoom with the mouse wheel, hover a page for its details."""

    # Set by show(); the controls only act once a crawl is loaded.
    result: CrawlResult
    crawl_file: Path

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=10)
        self.app = app
        self.data = GraphData({}, [])
        self.layout = tk.StringVar(value=Layout.LEVELS)
        self.colour_by = tk.StringVar(value=ColourBy.LEVEL)
        self.size_by = tk.StringVar(value=SizeBy.LINKS_IN)
        self.node_scale = tk.DoubleVar(value=1.0)
        self.labels = tk.BooleanVar(value=True)
        self.edges = tk.BooleanVar(value=True)
        self.unvisited = tk.BooleanVar(value=False)
        self._build()

    def _build(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 8))
        choices = [
            ("Layout", self.layout, Layout, self.relayout),
            ("Colour by", self.colour_by, ColourBy, self.restyle),
            ("Size by", self.size_by, SizeBy, self.restyle),
        ]
        for label, variable, options, action in choices:
            ttk.Label(controls, text=label).pack(side="left", padx=(0, 6))
            box = ttk.Combobox(
                controls,
                textvariable=variable,
                values=[option.value for option in options],
                state="readonly",
                width=18,
            )
            box.pack(side="left", padx=(0, 16))
            box.bind("<<ComboboxSelected>>", _ignoring_event(action))
        ttk.Label(controls, text="Node size").pack(side="left", padx=(0, 6))
        ttk.Scale(
            controls,
            from_=0.4,
            to=3.0,
            variable=self.node_scale,
            command=lambda _: self.restyle(),
            length=120,
        ).pack(side="left")

        toggles = ttk.Frame(self)
        toggles.pack(fill="x", pady=(0, 8))
        for text, flag, toggled in [
            ("Labels", self.labels, self.restyle),
            ("Links", self.edges, self.restyle),
            ("Linked pages that were not visited", self.unvisited, self.reload),
        ]:
            tb.Checkbutton(
                toggles, text=text, variable=flag, command=toggled, bootstyle="round-toggle"
            ).pack(side="left", padx=(0, 18))
        tb.Button(toggles, text="Save PNG", command=self.save_png, bootstyle="secondary").pack(
            side="right"
        )
        tb.Button(
            toggles, text="Fit to window", command=lambda: self.canvas.fit(), bootstyle="secondary"
        ).pack(side="right", padx=8)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        side = ttk.Frame(body, width=300, padding=(12, 0, 0, 0))
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        self.canvas = GraphCanvas(body, on_hover=self._show_details, on_open=webbrowser.open)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.summary = ttk.Label(side, text="No crawl loaded", font="TkHeadingFont")
        self.summary.pack(anchor="w")
        ttk.Label(side, text="Legend", font="TkHeadingFont").pack(anchor="w", pady=(14, 4))
        self.legend = ttk.Frame(side)
        self.legend.pack(fill="x")
        ttk.Label(side, text="Page under the cursor", font="TkHeadingFont").pack(
            anchor="w", pady=(14, 4)
        )
        self.details = ttk.Label(side, text="Hover a page", wraplength=280, justify="left")
        self.details.pack(anchor="w")
        tb.Label(
            side,
            text="Mouse wheel: zoom\nDrag the background: move the view\n"
            "Drag a page: move it\nDouble-click a page: open it",
            justify="left",
            bootstyle="secondary",
        ).pack(anchor="w", side="bottom")

    def show(self, result: CrawlResult, path: Path) -> None:
        self.result, self.crawl_file = result, path
        self.reload()

    def reload(self) -> None:
        """Rebuild the graph from the crawl, e.g. after toggling unvisited pages."""
        if not hasattr(self, "result"):
            return
        self.data = graph_data(self.result, visited_only=not self.unvisited.get())
        self.labels.set(len(self.data.nodes) <= LABELS_BY_DEFAULT_UP_TO)
        self.relayout()

    def relayout(self) -> None:
        """Compute positions in the background; big graphs can take a second."""
        if not hasattr(self, "result"):
            return
        data, layout = self.data, Layout(self.layout.get())
        self.summary.configure(text="Laying out the graph …")
        self.app.tasks.run(lambda: positions(data, layout), self._display)

    def restyle(self) -> None:
        self.canvas.restyle(self._style())
        self._fill_legend()

    def save_png(self) -> None:
        if not hasattr(self, "result"):
            return
        style = self.canvas.style
        hosts = hosts_by_frequency(self.data)
        nodes = self.data.nodes
        world = self.canvas.world
        figure = network_figure(
            self.data.edges,
            world,
            {url: category(node, style.colour_by, hosts).colour for url, node in nodes.items()},
            {url: radius(node, style.size_by, style.node_scale) for url, node in nodes.items()},
            {url: short_label(url, self.result.config.start_url) for url in nodes}
            if style.labels
            else {},
            f"{self.result.config.start_url} · {self.result.config.describe()}",
        )
        path = self.crawl_file.with_name(f"{self.crawl_file.stem}-graph.png")
        save_figure(figure, path)
        self.app.set_status(f"Saved {path}")

    def _display(self, world: dict[str, tuple[float, float]]) -> None:
        self.canvas.style = self._style()
        self.canvas.load(self.data, world, self.result.config.start_url)
        pages, links = len(self.data.nodes), len(self.data.edges)
        self.summary.configure(
            text=f"{pages} page{'s' * (pages != 1)} · {links} link{'s' * (links != 1)}"
        )
        self._fill_legend()

    def _style(self) -> Style:
        colours = self.app.theme_colours()
        return Style(
            colour_by=ColourBy(self.colour_by.get()),
            size_by=SizeBy(self.size_by.get()),
            node_scale=self.node_scale.get(),
            labels=self.labels.get(),
            edges=self.edges.get(),
            background=colours.inputbg,
            foreground=colours.inputfg,
            accent=colours.primary,
            tip_background=colours.bg,
            tip_foreground=colours.fg,
        )

    def _fill_legend(self) -> None:
        for child in self.legend.winfo_children():
            child.destroy()
        for group, count in legend(self.data, ColourBy(self.colour_by.get())):
            row = ttk.Frame(self.legend)
            row.pack(fill="x", pady=1)
            tk.Label(row, background=group.colour, width=2).pack(side="left")
            ttk.Label(row, text=group.label).pack(side="left", padx=8)
            ttk.Label(row, text=str(count)).pack(side="right")

    def _show_details(self, node: Node | None) -> None:
        self.details.configure(text=describe(node) if node else "Hover a page")


def _ignoring_event(action: Callable[[], object]) -> Callable[[tk.Event[tk.Misc]], object]:
    """Adapt a no-argument action to a Tk event handler."""
    return lambda _: action()
