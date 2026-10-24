"""The ExploreIT window: one tab per task, a status bar and a light/dark switch."""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import sv_ttk

from exploreit.crawler import CrawlResult
from exploreit.gui.compare_tab import CompareTab
from exploreit.gui.crawl_tab import CrawlTab
from exploreit.gui.experiments_tab import ExperimentsTab
from exploreit.gui.graph_tab import GraphTab
from exploreit.gui.results_tab import ContentTab, PagesTab, ResultsTab
from exploreit.gui.widgets import TaskRunner


class ExploreApp:
    """Crawl sites, explore their link graph, run experiments and compare content."""

    def __init__(self, root: tk.Tk, data_dir: Path) -> None:
        self.root = root
        self.data_dir = data_dir
        self.tasks = TaskRunner(root)
        self.status = tk.StringVar(value=f"Results are saved in {data_dir.resolve()}")
        self.dark = tk.BooleanVar(value=False)

        root.title("ExploreIT")
        root.geometry("1280x820")
        root.minsize(960, 640)
        sv_ttk.set_theme("light")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.crawl_tab = CrawlTab(self.notebook, self)
        self.results_tab = ResultsTab(self.notebook, self)
        self.graph_tab = GraphTab(self.notebook, self)
        self.pages_tab = PagesTab(self.notebook)
        self.content_tab = ContentTab(self.notebook)
        self.experiments_tab = ExperimentsTab(self.notebook, self)
        self.compare_tab = CompareTab(self.notebook, self)
        tabs: list[tuple[ttk.Frame, str]] = [
            (self.crawl_tab, "Crawl"),
            (self.results_tab, "Results"),
            (self.graph_tab, "Graph"),
            (self.pages_tab, "Pages"),
            (self.content_tab, "Content"),
            (self.experiments_tab, "Experiments"),
            (self.compare_tab, "Compare"),
        ]
        for tab, title in tabs:
            self.notebook.add(tab, text=title)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self.compare_tab.refresh())

        status_bar = ttk.Frame(root, padding=(10, 6))
        status_bar.pack(fill="x")
        ttk.Label(status_bar, textvariable=self.status).pack(side="left")
        ttk.Checkbutton(
            status_bar,
            text="Dark mode",
            style="Switch.TCheckbutton",
            variable=self.dark,
            command=lambda: sv_ttk.set_theme("dark" if self.dark.get() else "light"),
        ).pack(side="right")
        root.bind("<Control-r>", lambda _: self.crawl_tab.start())

    def set_status(self, text: str) -> None:
        self.status.set(text)

    def show_crawl(self, result: CrawlResult, path: Path) -> None:
        """Show a crawl, fresh or opened from disk, in every tab that describes it."""
        self.results_tab.show(result, path)
        self.graph_tab.show(result)
        self.pages_tab.show(result)
        self.content_tab.show(result)
        self.notebook.select(self.results_tab)
        self.set_status(f"{len(result.pages)} pages, {len(result.edges)} links · {path}")


def run_app(data_dir: Path = Path("data")) -> None:
    """Open the ExploreIT window and run until it is closed."""
    if sys.platform == "win32":
        import ctypes

        # Render sharp text on high-DPI screens instead of a blurry, scaled-up window.
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    root = tk.Tk()
    ExploreApp(root, data_dir)
    root.mainloop()
