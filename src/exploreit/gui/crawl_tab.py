"""Crawl tab: every crawl setting and a live log of visited pages."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import TYPE_CHECKING

from pydantic import ValidationError

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult, crawl
from exploreit.export import write_html
from exploreit.frontier import Strategy
from exploreit.gui.widgets import describe_errors, timestamp
from exploreit.models import CrawledPage
from exploreit.parser import LinkMode
from exploreit.storage import ContentField, write_csv, write_sqlite
from exploreit.urls import Scope

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp

SEPARATORS = {"comma ( , )": ",", "semicolon ( ; )": ";", "tab": "\t"}


class CrawlTab(ttk.Frame):
    """Settings on top, progress and the log of visited pages below."""

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        self.url = tk.StringVar()
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
        self._build()

    def _build(self) -> None:
        settings = ttk.LabelFrame(self, text="Crawl settings", padding=10)
        settings.pack(fill="x")
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Start URL").grid(row=0, column=0, sticky="w", pady=4)
        url = ttk.Entry(settings, textvariable=self.url)
        url.grid(row=0, column=1, columnspan=5, sticky="ew", pady=4)
        url.insert(0, "https://")

        choices = [
            ("Strategy", self.strategy, Strategy),
            ("Scope", self.scope, Scope),
            ("Links to follow", self.links, LinkMode),
        ]
        for column, (label, variable, options) in enumerate(choices):
            ttk.Label(settings, text=label).grid(row=1, column=column * 2, sticky="w", pady=4)
            ttk.Combobox(
                settings,
                textvariable=variable,
                values=[option.value for option in options],
                state="readonly",
                width=14,
            ).grid(row=1, column=column * 2 + 1, sticky="w", padx=(6, 18), pady=4)

        numbers = [
            ("Max depth (0 = start page only)", self.max_depth, 0, 50, 1),
            ("Max pages", self.max_pages, 1, 100_000, 10),
            ("Delay between requests (s)", self.delay, 0, 30, 0.5),
        ]
        for column, (label, number, low, high, step) in enumerate(numbers):
            ttk.Label(settings, text=label).grid(row=2, column=column * 2, sticky="w", pady=4)
            ttk.Spinbox(
                settings, textvariable=number, from_=low, to=high, increment=step, width=10
            ).grid(row=2, column=column * 2 + 1, sticky="w", padx=(6, 18), pady=4)

        ttk.Checkbutton(settings, text="Respect robots.txt", variable=self.respect_robots).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=4
        )

        content = ttk.LabelFrame(self, text="Page content (title, meta tags, body)", padding=10)
        content.pack(fill="x", pady=(10, 0))
        ttk.Checkbutton(
            content, text="Save page content as CSV and SQLite", variable=self.store_content
        ).grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(content, text="CSV fields").grid(row=1, column=0, sticky="w", pady=4)
        for column, (field, ticked) in enumerate(self.fields.items(), start=1):
            ttk.Checkbutton(content, text=field.value, variable=ticked).grid(
                row=1, column=column, sticky="w", padx=(0, 10)
            )
        ttk.Label(content, text="Separator").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(
            content, textvariable=self.separator, values=list(SEPARATORS), state="readonly"
        ).grid(row=2, column=1, columnspan=3, sticky="w")

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=10)
        self.start_button = ttk.Button(
            actions, text="Start crawl  (Ctrl+R)", style="Accent.TButton", command=self.start
        )
        self.start_button.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))

        self.log = ScrolledText(self, height=12, wrap="none", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("ok", foreground="#0ca30c")
        self.log.tag_configure("error", foreground="#d03b3b")
        self.log.tag_configure("dim", foreground="#898781")

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
        if str(self.start_button["state"]) == "disabled":
            return  # a crawl is already running
        try:
            config = self.read_config()
        except ValidationError as error:
            messagebox.showerror("Invalid settings", describe_errors(error))
            return
        fields = [field for field, variable in self.fields.items() if variable.get()]
        if config.store_content and not fields:
            messagebox.showerror("Invalid settings", "Pick at least one CSV field.")
            return

        separator = SEPARATORS[self.separator.get()]
        self.start_button.state(["disabled"])
        self.progress.configure(maximum=config.max_pages, value=0)
        self.log.delete("1.0", "end")
        self.app.set_status(f"Crawling {config.start_url} …")
        self.app.tasks.run(lambda: self._crawl(config, fields, separator), self._finish)

    def _crawl(
        self, config: CrawlConfig, fields: list[ContentField], separator: str
    ) -> tuple[CrawlResult, Path]:
        """Runs in a background thread."""
        result = crawl(config, on_page=lambda page: self.app.tasks.call(self._log_page, page))
        path = self.app.data_dir / f"crawl-{timestamp()}.json"
        result.save(path)
        write_html(result, path.with_suffix(".html"))
        if result.contents:
            write_csv(result.contents, path.with_suffix(".csv"), fields, separator)
            write_sqlite(result, path.with_suffix(".sqlite"))
        return result, path

    def _log_page(self, page: CrawledPage) -> None:
        self.log.insert("end", f"{page.depth}  ", "dim")
        self.log.insert("end", f"{page.status_code}  ", "ok" if page.status_code < 400 else "error")
        self.log.insert("end", f"{page.url}\n")
        self.log.see("end")
        self.progress.step(1)

    def _finish(self, outcome: tuple[CrawlResult, Path]) -> None:
        result, path = outcome
        self.start_button.state(["!disabled"])
        for url, reason in result.failed.items():
            self.log.insert("end", f"failed  {url}: {reason}\n", "error")
        self.app.show_crawl(result, path)
