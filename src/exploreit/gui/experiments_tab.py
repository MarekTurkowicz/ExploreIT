"""Experiments tab: crawl with many parameter combinations and compare the graphs."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from enum import StrEnum
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

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
from exploreit.graph import format_duration
from exploreit.gui.widgets import ChartPanel, Table, describe_errors, show_error, timestamp
from exploreit.parser import LinkMode
from exploreit.urls import Scope

if TYPE_CHECKING:
    import pandas as pd

    from exploreit.gui.app import ExploreApp

SHARED_SETTINGS = {"max_depth", "max_pages", "delay", "timeout", "respect_robots"}


class ExperimentsTab(ttk.Frame):
    """Tick parameter values, crawl every combination and see them side by side."""

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        self.running = False
        self._stop_requested = threading.Event()
        self._started = 0.0
        self.boxes: list[ttk.Checkbutton] = []  # locked while experiments run
        ttk.Label(
            self,
            text="Uses the start URL, depth, page limit and delay from the Crawl tab. "
            "Every combination of the values ticked below is crawled.",
        ).pack(anchor="w")

        groups = ttk.Frame(self)
        groups.pack(fill="x", pady=10)
        self.strategies = self._checkboxes(groups, "Strategy", Strategy)
        self.scopes = self._checkboxes(groups, "Scope", Scope)
        self.link_modes = self._checkboxes(groups, "Links", LinkMode)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 10))
        self.run_button = tb.Button(
            actions, text="Run experiments", command=self.run, bootstyle="primary"
        )
        self.run_button.pack(side="left")
        self.stop_button = tb.Button(actions, text="Stop", command=self.stop, bootstyle="danger")
        self.stop_button.pack(side="left", padx=(8, 0))
        self.stop_button.state(["disabled"])
        self.progress = tb.Progressbar(actions, mode="determinate", bootstyle="striped")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)
        self.current = ttk.Label(actions, text="", width=46)
        self.current.pack(side="left")

        panes = ttk.PanedWindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        self.table = Table(panes, height=8)
        panes.add(self.table, weight=1)
        self.chart = ChartPanel(panes)
        panes.add(self.chart, weight=2)

    def _checkboxes[E: StrEnum](
        self, master: ttk.Frame, title: str, options: type[E]
    ) -> dict[E, tk.BooleanVar]:
        frame = ttk.LabelFrame(master, text=title, padding=10)
        frame.pack(side="left", fill="y", padx=(0, 12))
        ticks = {option: tk.BooleanVar(value=True) for option in options}
        for option, variable in ticks.items():
            box = ttk.Checkbutton(frame, text=option.value, variable=variable)
            box.pack(anchor="w", pady=2)
            self.boxes.append(box)
        return ticks

    def set_locked(self, locked: bool) -> None:
        state = ["disabled"] if locked else ["!disabled"]
        for widget in [*self.boxes, self.run_button]:
            widget.state(state)

    def stop(self) -> None:
        """Finish the running crawl early, save it, and skip the remaining ones."""
        if self.running and not self._stop_requested.is_set():
            self._stop_requested.set()
            self.stop_button.state(["disabled"])
            self.app.set_status("Stopping after the current page …")

    def run(self) -> None:
        if self.running or self.app.crawl_tab.running:
            return
        try:
            base = self.app.crawl_tab.read_config()
        except ValueError as error:
            messagebox.showerror("Check the Crawl tab", describe_errors(error))
            return
        chosen = [_ticked(ticks) for ticks in (self.strategies, self.scopes, self.link_modes)]
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
        self.running = True
        self._stop_requested.clear()
        self.app.set_busy(True)
        self.stop_button.state(["!disabled"])
        self._started = time.monotonic()
        self.progress.configure(maximum=len(configs), value=0)
        self.current.configure(text=f"0 of {len(configs)} crawls")
        self.app.set_status(f"Running {len(configs)} crawls into {out_dir} …")
        self.app.tasks.run(lambda: self._experiment(configs, out_dir), self._finish, self._failed)

    def _experiment(self, configs: list[CrawlConfig], out_dir: Path) -> tuple[pd.DataFrame, Path]:
        """Runs in a background thread."""
        results = run_experiments(
            configs,
            out_dir,
            on_crawl=lambda c, r: self.app.tasks.call(self._crawled, c, r),
            should_stop=self._stop_requested.is_set,
        )
        return save_comparison(results, out_dir), out_dir

    def _crawled(self, config: CrawlConfig, result: CrawlResult) -> None:
        self.progress.step(1)
        elapsed = format_duration(time.monotonic() - self._started)
        self.current.configure(
            text=f"⏱ {elapsed} · {experiment_name(config)}: {len(result.pages)} pages"
        )

    def _stop(self) -> None:
        self.running = False
        self.stop_button.state(["disabled"])
        self.app.set_busy(False)

    def _failed(self, error: Exception) -> None:
        self._stop()
        show_error(error)

    def _finish(self, outcome: tuple[pd.DataFrame, Path]) -> None:
        table, out_dir = outcome
        self._stop()
        mark = "■ Stopped" if self._stop_requested.is_set() else "✔"
        elapsed = format_duration(time.monotonic() - self._started)
        self.current.configure(text=f"{mark} {elapsed} · {len(table)} crawls")
        rows = (
            [f"{value:.1f}" if isinstance(value, float) else value for value in row]
            for row in table[SUMMARY_COLUMNS].itertuples(index=False)
        )
        self.table.set_rows([c.replace("_", " ") for c in SUMMARY_COLUMNS], rows, widths=[90] * 11)
        from exploreit.plots import comparison_figure

        self.chart.show(comparison_figure(table))
        self.app.set_status(f"Experiments saved to {out_dir} (summary.csv, comparison.png)")


def _ticked[E: StrEnum](ticks: dict[E, tk.BooleanVar]) -> list[E]:
    return [option for option, variable in ticks.items() if variable.get()]
