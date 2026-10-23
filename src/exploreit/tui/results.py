"""Results, Pages and Content tabs: everything known about one crawl."""

import webbrowser
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Select, Static, Tree
from textual.widgets.tree import TreeNode

from exploreit.crawler import CrawlResult
from exploreit.export import write_html
from exploreit.graph import click_tree, compute_stats, shortest_levels
from exploreit.plots import plot_levels, plot_out_links
from exploreit.tui.common import CrawlLoaded, saved_crawls, shorten

BAR_WIDTH = 30


class ResultsPane(Horizontal):
    """Graph statistics, pages per level and the site tree of the current crawl."""

    DEFAULT_CSS = """
    ResultsPane #summary { width: 66; padding: 0 1; }
    ResultsPane .row { height: auto; margin-bottom: 1; }
    ResultsPane .row Select { width: 1fr; }
    ResultsPane #levels { margin: 1 0; }
    ResultsPane Tree { border-left: solid $panel; }
    """

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = data_dir
        self.crawl_file = Path()

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="summary"):
            with Horizontal(classes="row"):
                yield Select[Path]([], prompt="Open a saved crawl", id="saved")
                yield Button("Open", id="open-saved")
            yield DataTable(show_header=False, cursor_type="none")
            yield Static(id="levels")
            with Horizontal(classes="row"):
                yield Button("Open graph in browser", id="open-graph", disabled=True)
                yield Button("Save charts (PNG)", id="save-charts", disabled=True)
        yield Tree("No crawl yet")

    def refresh_saved(self) -> None:
        self.query_one("#saved", Select).set_options(saved_crawls(self.data_dir))

    @on(Button.Pressed, "#open-saved")
    def _open_saved(self) -> None:
        path = self.query_one("#saved", Select).value
        if not isinstance(path, Path):
            self.notify("Pick a saved crawl first.", severity="warning")
            return
        try:
            result = CrawlResult.load(path)
        except (OSError, ValidationError) as error:
            self.notify(str(error), title=f"Cannot open {path.name}", severity="error")
            return
        self.post_message(CrawlLoaded(result, path))

    def show(self, result: CrawlResult, path: Path) -> None:
        self.crawl_file = path
        stats = compute_stats(result)

        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("Metric", "Value")
        table.add_rows(stats.summary())

        peak = max(stats.pages_per_level.values(), default=1)
        bars = [
            f"{level:>3} [cyan]{'█' * max(1, round(count / peak * BAR_WIDTH))}[/] {count}"
            for level, count in stats.pages_per_level.items()
        ]
        self.query_one("#levels", Static).update("[b]Pages per level[/]\n" + "\n".join(bars))
        self._fill_tree(result)
        for button in self.query(".row Button"):
            button.disabled = False

    def _fill_tree(self, result: CrawlResult) -> None:
        tree: Tree[None] = self.query_one(Tree)
        tree.clear()
        start = result.config.start_url
        tree.root.set_label(start)
        children = click_tree(result)

        def add(node: TreeNode[None], url: str) -> None:
            for child in children[url]:
                label = _short_label(child, start)
                if children[child]:
                    add(node.add(label), child)
                else:
                    node.add_leaf(label)

        if children:
            add(tree.root, start)
        tree.root.expand()

    @on(Button.Pressed, "#open-graph")
    def _open_graph(self) -> None:
        html_file = self.crawl_file.with_suffix(".html")
        if not html_file.exists():
            write_html(CrawlResult.load(self.crawl_file), html_file)
        webbrowser.open(html_file.resolve().as_uri())

    @on(Button.Pressed, "#save-charts")
    def _save_charts(self) -> None:
        result = CrawlResult.load(self.crawl_file)
        paths = []
        for suffix, plot in (("levels", plot_levels), ("out-links", plot_out_links)):
            path = self.crawl_file.with_name(f"{self.crawl_file.stem}-{suffix}.png")
            plot(result, path)
            paths.append(path.name)
        self.notify(", ".join(paths), title="Charts saved")


class PagesTable(DataTable[object]):
    """Every visited page with its level, status and link counts."""

    def show(self, result: CrawlResult) -> None:
        levels = shortest_levels(result)
        out_links = Counter(edge.source for edge in result.edges)
        in_links = Counter(edge.target for edge in result.edges)
        self.clear(columns=True)
        self.add_columns("Level", "Status", "Type", "Links out", "Links in", "URL")
        for page in result.pages:
            self.add_row(
                levels.get(page.url, "-"),
                page.status_code,
                page.content_type,
                out_links[page.url],
                in_links[page.url],
                page.url,
            )


class ContentTable(DataTable[object]):
    """Title, meta tags and body length of every page with stored content."""

    def show(self, result: CrawlResult) -> None:
        self.clear(columns=True)
        self.add_columns("URL", "Title", "Description", "Keywords", "Body words")
        for content in result.contents:
            self.add_row(
                content.url,
                shorten(content.title, 50),
                shorten(content.description, 60),
                shorten(", ".join(content.keywords), 40),
                len(content.body.split()),
            )


def _short_label(url: str, start: str) -> str:
    """Show only the path for pages on the start host, the full URL otherwise."""
    parts = urlsplit(url)
    if parts.netloc != urlsplit(start).netloc:
        return url
    return parts.path + (f"?{parts.query}" if parts.query else "")
