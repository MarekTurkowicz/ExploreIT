"""Crawl tab: every crawl setting, a timer and a live log of visited pages."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import TYPE_CHECKING

import ttkbootstrap as tb
from pydantic import ValidationError

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult, crawl
from exploreit.export import write_html
from exploreit.frontier import Strategy
from exploreit.graph import format_duration
from exploreit.gui.widgets import describe_errors, show_error, timestamp
from exploreit.models import CrawledPage
from exploreit.parser import LinkMode
from exploreit.storage import ContentField, write_csv, write_sqlite
from exploreit.urls import Scope

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp

SEPARATORS = {"comma ( , )": ",", "semicolon ( ; )": ";", "tab": "\t"}
TIMER_MS = 250


class CrawlTab(ttk.Frame):
    """Settings on top, progress, timer and the log of visited pages below."""

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        self.url = tk.StringVar(value="https://")
        self.strategy = tk.StringVar(value=Strategy.BFS)
        self.scope = tk.StringVar(value=Scope.SERVER)
        self.links = tk.StringVar(value=LinkMode.HYPERLINKS)
        self.max_depth = tk.StringVar(value="3")
        self.max_pages = tk.StringVar(value="100")
        self.delay = tk.StringVar(value="1.0")
        self.respect_robots = tk.BooleanVar(value=True)
        self.store_content = tk.BooleanVar(value=False)
        self.fields = {field: tk.BooleanVar(value=True) for field in ContentField}
        self.separator = tk.StringVar(value=next(iter(SEPARATORS)))
        self.timer = tk.StringVar(value="Not started")
        self.running = False
        self._stop_requested = threading.Event()
        self._started = 0.0
        self._pages = 0
        self.inputs: list[ttk.Widget] = []  # everything locked while a crawl runs
        self._build()

    def _build(self) -> None:
        settings = ttk.LabelFrame(self, text="Crawl settings", padding=12)
        settings.pack(fill="x")
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Start URL").grid(row=0, column=0, sticky="w", pady=6)
        self._add(ttk.Entry(settings, textvariable=self.url)).grid(
            row=0, column=1, columnspan=5, sticky="ew", pady=6
        )

        choices = [
            ("Strategy", self.strategy, Strategy),
            ("Scope", self.scope, Scope),
            ("Links to follow", self.links, LinkMode),
        ]
        for column, (label, variable, options) in enumerate(choices):
            ttk.Label(settings, text=label).grid(row=1, column=column * 2, sticky="w", pady=6)
            box = ttk.Combobox(
                settings,
                textvariable=variable,
                values=[option.value for option in options],
                state="readonly",
                width=14,
            )
            self._add(box).grid(row=1, column=column * 2 + 1, sticky="w", padx=(8, 24), pady=6)

        numbers = [
            ("Max depth (0 = start page only)", self.max_depth, 0, 50, 1),
            ("Max pages", self.max_pages, 1, 100_000, 10),
            ("Delay between requests (s)", self.delay, 0, 30, 0.5),
        ]
        for column, (label, number, low, high, step) in enumerate(numbers):
            ttk.Label(settings, text=label).grid(row=2, column=column * 2, sticky="w", pady=6)
            spin = ttk.Spinbox(
                settings, textvariable=number, from_=low, to=high, increment=step, width=10
            )
            self._add(spin).grid(row=2, column=column * 2 + 1, sticky="w", padx=(8, 24), pady=6)

        robots = tb.Checkbutton(
            settings,
            text="Respect robots.txt",
            variable=self.respect_robots,
            bootstyle="round-toggle",
        )
        self._add(robots).grid(row=3, column=0, columnspan=2, sticky="w", pady=6)

        content = ttk.LabelFrame(self, text="Page content (title, meta tags, body)", padding=12)
        content.pack(fill="x", pady=(10, 0))
        save = tb.Checkbutton(
            content,
            text="Save page content as CSV and SQLite",
            variable=self.store_content,
            bootstyle="round-toggle",
        )
        self._add(save).grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(content, text="CSV fields").grid(row=1, column=0, sticky="w", pady=6)
        for column, (field, ticked) in enumerate(self.fields.items(), start=1):
            tick = ttk.Checkbutton(content, text=field.value, variable=ticked)
            self._add(tick).grid(row=1, column=column, sticky="w", padx=(8, 12))
        ttk.Label(content, text="Separator").grid(row=2, column=0, sticky="w", pady=6)
        separator = ttk.Combobox(
            content, textvariable=self.separator, values=list(SEPARATORS), state="readonly"
        )
        self._add(separator).grid(row=2, column=1, columnspan=3, sticky="w", padx=8)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=12)
        self.start_button = tb.Button(
            actions, text="Start crawl  (Ctrl+R)", command=self.start, bootstyle="primary"
        )
        self.start_button.pack(side="left")
        self.stop_button = tb.Button(
            actions, text="Stop  (Esc)", command=self.stop, bootstyle="danger"
        )
        self.stop_button.pack(side="left", padx=(8, 0))
        self.stop_button.state(["disabled"])
        self.progress = tb.Progressbar(actions, mode="determinate", bootstyle="striped")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)
        ttk.Label(actions, textvariable=self.timer, width=36, font="TkHeadingFont").pack(
            side="left"
        )

        self.log = ScrolledText(self, height=12, wrap="none", relief="flat", borderwidth=8)
        self.log.pack(fill="both", expand=True)
        self.apply_theme()

    def _add[W: ttk.Widget](self, widget: W) -> W:
        self.inputs.append(widget)
        return widget

    def apply_theme(self) -> None:
        colours = self.app.theme_colours()
        self.log.configure(
            background=colours.inputbg,
            foreground=colours.inputfg,
            insertbackground=colours.inputfg,
            font="TkFixedFont",
        )
        self.log.tag_configure("ok", foreground=colours.success)
        self.log.tag_configure("error", foreground=colours.danger)
        self.log.tag_configure("dim", foreground=colours.secondary)

    def set_locked(self, locked: bool) -> None:
        state = ["disabled"] if locked else ["!disabled"]
        for widget in [*self.inputs, self.start_button]:
            widget.state(state)

    def stop(self) -> None:
        """Ask the running crawl to finish after the current page."""
        if self.running and not self._stop_requested.is_set():
            self._stop_requested.set()
            self.stop_button.state(["disabled"])
            self.app.set_status("Stopping after the current page …")

    def read_config(self) -> CrawlConfig:
        """Return the settings as a crawl config.

        Raises:
            ValidationError: If a setting is missing or invalid.
        """
        return CrawlConfig.model_validate(
            {
                "start_url": self.url.get().strip(),
                "strategy": self.strategy.get(),
                "scope": self.scope.get(),
                "link_mode": self.links.get(),
                "max_depth": self.max_depth.get(),
                "max_pages": self.max_pages.get(),
                "delay": self.delay.get(),
                "respect_robots": self.respect_robots.get(),
                "store_content": self.store_content.get(),
            }
        )

    def start(self) -> None:
        if self.running or self.app.experiments_tab.running:
            return
        try:
            config = self.read_config()
        except ValidationError as error:
            messagebox.showerror("Invalid settings", describe_errors(error))
            return
        fields = [field for field, ticked in self.fields.items() if ticked.get()]
        if config.store_content and not fields:
            messagebox.showerror("Invalid settings", "Pick at least one CSV field.")
            return

        separator = SEPARATORS[self.separator.get()]
        self.running = True
        self._stop_requested.clear()
        self.app.set_busy(True)
        self.stop_button.state(["!disabled"])
        self.progress.configure(maximum=config.max_pages, value=0)
        self.log.delete("1.0", "end")
        self._started, self._pages = time.monotonic(), 0
        self._tick()
        self.app.set_status(f"Crawling {config.start_url} …")
        self.app.tasks.run(
            lambda: self._crawl(config, fields, separator), self._finish, self._failed
        )

    def _crawl(
        self, config: CrawlConfig, fields: list[ContentField], separator: str
    ) -> tuple[CrawlResult, Path]:
        """Runs in a background thread."""
        result = crawl(
            config,
            on_page=lambda page: self.app.tasks.call(self._log_page, page),
            should_stop=self._stop_requested.is_set,
        )
        path = self.app.data_dir / f"crawl-{timestamp()}.json"
        result.save(path)
        write_html(result, path.with_suffix(".html"))
        if result.contents:
            write_csv(result.contents, path.with_suffix(".csv"), fields, separator)
            write_sqlite(result, path.with_suffix(".sqlite"))
        return result, path

    def _tick(self) -> None:
        if not self.running:
            return
        elapsed = time.monotonic() - self._started
        rate = self._pages / elapsed if elapsed else 0.0
        self.timer.set(f"⏱ {format_duration(elapsed)} · {self._pages} pages · {rate:.1f}/s")
        self.after(TIMER_MS, self._tick)

    def _log_page(self, page: CrawledPage) -> None:
        self._pages += 1
        self.log.insert("end", f"{page.depth}  ", "dim")
        self.log.insert("end", f"{page.status_code}  ", "ok" if page.status_code < 400 else "error")
        self.log.insert("end", f"{page.url}\n")
        self.log.see("end")
        self.progress.step(1)

    def _stop(self) -> None:
        self.running = False
        self.stop_button.state(["disabled"])
        self.app.set_busy(False)

    def _finish(self, outcome: tuple[CrawlResult, Path]) -> None:
        result, path = outcome
        self._stop()
        rate = len(result.pages) / result.duration if result.duration else 0.0
        mark = "■ Stopped" if result.stopped else "✔"
        self.timer.set(
            f"{mark} {format_duration(result.duration)} · {len(result.pages)} pages · {rate:.1f}/s"
        )
        for url, reason in result.failed.items():
            self.log.insert("end", f"failed  {url}: {reason}\n", "error")
        self.app.show_crawl(result, path)

    def _failed(self, error: Exception) -> None:
        self._stop()
        self.timer.set("Crawl failed")
        show_error(error)
