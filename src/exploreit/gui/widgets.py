"""Building blocks shared by the tabs: a sortable table, a chart panel and a task runner."""

from __future__ import annotations

import gc
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from functools import partial
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from pydantic import ValidationError

if TYPE_CHECKING:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

POLL_MS = 50
COLLECT_EVERY_S = 2.0


class TaskRunner:
    """Runs slow work in a background thread and hands its results back to the Tk thread.

    Tk widgets may only be touched from the thread that created them, so a worker never
    updates the window itself: it queues calls that the Tk thread runs every POLL_MS.

    Python's cyclic garbage collector runs in whichever thread happens to allocate memory.
    If it frees an old Tk object (a replaced chart, a destroyed widget) from a worker,
    Tk raises "main thread is not in main loop". So automatic collection is switched off
    while the window is open and the Tk thread collects garbage itself every few seconds.
    """

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._calls: queue.Queue[Callable[[], object]] = queue.Queue()
        self._running = 0
        self._after = ""
        self._collected = time.monotonic()
        gc.disable()
        root.bind("<Destroy>", self._stop, add="+")
        self._poll()

    @property
    def busy(self) -> bool:
        return self._running > 0 or not self._calls.empty()

    def run[T](
        self,
        work: Callable[[], T],
        on_done: Callable[[T], object],
        on_error: Callable[[Exception], object] = lambda error: show_error(error),
    ) -> None:
        """Run work() in a thread, then on_done(result), or on_error(error), in the Tk thread."""
        self._running += 1

        def target() -> None:
            try:
                result = work()
            except Exception as error:  # show any failure in the window instead of losing it
                self.call(on_error, error)
            else:
                self.call(on_done, result)
            finally:
                self.call(self._finish)

        threading.Thread(target=target, daemon=True).start()

    def call(self, function: Callable[..., object], *args: object) -> None:
        """Queue function(*args) to run in the Tk thread. Safe to use from any thread."""
        self._calls.put(lambda: function(*args))

    def _finish(self) -> None:
        self._running -= 1

    def _poll(self) -> None:
        while not self._calls.empty():
            self._calls.get_nowait()()
        if time.monotonic() - self._collected > COLLECT_EVERY_S:
            gc.collect()
            self._collected = time.monotonic()
        self._after = self._root.after(POLL_MS, self._poll)

    def _stop(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is self._root:  # children send <Destroy> too
            self._root.after_cancel(self._after)
            gc.enable()


class Table(ttk.Frame):
    """A Treeview showing rows of values, sortable by clicking a column header."""

    def __init__(
        self,
        master: tk.Misc,
        height: int = 12,
        on_select: Callable[[tuple[str, ...]], object] = lambda _: None,
        on_open: Callable[[tuple[str, ...]], object] = lambda _: None,
    ) -> None:
        super().__init__(master)
        self._sorted_by = ""
        self.tree = ttk.Treeview(self, show="headings", height=height)
        scroll_y = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", lambda _: on_select(self.selected()))
        self.tree.bind("<Double-1>", lambda _: on_open(self.selected()))

    def set_rows(
        self, columns: Sequence[str], rows: Iterable[Sequence[object]], widths: Sequence[int] = ()
    ) -> None:
        """Show the rows; widths are in pixels at 96 DPI and grow to fit each heading."""
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=list(columns))
        dpi_scale = float(self.tk.call("tk", "scaling")) * 72 / 96
        heading_font = tkfont.nametofont("TkHeadingFont")
        for index, column in enumerate(columns):
            self.tree.heading(column, text=column, command=partial(self._sort, column))
            width = widths[index] if index < len(widths) else 120
            width = max(round(width * dpi_scale), heading_font.measure(column) + 24)
            self.tree.column(column, width=width, stretch=True)  # all share the spare room
        for row in rows:
            self.tree.insert("", "end", values=[str(value) for value in row])

    def rows(self) -> list[tuple[str, ...]]:
        return [tuple(self.tree.item(item, "values")) for item in self.tree.get_children()]

    def selected(self) -> tuple[str, ...]:
        selection = self.tree.selection()
        return tuple(self.tree.item(selection[0], "values")) if selection else ()

    def _sort(self, column: str) -> None:
        items = [(self.tree.set(item, column), item) for item in self.tree.get_children()]
        descending = self._sorted_by == column  # a second click reverses the order
        items.sort(key=lambda pair: _sort_key(pair[0]), reverse=descending)
        for index, (_, item) in enumerate(items):
            self.tree.move(item, "", index)
        self._sorted_by = "" if descending else column


class ChartPanel(ttk.Frame):
    """Shows a matplotlib Figure, optionally with the zoom, pan and save toolbar."""

    def __init__(self, master: tk.Misc, toolbar: bool = False) -> None:
        super().__init__(master)
        self.toolbar = toolbar

    def show(self, figure: Figure) -> FigureCanvasTkAgg:
        for child in self.winfo_children():
            child.destroy()
        # The old chart holds Tk images that may only be freed in this thread. Collect it
        # now, or Python may free it later in a worker thread and Tk would complain.
        gc.collect()
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

        self._match_theme(figure)
        canvas = FigureCanvasTkAgg(figure, master=self)
        if self.toolbar:
            NavigationToolbar2Tk(canvas, self, pack_toolbar=False).pack(side="bottom", fill="x")
        widget = canvas.get_tk_widget()
        # Ask for little room and fill whatever the layout gives: the figure is redrawn to
        # fit, instead of forcing the window to its own size in inches.
        widget.configure(width=200, height=150)
        widget.pack(fill="both", expand=True)
        canvas.draw()
        return canvas

    def _match_theme(self, figure: Figure) -> None:
        """Paint the chart background and text in the window's colours (light or dark)."""
        from matplotlib.text import Text

        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or "white"
        foreground = style.lookup("TLabel", "foreground") or "black"
        figure.set_facecolor(background)
        for text in figure.findobj(Text):
            text.set_color(foreground)
        for ax in figure.axes:
            ax.set_facecolor(background)
            ax.tick_params(colors=foreground)
            for spine in ax.spines.values():
                spine.set_edgecolor(foreground)
            for line in [*ax.get_xgridlines(), *ax.get_ygridlines()]:
                line.set_color(foreground)
                line.set_alpha(0.15)
        for legend in [*figure.legends, *(ax.get_legend() for ax in figure.axes)]:
            if legend is not None:
                legend.get_frame().set_facecolor(background)
                legend.get_frame().set_edgecolor(background)


def saved_crawls(data_dir: Path) -> list[str]:
    """Paths of saved crawl results relative to the data directory, newest first."""
    paths = sorted(data_dir.rglob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path.relative_to(data_dir)) for path in paths]


def timestamp() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}"


def describe_errors(error: ValueError) -> str:
    """Readable text for a pydantic validation error or any other ValueError."""
    if isinstance(error, ValidationError):
        return "\n".join(f"{problem['loc'][0]}: {problem['msg']}" for problem in error.errors())
    return str(error)


def show_error(error: Exception) -> None:
    messagebox.showerror("ExploreIT", f"{type(error).__name__}: {error}")


def _sort_key(value: str) -> tuple[int, float | str]:
    """Sort numbers numerically and before text."""
    try:
        return (0, float(value))
    except ValueError:
        return (1, value.lower())
