"""Compare tab: page content stored by two crawls, side by side."""

from pathlib import Path

from pydantic import ValidationError
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Select, Static

from exploreit.compare import comparison_rows
from exploreit.crawler import CrawlResult
from exploreit.tui.common import saved_crawls


class ComparePane(Vertical):
    """Pick two saved crawls and compare the content databases they hold."""

    DEFAULT_CSS = """
    ComparePane { padding: 0 1; }
    ComparePane .row { height: auto; margin: 1 0; }
    ComparePane .row Select { width: 1fr; }
    """

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = data_dir

    def compose(self) -> ComposeResult:
        yield Static("Crawls made with 'Save page content' can be compared here.")
        with Horizontal(classes="row"):
            yield Select[Path]([], prompt="First crawl", id="first")
            yield Select[Path]([], prompt="Second crawl", id="second")
            yield Button("Compare", variant="primary", id="compare")
        yield DataTable(cursor_type="row")

    def refresh_saved(self) -> None:
        options = saved_crawls(self.data_dir)
        for select in self.query(Select):
            select.set_options(options)

    @on(Button.Pressed, "#compare")
    def _compare(self) -> None:
        first_file = self.query_one("#first", Select).value
        second_file = self.query_one("#second", Select).value
        if not isinstance(first_file, Path) or not isinstance(second_file, Path):
            self.notify("Pick two saved crawls.", severity="warning")
            return
        try:
            first, second = CrawlResult.load(first_file), CrawlResult.load(second_file)
        except (OSError, ValidationError) as error:
            self.notify(str(error), title="Cannot open crawl", severity="error")
            return
        if not first.contents or not second.contents:
            self.notify("A crawl without stored content shows zeros.", severity="warning")

        table = self.query_one(DataTable)
        table.clear(columns=True)
        labels = (str(path.relative_to(self.data_dir)) for path in (first_file, second_file))
        table.add_columns("", *labels)
        table.add_rows(comparison_rows(first, second))
