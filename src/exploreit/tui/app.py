"""The ExploreIT application window: one tab per task."""

from pathlib import Path
from typing import ClassVar

from textual import on
from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.widgets import Footer, Header, TabbedContent, TabPane, Tree

from exploreit.tui.common import CrawlLoaded
from exploreit.tui.compare import ComparePane
from exploreit.tui.crawl import CrawlPane
from exploreit.tui.experiments import ExperimentsPane
from exploreit.tui.results import ContentTable, PagesTable, ResultsPane


class ExploreApp(App[None]):
    """Crawl sites, explore their link graph, run experiments and compare content."""

    TITLE = "ExploreIT"
    BINDINGS: ClassVar[list[BindingType]] = [("ctrl+r", "start_crawl", "Start crawl")]

    def __init__(self, data_dir: Path = Path("data")) -> None:
        super().__init__()
        self.data_dir = data_dir

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="crawl"):
            with TabPane("Crawl", id="crawl"):
                yield CrawlPane(self.data_dir)
            with TabPane("Results", id="results"):
                yield ResultsPane(self.data_dir)
            with TabPane("Pages", id="pages"):
                yield PagesTable(cursor_type="row")
            with TabPane("Content", id="content"):
                yield ContentTable(cursor_type="row")
            with TabPane("Experiments", id="experiments"):
                yield ExperimentsPane(self.data_dir)
            with TabPane("Compare", id="compare"):
                yield ComparePane(self.data_dir)
        yield Footer()

    def action_start_crawl(self) -> None:
        self.query_one(CrawlPane).start_crawl()

    @on(TabbedContent.TabActivated)
    def _refresh_saved_crawls(self) -> None:
        self.query_one(ResultsPane).refresh_saved()
        self.query_one(ComparePane).refresh_saved()

    @on(CrawlLoaded)
    def _show_crawl(self, message: CrawlLoaded) -> None:
        self.query_one(ResultsPane).show(message.result, message.path)
        self.query_one(PagesTable).show(message.result)
        self.query_one(ContentTable).show(message.result)
        self.query_one(TabbedContent).active = "results"
        # Move focus into the Results tab, otherwise the tab holding focus stays active.
        self.query_one(ResultsPane).query_one(Tree).focus()
        self.notify(f"{len(message.result.pages)} pages · {message.path}", title="Crawl loaded")
