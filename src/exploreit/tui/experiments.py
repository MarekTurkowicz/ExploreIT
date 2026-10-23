"""Experiments tab: crawl with many parameter combinations and compare the graphs."""

import webbrowser
from enum import StrEnum
from pathlib import Path

import pandas as pd
from pydantic import ValidationError
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, ProgressBar, RichLog, SelectionList, Static

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.experiments import (
    CHART_FILE,
    SUMMARY_COLUMNS,
    experiment_configs,
    experiment_name,
    run_experiments,
    save_comparison,
)
from exploreit.frontier import Strategy
from exploreit.parser import LinkMode
from exploreit.tui.common import describe_errors, timestamp
from exploreit.tui.crawl import CrawlForm
from exploreit.urls import Scope

SHARED_SETTINGS = {"max_depth", "max_pages", "delay", "timeout", "respect_robots"}


class ExperimentsPane(Vertical):
    """Pick parameter values, run every combination and see them side by side."""

    DEFAULT_CSS = """
    ExperimentsPane { padding: 0 1; }
    ExperimentsPane #choices { height: auto; }
    ExperimentsPane SelectionList { width: 1fr; height: auto; border: round $panel-lighten-2; }
    ExperimentsPane .row { height: auto; margin: 1 0; }
    ExperimentsPane RichLog { height: 8; border: round $panel; }
    """

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        self.data_dir = data_dir
        self.chart = Path()

    def compose(self) -> ComposeResult:
        yield Static(
            "Uses the start URL, depth, page limit and delay from the Crawl tab. "
            "Every combination of the values ticked below is crawled."
        )
        with Horizontal(id="choices"):
            yield _choices(Strategy, "Strategy")
            yield _choices(Scope, "Scope")
            yield _choices(LinkMode, "Links")
        with Horizontal(classes="row"):
            yield Button("Run experiments", variant="primary", id="run")
            yield Button("Open chart", id="open-chart", disabled=True)
        yield ProgressBar(show_eta=False)
        yield RichLog(markup=True)
        yield DataTable(cursor_type="row")

    @on(Button.Pressed, "#run")
    def _start(self) -> None:
        try:
            base = self.app.query_one(CrawlForm).read_config()
        except ValidationError as error:
            self.notify(describe_errors(error), title="Check the Crawl tab", severity="error")
            return
        lists = list(self.query(SelectionList))
        if not all(selection.selected for selection in lists):
            self.notify("Tick at least one value in every column.", severity="error")
            return

        strategies, scopes, link_modes = (selection.selected for selection in lists)
        configs = experiment_configs(
            base.start_url,
            [strategy for strategy in Strategy if strategy in strategies],
            [scope for scope in Scope if scope in scopes],
            [mode for mode in LinkMode if mode in link_modes],
            **base.model_dump(include=SHARED_SETTINGS),
        )
        self.query_one("#run", Button).disabled = True
        self.query_one(RichLog).clear()
        self.query_one(ProgressBar).update(total=len(configs), progress=0)
        self._run(configs, self.data_dir / f"experiments-{timestamp()}")

    @work(thread=True, exclusive=True)
    def _run(self, configs: list[CrawlConfig], out_dir: Path) -> None:
        results = run_experiments(
            configs,
            out_dir,
            on_crawl=lambda config, result: self.app.call_from_thread(self._log, config, result),
        )
        table = save_comparison(results, out_dir)
        self.app.call_from_thread(self._finish, table, out_dir)

    def _log(self, config: CrawlConfig, result: CrawlResult) -> None:
        self.query_one(RichLog).write(
            f"{experiment_name(config)}: {len(result.pages)} pages, {len(result.edges)} links"
        )
        self.query_one(ProgressBar).advance(1)

    def _finish(self, table: pd.DataFrame, out_dir: Path) -> None:
        view = self.query_one(DataTable)
        view.clear(columns=True)
        view.add_columns(*(column.replace("_", " ") for column in SUMMARY_COLUMNS))
        for row in table[SUMMARY_COLUMNS].itertuples(index=False):
            view.add_row(*(f"{value:.1f}" if isinstance(value, float) else value for value in row))

        self.chart = out_dir / CHART_FILE
        self.query_one("#run", Button).disabled = False
        self.query_one("#open-chart", Button).disabled = False
        self.notify(f"Results saved to {out_dir}", title="Experiments finished")

    @on(Button.Pressed, "#open-chart")
    def _open_chart(self) -> None:
        webbrowser.open(self.chart.resolve().as_uri())


def _choices[E: StrEnum](options: type[E], title: str) -> SelectionList[E]:
    selection = SelectionList[E](*((option.value, option, True) for option in options))
    selection.border_title = title
    return selection
