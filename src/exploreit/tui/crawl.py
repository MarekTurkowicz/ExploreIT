"""Crawl tab: the settings form and the live log of a running crawl."""

from pathlib import Path

from pydantic import ValidationError
from rich.markup import escape
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    SelectionList,
)

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult, crawl
from exploreit.export import write_html
from exploreit.frontier import Strategy
from exploreit.models import CrawledPage
from exploreit.parser import LinkMode
from exploreit.storage import ContentField, write_csv, write_sqlite
from exploreit.tui.common import CrawlLoaded, describe_errors, enum_select, timestamp
from exploreit.urls import Scope

SEPARATORS = [("comma  ,", ","), ("semicolon  ;", ";"), ("tab", "\t")]


class CrawlForm(VerticalScroll):
    """Every crawl setting, including how page content is saved."""

    DEFAULT_CSS = """
    CrawlForm { width: 44; padding: 0 1; border-right: solid $panel; }
    CrawlForm Label { margin-top: 1; }
    CrawlForm SelectionList { height: auto; }
    CrawlForm #start { margin-top: 1; width: 100%; }
    """

    def compose(self) -> ComposeResult:
        yield Label("Start URL")
        yield Input(placeholder="https://example.com", id="url")
        yield Label("Strategy")
        yield enum_select(Strategy, Strategy.BFS, "strategy")
        yield Label("Scope")
        yield enum_select(Scope, Scope.SERVER, "scope")
        yield Label("Links to follow")
        yield enum_select(LinkMode, LinkMode.HYPERLINKS, "links")
        yield Label("Max depth (0 = start page only)")
        yield Input("3", type="integer", id="max-depth")
        yield Label("Max pages")
        yield Input("100", type="integer", id="max-pages")
        yield Label("Delay between requests (s)")
        yield Input("1.0", type="number", id="delay")
        yield Checkbox("Respect robots.txt", value=True, id="robots")
        yield Checkbox("Save page content (CSV, SQLite)", id="store-content")
        yield Label("CSV fields")
        yield SelectionList[ContentField](
            *((field.value, field, True) for field in ContentField), id="fields"
        )
        yield Label("CSV separator")
        yield Select(SEPARATORS, value=",", allow_blank=False, id="separator")
        yield Button("Start crawl", variant="primary", id="start")

    def read_config(self) -> CrawlConfig:
        """Return the settings as a crawl config.

        Raises:
            ValidationError: If a setting is missing or invalid.
        """
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
                "store_content": self.query_one("#store-content", Checkbox).value,
            }
        )

    def csv_fields(self) -> list[ContentField]:
        selected = self.query_one("#fields", SelectionList).selected
        return [field for field in ContentField if field in selected]

    def csv_separator(self) -> str:
        return str(self.query_one("#separator", Select).value)


class CrawlPane(Horizontal):
    """Settings on the left, progress and visited pages on the right."""

    DEFAULT_CSS = """
    CrawlPane #live { padding: 0 1; }
    CrawlPane RichLog { height: 1fr; border: round $panel; }
    """

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = data_dir

    def compose(self) -> ComposeResult:
        yield CrawlForm()
        with Vertical(id="live"):
            yield ProgressBar(show_eta=False)
            yield RichLog(markup=True)

    @on(Button.Pressed, "#start")
    def start_crawl(self) -> None:
        start = self.query_one("#start", Button)
        if start.disabled:
            return  # a crawl is already running
        form = self.query_one(CrawlForm)
        try:
            config = form.read_config()
        except ValidationError as error:
            self.notify(describe_errors(error), title="Invalid settings", severity="error")
            return
        fields = form.csv_fields()
        if config.store_content and not fields:
            self.notify("Pick at least one CSV field.", severity="error")
            return

        start.disabled = True
        self.query_one(RichLog).clear()
        self.query_one(ProgressBar).update(total=config.max_pages, progress=0)
        self._crawl(config, fields, form.csv_separator())

    @work(thread=True, exclusive=True)
    def _crawl(self, config: CrawlConfig, fields: list[ContentField], separator: str) -> None:
        result = crawl(config, on_page=lambda page: self.app.call_from_thread(self._log, page))
        path = self.data_dir / f"crawl-{timestamp()}.json"
        _save_outputs(result, path, fields, separator)
        self.app.call_from_thread(self._finish, result, path)

    def _log(self, page: CrawledPage) -> None:
        colour = "green" if page.status_code < 400 else "red"
        self.query_one(RichLog).write(
            f"[dim]{page.depth}[/] [{colour}]{page.status_code}[/] {escape(page.url)}"
        )
        self.query_one(ProgressBar).advance(1)

    def _finish(self, result: CrawlResult, path: Path) -> None:
        self.query_one("#start", Button).disabled = False
        self.post_message(CrawlLoaded(result, path))


def _save_outputs(
    result: CrawlResult, path: Path, fields: list[ContentField], separator: str
) -> None:
    """Save the crawl as JSON and HTML graph, plus CSV and SQLite when content was kept."""
    result.save(path)
    write_html(result, path.with_suffix(".html"))
    if result.contents:
        write_csv(result.contents, path.with_suffix(".csv"), fields, separator)
        write_sqlite(result, path.with_suffix(".sqlite"))
