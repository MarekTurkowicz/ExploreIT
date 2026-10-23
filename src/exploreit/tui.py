"""Interactive terminal interface: configure a crawl, watch it run and explore the result."""

import webbrowser
from collections import Counter
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

from pydantic import ValidationError
from rich.markup import escape
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)
from textual.widgets.tree import TreeNode

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult, crawl
from exploreit.export import write_html
from exploreit.frontier import Strategy
from exploreit.graph import click_tree, compute_stats, shortest_levels
from exploreit.models import CrawledPage
from exploreit.parser import LinkMode
from exploreit.urls import Scope

DATA_DIR = Path("data")
BAR_WIDTH = 30


class ExploreApp(App[None]):
    """Crawl a site from a form and browse its structure."""

    TITLE = "ExploreIT"
    _graph_file = Path()
    BINDINGS: ClassVar[list[BindingType]] = [("ctrl+r", "start", "Start crawl")]
    CSS = """
    #form { width: 42; padding: 0 1; border-right: solid $panel; }
    #form Label { margin-top: 1; }
    #form Button { margin-top: 1; width: 100%; }
    #live { padding: 0 1; }
    #log { height: 1fr; border: round $panel; }
    #summary { width: 64; padding: 0 1; }
    #levels { margin-top: 1; }
    #open-graph { margin-top: 1; }
    #tree { border-left: solid $panel; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="crawl"):
            with TabPane("Crawl", id="crawl"), Horizontal():
                with VerticalScroll(id="form"):
                    yield Label("Start URL")
                    yield Input(placeholder="https://example.com", id="url")
                    yield Label("Strategy")
                    yield _choice(Strategy, Strategy.BFS, "strategy")
                    yield Label("Scope")
                    yield _choice(Scope, Scope.SERVER, "scope")
                    yield Label("Links to follow")
                    yield _choice(LinkMode, LinkMode.HYPERLINKS, "links")
                    yield Label("Max depth")
                    yield Input("3", type="integer", id="max-depth")
                    yield Label("Max pages")
                    yield Input("100", type="integer", id="max-pages")
                    yield Label("Delay between requests (s)")
                    yield Input("1.0", type="number", id="delay")
                    yield Checkbox("Respect robots.txt", value=True, id="robots")
                    yield Button("Start crawl", variant="primary", id="start")
                with Vertical(id="live"):
                    yield ProgressBar(id="progress", show_eta=False)
                    yield RichLog(id="log", markup=True)
            with TabPane("Results", id="results"), Horizontal():
                with VerticalScroll(id="summary"):
                    yield DataTable(id="stats", show_header=False, cursor_type="none")
                    yield Static(id="levels")
                    yield Button("Open graph in browser", id="open-graph", disabled=True)
                yield Tree("No crawl yet", id="tree")
            with TabPane("Pages", id="pages"):
                yield DataTable(id="pages-table", cursor_type="row")
        yield Footer()

    @on(Button.Pressed, "#start")
    def action_start(self) -> None:
        try:
            config = self._read_config()
        except ValidationError as error:
            problems = (f"{problem['loc'][0]}: {problem['msg']}" for problem in error.errors())
            self.notify("\n".join(problems), title="Invalid settings", severity="error")
            return

        self.query_one("#start", Button).disabled = True
        self.query_one("#log", RichLog).clear()
        self.query_one("#progress", ProgressBar).update(total=config.max_pages, progress=0)
        self._run_crawl(config)

    def _read_config(self) -> CrawlConfig:
        return CrawlConfig.model_validate(
            {
                "start_url": self.query_one("#url", Input).value,
                "strategy": self.query_one("#strategy", Select).value,
                "scope": self.query_one("#scope", Select).value,
                "link_mode": self.query_one("#links", Select).value,
                "max_depth": self.query_one("#max-depth", Input).value,
                "max_pages": self.query_one("#max-pages", Input).value,
                "delay": self.query_one("#delay", Input).value,
                "respect_robots": self.query_one("#robots", Checkbox).value,
            }
        )

    @work(thread=True, exclusive=True)
    def _run_crawl(self, config: CrawlConfig) -> None:
        result = crawl(config, on_page=lambda page: self.call_from_thread(self._show_page, page))
        path = DATA_DIR / f"crawl-{datetime.now():%Y%m%d-%H%M%S}.json"
        result.save(path)
        write_html(result, path.with_suffix(".html"))
        self.call_from_thread(self._show_result, result, path)

    def _show_page(self, page: CrawledPage) -> None:
        colour = "green" if page.status_code < 400 else "red"
        self.query_one("#log", RichLog).write(
            f"[dim]{page.depth}[/] [{colour}]{page.status_code}[/] {escape(page.url)}"
        )
        self.query_one("#progress", ProgressBar).advance(1)

    @on(Button.Pressed, "#open-graph")
    def _open_graph(self) -> None:
        webbrowser.open(self._graph_file.resolve().as_uri())

    def _show_result(self, result: CrawlResult, path: Path) -> None:
        self._graph_file = path.with_suffix(".html")
        self.query_one("#open-graph", Button).disabled = False
        self._fill_summary(result)
        self._fill_tree(result)
        self._fill_pages(result)
        self.query_one("#start", Button).disabled = False
        self.query_one(TabbedContent).active = "results"
        self.query_one("#tree", Tree).focus()
        self.notify(f"{len(result.pages)} pages saved to {path}", title="Crawl finished")

    def _fill_summary(self, result: CrawlResult) -> None:
        stats = compute_stats(result)
        table = self.query_one("#stats", DataTable)
        table.clear(columns=True)
        table.add_columns("Metric", "Value")
        table.add_rows(stats.summary())

        peak = max(stats.pages_per_level.values(), default=1)
        bars = [
            f"{level:>3} [cyan]{'█' * max(1, round(count / peak * BAR_WIDTH))}[/] {count}"
            for level, count in stats.pages_per_level.items()
        ]
        self.query_one("#levels", Static).update("[b]Pages per level[/]\n" + "\n".join(bars))

    def _fill_tree(self, result: CrawlResult) -> None:
        tree: Tree[None] = self.query_one("#tree", Tree)
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

    def _fill_pages(self, result: CrawlResult) -> None:
        levels = shortest_levels(result)
        out_links = Counter(edge.source for edge in result.edges)
        in_links = Counter(edge.target for edge in result.edges)

        table = self.query_one("#pages-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Level", "Status", "Type", "Links out", "Links in", "URL")
        for page in result.pages:
            table.add_row(
                levels.get(page.url, "-"),
                page.status_code,
                page.content_type,
                out_links[page.url],
                in_links[page.url],
                page.url,
            )


def _choice[E: StrEnum](options: type[E], default: E, widget_id: str) -> Select[E]:
    return Select(
        [(option.value, option) for option in options],
        value=default,
        allow_blank=False,
        id=widget_id,
    )


def _short_label(url: str, start: str) -> str:
    """Show only the path for pages on the start host, the full URL otherwise."""
    parts = urlsplit(url)
    if parts.netloc != urlsplit(start).netloc:
        return url
    return parts.path + (f"?{parts.query}" if parts.query else "")
