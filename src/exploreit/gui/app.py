"""The ExploreIT window: one tab per task, a status bar, theme and font size controls."""

import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

import ttkbootstrap as tb
from ttkbootstrap.style.theme import Colors

from exploreit.crawler import CrawlResult
from exploreit.gui.compare_tab import CompareTab
from exploreit.gui.crawl_tab import CrawlTab
from exploreit.gui.experiments_tab import ExperimentsTab
from exploreit.gui.graph_tab import GraphTab
from exploreit.gui.results_tab import ContentTab, PagesTab, ResultsTab
from exploreit.gui.widgets import TaskRunner

LIGHT_THEME, DARK_THEME = "nord-light", "nord-dark"
DEFAULT_FONT_SIZE = 12
FONT_SIZES = range(9, 21)
UI_FONTS = ["TkDefaultFont", "TkTextFont", "TkMenuFont", "TkCaptionFont", "TkTooltipFont"]


class ExploreApp:
    """Crawl sites, explore their link graph, run experiments and compare content."""

    def __init__(self, root: tb.Window, data_dir: Path) -> None:
        self.root = root
        self.output_dir = tk.StringVar(value=str(data_dir.resolve()))
        self.tasks = TaskRunner(root)
        self.status = tk.StringVar(value=f"Results are saved in {data_dir.resolve()}")
        self.dark = tk.BooleanVar(value=False)
        self.font_size = tk.IntVar(value=DEFAULT_FONT_SIZE)
        self.set_font_size(DEFAULT_FONT_SIZE)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.crawl_tab = CrawlTab(self.notebook, self)
        self.results_tab = ResultsTab(self.notebook, self)
        self.graph_tab = GraphTab(self.notebook, self)
        self.pages_tab = PagesTab(self.notebook)
        self.content_tab = ContentTab(self.notebook, self)
        self.experiments_tab = ExperimentsTab(self.notebook, self)
        self.compare_tab = CompareTab(self.notebook, self)
        tabs: list[tuple[ttk.Frame, str]] = [
            (self.crawl_tab, "  Crawl  "),
            (self.results_tab, "  Results  "),
            (self.graph_tab, "  Graph  "),
            (self.pages_tab, "  Pages  "),
            (self.content_tab, "  Content  "),
            (self.experiments_tab, "  Experiments  "),
            (self.compare_tab, "  Compare  "),
        ]
        for tab, title in tabs:
            self.notebook.add(tab, text=title)
        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self.compare_tab.refresh())
        self._build_status_bar()

        root.bind("<Control-r>", lambda _: self.crawl_tab.start())
        root.bind("<Escape>", lambda _: self.crawl_tab.stop())
        root.bind("<Control-equal>", lambda _: self.set_font_size(self.font_size.get() + 1))
        root.bind("<Control-plus>", lambda _: self.set_font_size(self.font_size.get() + 1))
        root.bind("<Control-minus>", lambda _: self.set_font_size(self.font_size.get() - 1))

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 6))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status).pack(side="left")
        tb.Checkbutton(
            bar,
            text="Dark mode",
            variable=self.dark,
            command=lambda: self.set_theme(DARK_THEME if self.dark.get() else LIGHT_THEME),
            bootstyle="round-toggle",
        ).pack(side="right", padx=(16, 0))
        size = ttk.Spinbox(
            bar,
            from_=FONT_SIZES[0],
            to=FONT_SIZES[-1],
            textvariable=self.font_size,
            width=4,
            command=lambda: self.set_font_size(self.font_size.get()),
        )
        size.pack(side="right")
        ttk.Label(bar, text="Text size").pack(side="right", padx=(0, 6))

    @property
    def data_dir(self) -> Path:
        """The folder chosen on the Crawl tab, where every result is saved and looked for."""
        return Path(self.output_dir.get().strip() or ".")

    def set_status(self, text: str) -> None:
        self.status.set(text)

    def set_busy(self, busy: bool) -> None:
        """Lock the settings while a crawl or an experiment runs, so they cannot change."""
        self.crawl_tab.set_locked(busy)
        self.experiments_tab.set_locked(busy)

    def set_theme(self, name: str) -> None:
        self.root.style.theme_use(name)
        self.set_font_size(self.font_size.get())  # a theme resets some widget fonts
        self.crawl_tab.apply_theme()
        self.content_tab.apply_theme()
        self.graph_tab.restyle()

    def theme_colours(self) -> Colors:
        colours: Colors = self.root.style.colors
        return colours

    def set_font_size(self, size: int) -> None:
        size = min(max(size, FONT_SIZES[0]), FONT_SIZES[-1])
        self.font_size.set(size)
        for name in UI_FONTS:
            tkfont.nametofont(name).configure(size=size)
        tkfont.nametofont("TkHeadingFont").configure(size=size, weight="bold")
        tkfont.nametofont("TkFixedFont").configure(size=size - 1)
        row_height = tkfont.nametofont("TkDefaultFont").metrics("linespace") + 10
        self.root.style.configure("Treeview", rowheight=row_height)

    def show_crawl(self, result: CrawlResult, path: Path) -> None:
        """Show a crawl, fresh or opened from disk, in every tab that describes it."""
        self.results_tab.show(result, path)
        self.graph_tab.show(result, path)
        self.pages_tab.show(result)
        self.content_tab.show(result, path)
        self.notebook.select(self.results_tab)
        self.set_status(f"{len(result.pages)} pages, {len(result.edges)} links · {path}")


def create_window(data_dir: Path = Path("data")) -> tuple[tb.Window, ExploreApp]:
    root = tb.Window(title="ExploreIT", themename=LIGHT_THEME, size=(1360, 880))
    root.minsize(1000, 680)
    return root, ExploreApp(root, data_dir)


def run_app(data_dir: Path = Path("data")) -> None:
    """Open the ExploreIT window in front of other windows and run until it is closed."""
    root, _ = create_window(data_dir)
    root.lift()
    root.attributes("-topmost", True)
    root.after(800, lambda: root.attributes("-topmost", False))
    root.focus_force()
    root.mainloop()
