"""Compare tab: page content stored by two crawls, side by side."""

from __future__ import annotations

import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from pydantic import ValidationError

from exploreit.compare import comparison_rows
from exploreit.crawler import CrawlResult
from exploreit.gui.widgets import Table, saved_crawls

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp


class CompareTab(ttk.Frame):
    """Pick two saved crawls and compare the content databases they hold."""

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        self.first = tk.StringVar()
        self.second = tk.StringVar()
        ttk.Label(self, text="Crawls made with 'Save page content' can be compared here.").pack(
            anchor="w"
        )

        form = ttk.Frame(self)
        form.pack(fill="x", pady=8)
        form.columnconfigure(1, weight=1)
        self.pickers = []
        for row, (label, variable) in enumerate((("First", self.first), ("Second", self.second))):
            ttk.Label(form, text=f"{label} crawl").grid(row=row, column=0, sticky="w", pady=4)
            picker = ttk.Combobox(form, textvariable=variable)
            picker.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
            self.pickers.append(picker)
            ttk.Button(form, text="Browse…", command=partial(self._browse, variable)).grid(
                row=row, column=2, pady=4
            )
        ttk.Button(form, text="Compare", style="Accent.TButton", command=self.compare).grid(
            row=2, column=1, sticky="w", padx=6, pady=(6, 0)
        )
        self.table = Table(self)
        self.table.pack(fill="both", expand=True)

    def refresh(self) -> None:
        options = saved_crawls(self.app.data_dir)
        for picker in self.pickers:
            picker.configure(values=options)

    def compare(self) -> None:
        files = [self._path(variable.get()) for variable in (self.first, self.second)]
        if not all(path.is_file() for path in files):
            messagebox.showerror("Compare", "Pick two saved crawls.")
            return
        try:
            first, second = (CrawlResult.load(path) for path in files)
        except (OSError, ValidationError) as error:
            messagebox.showerror("Cannot open crawl", str(error))
            return
        names = [path.name for path in files]
        self.table.set_rows(["", *names], comparison_rows(first, second), widths=[200, 300])
        if not first.contents or not second.contents:
            self.app.set_status("A crawl without saved page content shows zeros.")

    def _path(self, value: str) -> Path:
        path = Path(value.strip())
        return path if path.is_absolute() else self.app.data_dir / path

    def _browse(self, variable: tk.StringVar) -> None:
        name = filedialog.askopenfilename(
            title="Pick a saved crawl",
            initialdir=self.app.data_dir if self.app.data_dir.exists() else Path.cwd(),
            filetypes=[("Crawl results", "*.json")],
        )
        if name:
            variable.set(name)
