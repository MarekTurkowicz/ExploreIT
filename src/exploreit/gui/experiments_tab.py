"""Experiments tab: crawl with many parameter combinations and compare the graphs."""

from __future__ import annotations

import tkinter as tk
from enum import StrEnum
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

import pandas as pd
from pydantic import ValidationError

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.experiments import (
    SUMMARY_COLUMNS,
    experiment_configs,
    experiment_name,
    run_experiments,
    save_comparison,
)
from exploreit.frontier import Strategy
from exploreit.gui.widgets import ChartPanel, Table, describe_errors, timestamp
from exploreit.parser import LinkMode
from exploreit.plots import comparison_figure
from exploreit.urls import Scope

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp

SHARED_SETTINGS = {"max_depth", "max_pages", "delay", "timeout", "respect_robots"}


class ExperimentsTab(ttk.Frame):
    """Tick parameter values, crawl every combination and see them side by side."""

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        ttk.Label(
            self,
            text="Uses the start URL, depth, page limit and delay from the Crawl tab. "
            "Every combination of the values ticked below is crawled.",
        ).pack(anchor="w")

        groups = ttk.Frame(self)
        groups.pack(fill="x", pady=8)
        self.strategies = _checkboxes(groups, "Strategy", Strategy)
        self.scopes = _checkboxes(groups, "Scope", Scope)
        self.link_modes = _checkboxes(groups, "Links", LinkMode)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 8))
        self.run_button = ttk.Button(
            actions, text="Run experiments", style="Accent.TButton", command=self.run
        )
        self.run_button.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)
        self.current = ttk.Label(actions, text="", width=40)
        self.current.pack(side="left")

        panes = ttk.PanedWindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        self.table = Table(panes, height=8)
        panes.add(self.table, weight=1)
        self.chart = ChartPanel(panes)
        panes.add(self.chart, weight=2)

    def run(self) -> None:
        if str(self.run_button["state"]) == "disabled":
            return
        try:
            base = self.app.crawl_tab.read_config()
        except ValidationError as error:
            messagebox.showerror("Check the Crawl tab", describe_errors(error))
            return
        chosen = [_ticked(boxes) for boxes in (self.strategies, self.scopes, self.link_modes)]
        if not all(chosen):
            messagebox.showerror("Experiments", "Tick at least one value in every group.")
            return

        strategies, scopes, link_modes = chosen
        configs = experiment_configs(
            base.start_url,
            strategies,
            scopes,
            link_modes,
            **base.model_dump(include=SHARED_SETTINGS),
        )
        out_dir = self.app.data_dir / f"experiments-{timestamp()}"
        self.run_button.state(["disabled"])
        self.progress.configure(maximum=len(configs), value=0)
        self.app.set_status(f"Running {len(configs)} crawls into {out_dir} …")
        self.app.tasks.run(lambda: self._experiment(configs, out_dir), self._finish)

    def _experiment(self, configs: list[CrawlConfig], out_dir: Path) -> tuple[pd.DataFrame, Path]:
        """Runs in a background thread."""
        results = run_experiments(
            configs, out_dir, on_crawl=lambda c, r: self.app.tasks.call(self._crawled, c, r)
        )
        return save_comparison(results, out_dir), out_dir

    def _crawled(self, config: CrawlConfig, result: CrawlResult) -> None:
        self.progress.step(1)
        self.current.configure(text=f"{experiment_name(config)}: {len(result.pages)} pages")

    def _finish(self, outcome: tuple[pd.DataFrame, Path]) -> None:
        table, out_dir = outcome
        self.run_button.state(["!disabled"])
        rows = (
            [f"{value:.1f}" if isinstance(value, float) else value for value in row]
            for row in table[SUMMARY_COLUMNS].itertuples(index=False)
        )
        self.table.set_rows([c.replace("_", " ") for c in SUMMARY_COLUMNS], rows, widths=[80] * 10)
        self.chart.show(comparison_figure(table))
        self.app.set_status(f"Experiments saved to {out_dir} (summary.csv, comparison.png)")


def _checkboxes[E: StrEnum](
    master: ttk.Frame, title: str, options: type[E]
) -> dict[E, tk.BooleanVar]:
    frame = ttk.LabelFrame(master, text=title, padding=8)
    frame.pack(side="left", fill="y", padx=(0, 10))
    boxes = {option: tk.BooleanVar(value=True) for option in options}
    for option, variable in boxes.items():
        ttk.Checkbutton(frame, text=option.value, variable=variable).pack(anchor="w")
    return boxes


def _ticked[E: StrEnum](boxes: dict[E, tk.BooleanVar]) -> list[E]:
    return [option for option, variable in boxes.items() if variable.get()]
