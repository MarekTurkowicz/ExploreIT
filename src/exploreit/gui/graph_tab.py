"""Graph tab: the link graph drawn inside the window, with zoom, pan and hover."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import TYPE_CHECKING

import numpy as np
from matplotlib.backend_bases import Event, MouseEvent

from exploreit.crawler import CrawlResult
from exploreit.gui.widgets import ChartPanel
from exploreit.plots import GraphDrawing, Layout, graph_figure

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp

HOVER_RADIUS_PX = 12
LAYOUTS: dict[str, Layout] = {"by level (tree)": "levels", "spring (clusters)": "spring"}


class GraphTab(ttk.Frame):
    """Draws the current crawl. Hover a page to see its URL, double-click to open it."""

    # Set by show() and by the background drawing.
    result: CrawlResult
    drawing: GraphDrawing

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        self.layout = tk.StringVar(value=next(iter(LAYOUTS)))
        self.show_unvisited = tk.BooleanVar(value=False)
        self.hovered = tk.StringVar(value="Crawl a site or open a saved crawl to draw its graph.")

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Layout").pack(side="left")
        layout = ttk.Combobox(
            toolbar, textvariable=self.layout, values=list(LAYOUTS), state="readonly", width=18
        )
        layout.pack(side="left", padx=(6, 12))
        layout.bind("<<ComboboxSelected>>", lambda _: self.redraw())
        ttk.Checkbutton(
            toolbar,
            text="Show linked pages that were not visited",
            variable=self.show_unvisited,
            command=self.redraw,
        ).pack(side="left")
        ttk.Label(self, textvariable=self.hovered, foreground="#52514e").pack(fill="x")
        self.chart = ChartPanel(self, toolbar=True)
        self.chart.pack(fill="both", expand=True)

    def show(self, result: CrawlResult) -> None:
        self.result = result
        self.redraw()

    def redraw(self) -> None:
        if not hasattr(self, "result"):
            return
        result, layout, unvisited = (
            self.result,
            LAYOUTS[self.layout.get()],
            self.show_unvisited.get(),
        )
        self.hovered.set("Drawing the graph …")
        self.app.tasks.run(lambda: graph_figure(result, layout, not unvisited), self._display)

    def url_at(self, x: float, y: float) -> str:
        """Return the URL of the page drawn nearest to a point in pixels, or ""."""
        if not self.drawing.urls:
            return ""
        points = self.drawing.axes.transData.transform(self.drawing.positions)
        distances = np.hypot(points[:, 0] - x, points[:, 1] - y)
        nearest = int(distances.argmin())
        return self.drawing.urls[nearest] if distances[nearest] <= HOVER_RADIUS_PX else ""

    def _display(self, drawing: GraphDrawing) -> None:
        self.drawing = drawing
        canvas = self.chart.show(drawing.figure)
        canvas.mpl_connect("motion_notify_event", self._on_move)
        canvas.mpl_connect("button_press_event", self._on_click)
        self.hovered.set(
            f"{len(drawing.urls)} pages. Hover a page to see its address, double-click to open "
            "it. Use the toolbar below to zoom, pan or save the picture."
        )

    def _on_move(self, event: Event) -> None:
        if isinstance(event, MouseEvent) and (url := self.url_at(event.x, event.y)):
            self.hovered.set(url)

    def _on_click(self, event: Event) -> None:
        if (
            isinstance(event, MouseEvent)
            and event.dblclick
            and (url := self.url_at(event.x, event.y))
        ):
            webbrowser.open(url)
