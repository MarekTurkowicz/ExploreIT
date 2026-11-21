"""An interactive link graph on a Tk canvas: drag pages, zoom with the wheel, hover for details."""

from __future__ import annotations

import tkinter as tk
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from math import hypot

from exploreit.gui.graph_model import (
    ColourBy,
    GraphData,
    Node,
    SizeBy,
    category,
    hosts_by_frequency,
    node_label,
    radius,
    top_prestige,
)

MARGIN = 50
LABEL_FONT = "ExploreITGraphLabel"  # a named font, sized by the app for page names
ZOOM_STEP = 1.15
DIM_MIX = 0.8  # how far faded items move towards the background colour
MANY_EDGES = 1500  # above this, links not being moved are hidden while dragging or zooming
EDGES_BACK_MS = 200  # links come back this long after the last zoom step


@dataclass
class Style:
    """How the graph looks. Changing it restyles the drawing without moving pages."""

    colour_by: ColourBy = ColourBy.LEVEL
    size_by: SizeBy = SizeBy.LINKS_IN
    node_scale: float = 1.0
    labels: bool = True
    edges: bool = True
    short_names: Mapping[str, str] = field(default_factory=dict)  # page -> "P1", ...
    background: str = "#ffffff"
    foreground: str = "#222222"
    edge_colour: str = "#9a9890"
    accent: str = "#2a78d6"
    tip_background: str = "#fffbe6"
    tip_foreground: str = "#222222"


class GraphCanvas(tk.Canvas):
    """Draws a GraphData and lets the user move, zoom and explore it."""

    def __init__(
        self,
        master: tk.Misc,
        on_hover: Callable[[Node | None], object] = lambda _: None,
        on_open: Callable[[str], object] = lambda _: None,
    ) -> None:
        super().__init__(master, highlightthickness=0, cursor="arrow")
        self.on_hover = on_hover
        self.on_open = on_open
        self.style = Style()
        self.data = GraphData({}, [])
        self.start_url = ""
        self.world: dict[str, tuple[float, float]] = {}  # positions in the unit square
        self.zoom = 1.0
        self.pan = (0.0, 0.0)
        self._node_items: dict[str, int] = {}
        self._label_items: dict[str, int] = {}
        self._edge_items: dict[tuple[str, str], int] = {}
        self._items_to_url: dict[int, str] = {}
        self._edges_of: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)
        self._colours: dict[str, str] = {}
        self._top = 0.0
        self._hovered = ""
        self._drag_url = ""
        self._last_mouse = (0, 0)

        self._redraw_pending = self._edges_pending = ""
        self._view = (1.0, 1.0)  # drawing area in pixels, measured by redraw()
        self._faded: dict[str, str] = {}  # node colours when another page is hovered
        self.bind("<Configure>", lambda _: self.redraw_soon())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Motion>", self._on_move)
        self.bind("<Leave>", lambda _: self._set_hovered(""))
        self.bind("<MouseWheel>", self._on_wheel)  # Windows and macOS
        self.bind("<Button-4>", lambda e: self.zoom_at(ZOOM_STEP, e.x, e.y))  # Linux
        self.bind("<Button-5>", lambda e: self.zoom_at(1 / ZOOM_STEP, e.x, e.y))

    # Drawing

    def load(self, data: GraphData, world: dict[str, tuple[float, float]], start_url: str) -> None:
        """Draw a new graph and reset the view."""
        self.delete("all")
        self.data, self.world, self.start_url = data, dict(world), start_url
        self._node_items.clear()
        self._label_items.clear()
        self._edge_items.clear()
        self._items_to_url.clear()
        self._edges_of.clear()
        self._hovered = ""
        for edge in data.edges:
            self._edge_items[edge] = self.create_line(0, 0, 0, 0, arrow="last", tags="edge")
            self._edges_of[edge[0]].append(edge)
            self._edges_of[edge[1]].append(edge)
        for url in data.nodes:
            item = self.create_oval(0, 0, 0, 0, width=1.5, tags="node")
            self._node_items[url] = item
            self._items_to_url[item] = url
            label = self.create_text(0, 0, anchor="w", text="", tags="label", font=LABEL_FONT)
            self._label_items[url] = label
            self._items_to_url[label] = url
        self.fit()
        self.restyle(self.style)

    def restyle(self, style: Style) -> None:
        """Apply colours, sizes and visibility without moving anything."""
        self.style = style
        self._top = top_prestige(self.data)
        self.configure(background=style.background)
        hosts = hosts_by_frequency(self.data)
        self._colours = {
            url: category(node, style.colour_by, hosts).colour
            for url, node in self.data.nodes.items()
        }
        self._faded = {
            url: _mix(colour, style.background, DIM_MIX) for url, colour in self._colours.items()
        }
        for url, item in self._node_items.items():
            self.itemconfigure(item, fill=self._colours[url], outline=style.background)
        for url, item in self._label_items.items():
            self.itemconfigure(
                item,
                text=node_label(
                    self.data.nodes[url], self.start_url, style.size_by, style.short_names
                ),
            )
        # One call per tag instead of one per item: a graph can have thousands of links.
        self.itemconfigure(
            "label", fill=style.foreground, state="normal" if style.labels else "hidden"
        )
        self.itemconfigure(
            "edge",
            fill=style.edge_colour,
            width=1,
            arrowshape=(7, 8, 3),
            state="normal" if style.edges else "hidden",
        )
        self.tag_raise("node")
        self.tag_raise("label")
        self.redraw()

    def redraw(self, edges: bool = True) -> None:
        """Move every item to where its page is under the current zoom and pan."""
        self._redraw_pending = ""
        self._view = self._view_size()
        positions = {url: self.screen(url) for url in self.data.nodes}
        for url in self.data.nodes:
            self._place_node(url, positions[url])
        if edges:
            for edge in self._edge_items:
                self._place_edge(edge, positions)

    def redraw_soon(self) -> None:
        """Redraw once the pending events are handled, so a burst of them costs one redraw."""
        if not self._redraw_pending:
            self._redraw_pending = self.after_idle(self.redraw)

    def _view_size(self) -> tuple[float, float]:
        return (
            max(self.winfo_width(), 2 * MARGIN + 1) - 2 * MARGIN,
            max(self.winfo_height(), 2 * MARGIN + 1) - 2 * MARGIN,
        )

    def fit(self) -> None:
        """Show the whole graph."""
        self.zoom, self.pan = 1.0, (0.0, 0.0)
        self.redraw()

    def zoom_at(self, factor: float, x: float, y: float) -> None:
        """Zoom by factor keeping the point (x, y) on screen in place."""
        self.zoom *= factor
        self.pan = (x - (x - self.pan[0]) * factor, y - (y - self.pan[1]) * factor)
        if not (self.style.edges and len(self._edge_items) > MANY_EDGES):
            self.redraw_soon()
            return
        # A big graph: move only the pages while the wheel turns, the links once it stops.
        self.itemconfigure("edge", state="hidden")
        self.redraw(edges=False)
        if self._edges_pending:
            self.after_cancel(self._edges_pending)
        self._edges_pending = self.after(EDGES_BACK_MS, self._show_edges)

    def _show_edges(self) -> None:
        self._edges_pending = ""
        self.redraw()
        self.itemconfigure("edge", state="normal" if self.style.edges else "hidden")

    def screen(self, url: str) -> tuple[float, float]:
        wx, wy = self.world[url]
        width, height = self._view
        return (
            (MARGIN + wx * width) * self.zoom + self.pan[0],
            (MARGIN + wy * height) * self.zoom + self.pan[1],
        )

    def move_node(self, url: str, dx: float, dy: float) -> None:
        """Move a page by (dx, dy) screen pixels and redraw its links."""
        width, height = (max(side, 1) * self.zoom for side in self._view)
        wx, wy = self.world[url]
        self.world[url] = (wx + dx / width, wy + dy / height)
        self._place_node(url)
        for edge in self._edges_of[url]:
            self._place_edge(edge)

    def node_at(self, x: float, y: float) -> str:
        """The page drawn under the point, or ""."""
        for item in reversed(self.find_overlapping(x - 1, y - 1, x + 1, y + 1)):
            if item in self._items_to_url and "edge" not in self.gettags(item):
                return self._items_to_url[item]
        return ""

    def _radius(self, node: Node) -> float:
        return radius(node, self.style.size_by, self.style.node_scale, self._top)

    def _place_node(self, url: str, position: tuple[float, float] | None = None) -> None:
        x, y = position or self.screen(url)
        r = self._radius(self.data.nodes[url])
        self.coords(self._node_items[url], x - r, y - r, x + r, y + r)
        self.coords(self._label_items[url], x + r + 4, y)

    def _place_edge(
        self, edge: tuple[str, str], positions: dict[str, tuple[float, float]] | None = None
    ) -> None:
        if positions is None:
            positions = {url: self.screen(url) for url in edge}
        (x1, y1), (x2, y2) = positions[edge[0]], positions[edge[1]]
        length = hypot(x2 - x1, y2 - y1) or 1.0
        # Stop the arrow at the edge of the target circle so its head stays visible.
        r = self._radius(self.data.nodes[edge[1]]) + 1
        self.coords(
            self._edge_items[edge], x1, y1, x2 - (x2 - x1) * r / length, y2 - (y2 - y1) * r / length
        )

    # Interaction

    def _on_press(self, event: tk.Event[tk.Misc]) -> None:
        self._drag_url = self.node_at(event.x, event.y)
        self._last_mouse = (event.x, event.y)
        self.configure(cursor="fleur")
        if self.style.edges and len(self._edge_items) > MANY_EDGES:
            # Repainting thousands of lines on every mouse move makes dragging stutter,
            # so only the dragged page's own links stay visible until the button is let go.
            self.itemconfigure("edge", state="hidden")
            for edge in self._edges_of[self._drag_url] if self._drag_url else []:
                self.itemconfigure(self._edge_items[edge], state="normal")

    def _on_drag(self, event: tk.Event[tk.Misc]) -> None:
        dx, dy = event.x - self._last_mouse[0], event.y - self._last_mouse[1]
        self._last_mouse = (event.x, event.y)
        if self._drag_url:
            self.move_node(self._drag_url, dx, dy)
        else:
            self.pan = (self.pan[0] + dx, self.pan[1] + dy)
            self.move("all", dx, dy)

    def _on_release(self, _: tk.Event[tk.Misc]) -> None:
        if self.style.edges and len(self._edge_items) > MANY_EDGES:
            self.itemconfigure("edge", state="normal")
        self._drag_url = ""
        self.configure(cursor="arrow")

    def destroy(self) -> None:
        for pending in (self._redraw_pending, self._edges_pending):
            if pending:
                self.after_cancel(pending)
        super().destroy()

    def _on_double_click(self, event: tk.Event[tk.Misc]) -> None:
        if url := self.node_at(event.x, event.y):
            self.on_open(url)

    def _on_move(self, event: tk.Event[tk.Misc]) -> None:
        if not self._drag_url:
            self._set_hovered(self.node_at(event.x, event.y))

    def _on_wheel(self, event: tk.Event[tk.Misc]) -> None:
        self.zoom_at(ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP, event.x, event.y)

    def _set_hovered(self, url: str) -> None:
        """Highlight a page with its links and neighbours and fade everything else."""
        if url == self._hovered:
            return
        self._hovered = url
        style = self.style
        if not url:
            for node, item in self._node_items.items():
                self.itemconfigure(item, fill=self._colours[node], width=1.5)
            self.itemconfigure("edge", fill=style.edge_colour, width=1)
            self.itemconfigure("label", fill=style.foreground)
            self.delete("tip")
            self.on_hover(None)
            return

        linked = {url} | {other for edge in self._edges_of[url] for other in edge}
        for node, item in self._node_items.items():
            colour = self._colours[node] if node in linked else self._faded[node]
            self.itemconfigure(item, fill=colour, width=3 if node == url else 1.5)
        self.itemconfigure("label", fill=_mix(style.foreground, style.background, DIM_MIX))
        for node in linked:
            self.itemconfigure(self._label_items[node], fill=style.foreground)
        self.itemconfigure("edge", fill=_mix(style.edge_colour, style.background, DIM_MIX), width=1)
        for edge in self._edges_of[url]:
            item = self._edge_items[edge]
            self.itemconfigure(item, fill=style.accent, width=2)
            self.tag_raise(item, "edge")
        self.tag_raise(self._node_items[url])
        self.tag_raise(self._label_items[url])
        self._show_tip(self.data.nodes[url])
        self.on_hover(self.data.nodes[url])

    def _show_tip(self, node: Node) -> None:
        """A small card next to the page with what is known about it."""
        self.delete("tip")
        x, y = self.screen(node.url)
        r = self._radius(node)
        text = self.create_text(
            x + r + 12,
            y + r + 10,
            anchor="nw",
            text=describe(node),
            fill=self.style.tip_foreground,
            tags="tip",
            font="TkDefaultFont",
        )
        x1, y1, x2, y2 = self.bbox(text)
        # Keep the card inside the canvas.
        shift_x = min(0, self.winfo_width() - x2 - 8)
        shift_y = min(0, self.winfo_height() - y2 - 8)
        self.move(text, shift_x, shift_y)
        card = self.create_rectangle(
            x1 - 8 + shift_x,
            y1 - 6 + shift_y,
            x2 + 8 + shift_x,
            y2 + 6 + shift_y,
            fill=self.style.tip_background,
            outline=self.style.accent,
            tags="tip",
        )
        self.tag_raise(card)
        self.tag_raise(text)


def _mix(colour: str, other: str, amount: float) -> str:
    """Blend two #rrggbb colours: amount 0 gives colour, 1 gives other."""
    a = [int(colour[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b, strict=True))


def describe(node: Node) -> str:
    """Text shown for a page under the cursor."""
    lines = [node.url]
    if node.visited:
        lines += [
            f"Level {node.level} · HTTP {node.status_code}",
            node.content_type or "unknown type",
        ]
    else:
        lines.append("Linked but not visited")
    lines.append(f"Links out {node.links_out} · links in {node.links_in}")
    if node.prestige:
        lines.append(f"Prestige {node.prestige:.4g}")
    lines.append("Drag to move · double-click to open")
    return "\n".join(lines)
