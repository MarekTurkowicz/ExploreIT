"""Results, Pages and Content tabs: everything known about the current crawl."""

from __future__ import annotations

import tkinter as tk
import webbrowser
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from pydantic import ValidationError

from exploreit.crawler import CrawlResult
from exploreit.export import write_gexf, write_html
from exploreit.graph import click_tree, compute_stats, shortest_levels
from exploreit.gui.widgets import ChartPanel, Table
from exploreit.plots import levels_figure, out_links_figure, save_figure

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp


class ResultsTab(ttk.Frame):
    """Graph statistics, pages per level and the site structure as a tree."""

    # Set by show(); the buttons that use them stay disabled until then.
    result: CrawlResult
    crawl_file: Path

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="Open saved crawl…", command=self._choose_file).pack(side="left")
        self.actions = [
            ttk.Button(toolbar, text="Open graph in browser", command=self.open_graph),
            ttk.Button(toolbar, text="Export GEXF (Gephi)", command=self.export_gexf),
            ttk.Button(toolbar, text="Save charts (PNG)", command=self.save_charts),
        ]
        for button in self.actions:
            button.pack(side="left", padx=(8, 0))
            button.state(["disabled"])
        self.file_label = ttk.Label(toolbar, text="No crawl loaded yet", foreground="#898781")
        self.file_label.pack(side="left", padx=12)

        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        self.stats = Table(left, height=14)
        self.stats.pack(fill="x")
        self.levels_chart = ChartPanel(left)
        self.levels_chart.pack(fill="both", expand=True, pady=(10, 0))
        panes.add(left, weight=1)

        right = ttk.Frame(panes)
        ttk.Label(right, text="Site structure (shortest click paths)").pack(anchor="w")
        self.tree = ttk.Treeview(right, show="tree")
        scroll = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        panes.add(right, weight=1)

    def open_file(self, path: Path) -> None:
        try:
            result = CrawlResult.load(path)
        except (OSError, ValidationError) as error:
            messagebox.showerror("Cannot open crawl", str(error))
            return
        self.app.show_crawl(result, path)

    def show(self, result: CrawlResult, path: Path) -> None:
        self.result, self.crawl_file = result, path
        self.file_label.configure(text=str(path))
        self.stats.set_rows(["Metric", "Value"], compute_stats(result).summary(), widths=[190])
        self.levels_chart.show(levels_figure(result))
        self._fill_tree(result)
        for button in self.actions:
            button.state(["!disabled"])

    def open_graph(self) -> None:
        html_file = self.crawl_file.with_suffix(".html")
        write_html(self.result, html_file)
        webbrowser.open(html_file.resolve().as_uri())

    def export_gexf(self) -> None:
        gexf_file = self.crawl_file.with_suffix(".gexf")
        write_gexf(self.result, gexf_file)
        self.app.set_status(f"Saved {gexf_file}")

    def save_charts(self) -> None:
        paths = []
        for suffix, figure in (("levels", levels_figure), ("out-links", out_links_figure)):
            path = self.crawl_file.with_name(f"{self.crawl_file.stem}-{suffix}.png")
            save_figure(figure(self.result), path)
            paths.append(path.name)
        self.app.set_status(f"Saved {', '.join(paths)} next to {self.crawl_file.name}")

    def _choose_file(self) -> None:
        name = filedialog.askopenfilename(
            title="Open a saved crawl",
            initialdir=self.app.data_dir if self.app.data_dir.exists() else Path.cwd(),
            filetypes=[("Crawl results", "*.json")],
        )
        if name:
            self.open_file(Path(name))

    def _fill_tree(self, result: CrawlResult) -> None:
        self.tree.delete(*self.tree.get_children())
        children = click_tree(result)
        start = result.config.start_url
        if not children:
            return
        root = self.tree.insert("", "end", text=start, open=True)
        stack = [(root, start)]
        while stack:
            node, url = stack.pop()
            for child in children[url]:
                item = self.tree.insert(node, "end", text=_short_label(child, start))
                stack.append((item, child))


class PagesTab(ttk.Frame):
    """Every visited page with its level, status and link counts. Double-click opens it."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=12)
        self.table = Table(self, on_open=lambda row: row and webbrowser.open(row[-1]))
        self.table.pack(fill="both", expand=True)

    def show(self, result: CrawlResult) -> None:
        levels = shortest_levels(result)
        out_links = Counter(edge.source for edge in result.edges)
        in_links = Counter(edge.target for edge in result.edges)
        self.table.set_rows(
            ["Level", "Status", "Type", "Links out", "Links in", "URL"],
            (
                (
                    levels.get(page.url, "-"),
                    page.status_code,
                    page.content_type,
                    out_links[page.url],
                    in_links[page.url],
                    page.url,
                )
                for page in result.pages
            ),
            widths=[60, 60, 150, 80, 80],
        )


class ContentTab(ttk.Frame):
    """Stored page content: a table of pages and the full text of the selected one."""

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        self.bodies: dict[str, str] = {}
        panes = ttk.PanedWindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        self.table = Table(panes, on_select=self._show_details)
        panes.add(self.table, weight=3)
        self.details = ScrolledText(panes, height=8, wrap="word", relief="flat", borderwidth=8)
        panes.add(self.details, weight=1)
        self.apply_theme()

    def apply_theme(self) -> None:
        colours = self.app.theme_colours()
        self.details.configure(
            background=colours.inputbg, foreground=colours.inputfg, font="TkTextFont"
        )

    def show(self, result: CrawlResult) -> None:
        self.bodies = {content.url: content.body for content in result.contents}
        self.table.set_rows(
            ["URL", "Title", "Description", "Keywords", "Body words"],
            (
                (
                    content.url,
                    content.title,
                    content.description,
                    ", ".join(content.keywords),
                    len(content.body.split()),
                )
                for content in result.contents
            ),
            widths=[300, 220, 260, 200],
        )
        self.details.delete("1.0", "end")
        if not result.contents:
            self.details.insert("end", "This crawl did not save page content.")

    def _show_details(self, row: tuple[str, ...]) -> None:
        if not row:
            return
        url, title, description, keywords, _ = row
        self.details.delete("1.0", "end")
        self.details.insert(
            "end",
            f"{url}\n\nTitle: {title}\nDescription: {description}\nKeywords: {keywords}\n\n"
            f"{self.bodies.get(url, '')}",
        )


def _short_label(url: str, start: str) -> str:
    """Show only the path for pages on the start host, the full URL otherwise."""
    parts = urlsplit(url)
    if parts.netloc != urlsplit(start).netloc:
        return url
    return parts.path + (f"?{parts.query}" if parts.query else "")
