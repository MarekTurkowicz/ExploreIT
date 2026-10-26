"""Ranking tab: check the graph, rank its pages with every method and compare them."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from exploreit.crawler import CrawlResult
from exploreit.gui.widgets import ChartPanel, Table
from exploreit.ranking.graph import LinkGraph, check_requirements, link_graph, shortest_cycle
from exploreit.ranking.matrix import (
    adjacency_matrix,
    short_labels,
    write_legend_csv,
    write_matrix_csv,
)
from exploreit.ranking.methods import (
    METHODS,
    Comparison,
    Settings,
    compare,
    format_tau,
    write_ranking_csv,
)
from exploreit.ranking.prestige import Dangling, Normalization

if TYPE_CHECKING:
    from exploreit.gui.app import ExploreApp

WEIGHTS = {"links": "0.5", "text": "0.3", "bridges": "0.2"}


class RankingTab(ttk.Frame):
    """Settings and results of ranking the pages of the current crawl."""

    # Set by show() and compute(); the buttons that need them stay disabled until then.
    result: CrawlResult
    crawl_file: Path
    graph: LinkGraph
    comparison: Comparison

    def __init__(self, master: tk.Misc, app: ExploreApp) -> None:
        super().__init__(master, padding=12)
        self.app = app
        self.normalization = tk.StringVar(value=Normalization.SUM)
        self.dangling = tk.StringVar(value=Dangling.LOST)
        self.smoothing = tk.StringVar(value="0.0")
        self.max_iterations = tk.StringVar(value="200")
        self.on_graph = tk.StringVar(value=METHODS[-1].name)
        self.cascade_words = tk.StringVar(value="10")
        self.weights = {part: tk.StringVar(value=value) for part, value in WEIGHTS.items()}
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x")
        checks = ttk.LabelFrame(top, text="Graph requirements (task point 1)", padding=10)
        checks.pack(side="left", fill="y")
        self.checks = ttk.Label(checks, text="Load a crawl first.", justify="left")
        self.checks.pack(anchor="w")

        settings = ttk.LabelFrame(top, text="Iteration (points 3 and 5)", padding=10)
        settings.pack(side="left", fill="both", expand=True, padx=(12, 0))
        rows = [
            ("Normalise after each step", self.normalization, [n.value for n in Normalization]),
            ("Pages without links out", self.dangling, [d.value for d in Dangling]),
        ]
        for row, (label, variable, values) in enumerate(rows):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Combobox(
                settings, textvariable=variable, values=values, state="readonly", width=12
            ).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(settings, text="Smoothing (0 - 0.9)").grid(row=0, column=2, sticky="w", padx=8)
        ttk.Spinbox(
            settings, textvariable=self.smoothing, from_=0, to=0.9, increment=0.1, width=6
        ).grid(row=0, column=3, sticky="w")
        ttk.Label(settings, text="Max iterations").grid(row=1, column=2, sticky="w", padx=8)
        ttk.Spinbox(
            settings, textvariable=self.max_iterations, from_=1, to=100_000, increment=50, width=8
        ).grid(row=1, column=3, sticky="w")
        ttk.Label(
            settings,
            text="Smoothing keeps part of the old value each step, which stops prestige "
            "from swapping back and forth in cycles.",
            wraplength=420,
            foreground="#898781",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        own = ttk.LabelFrame(top, text="ExploreIT rank (own method)", padding=10)
        own.pack(side="left", fill="both", padx=(12, 0))
        ttk.Label(own, text="Words in round 1").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Spinbox(own, textvariable=self.cascade_words, from_=1, to=50, width=5).grid(
            row=0, column=1, sticky="w", padx=8
        )
        for row, (part, variable) in enumerate(self.weights.items(), start=1):
            ttk.Label(own, text=f"Weight of {part}").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Spinbox(own, textvariable=variable, from_=0, to=1, increment=0.1, width=5).grid(
                row=row, column=1, sticky="w", padx=8
            )

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=10)
        self.compute_button = tb.Button(
            actions, text="Rank pages", command=self.compute, bootstyle="primary"
        )
        self.compute_button.pack(side="left")
        self.compute_button.state(["disabled"])
        ttk.Label(actions, text="Show on graph").pack(side="left", padx=(18, 6))
        ttk.Combobox(
            actions,
            textvariable=self.on_graph,
            values=[method.name for method in METHODS],
            state="readonly",
            width=18,
        ).pack(side="left")
        self.result_buttons = [
            ttk.Button(actions, text="Show", command=self.show_on_graph),
            ttk.Button(actions, text="Save rankings (CSV)", command=self.save_rankings),
            ttk.Button(actions, text="Save matrices (CSV)", command=self.save_matrices),
        ]
        for button in self.result_buttons:
            button.pack(side="left", padx=(8, 0))
            button.state(["disabled"])

        panes = ttk.PanedWindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        self.table = Table(panes, height=8)
        panes.add(self.table, weight=3)
        below = ttk.Frame(panes)
        self.methods_table = Table(below, height=8)
        self.methods_table.pack(side="left", fill="y")
        self.agreement = Table(below, height=8)
        self.agreement.pack(side="left", fill="y", padx=10)
        self.chart = ChartPanel(below)
        self.chart.pack(side="left", fill="both", expand=True)
        panes.add(below, weight=2)

    def show(self, result: CrawlResult, path: Path) -> None:
        self.result, self.crawl_file = result, path
        self.graph = link_graph(result)
        lines = [
            f"{'✔' if check.met else '✘'}  {check.description}: {check.actual}"
            for check in check_requirements(self.graph)
        ]
        cycle = shortest_cycle(self.graph)
        labels = dict(zip(self.graph.pages, short_labels(self.graph), strict=True))
        if cycle:
            lines.append("    cycle: " + " → ".join(labels[page] for page in [*cycle, cycle[0]]))
        lines.append(f"{len(self.graph.pages)} pages, {len(self.graph.links)} links between them")
        self.checks.configure(text="\n".join(lines))
        self.compute_button.state(["!disabled"] if self.graph.pages else ["disabled"])

    def settings(self) -> Settings:
        """Raises ValueError for numbers that cannot be read or are out of range."""
        smoothing = float(self.smoothing.get())
        if not 0 <= smoothing < 1:
            raise ValueError("Smoothing must be at least 0 and less than 1.")
        weights = {part: float(variable.get()) for part, variable in self.weights.items()}
        if any(weight < 0 for weight in weights.values()):
            raise ValueError("Weights cannot be negative.")
        return Settings(
            normalization=Normalization(self.normalization.get()),
            dangling=Dangling(self.dangling.get()),
            smoothing=smoothing,
            max_iterations=max(1, int(self.max_iterations.get())),
            cascade_words=max(1, int(self.cascade_words.get())),
            weight_links=weights["links"],
            weight_text=weights["text"],
            weight_bridges=weights["bridges"],
        )

    def compute(self) -> None:
        try:
            settings = self.settings()
        except ValueError as error:
            messagebox.showerror("Ranking", str(error))
            return
        graph = self.graph
        self.compute_button.state(["disabled"])
        self.app.tasks.run(lambda: compare(graph, settings), self._display)

    def _display(self, comparison: Comparison) -> None:
        from exploreit.plots import convergence_figure

        self.comparison = comparison
        self.compute_button.state(["!disabled"])
        for button in self.result_buttons:
            button.state(["!disabled"])
        names = [result.method.name for result in comparison.results]
        labels = dict(zip(self.graph.pages, short_labels(self.graph), strict=True))
        self.table.set_rows(
            ["Page", "URL", *(f"{name}" for name in names)],
            (
                [
                    labels[page],
                    page,
                    *(f"{place}.  {score:.4g}" for place, score in zip(pl, sc, strict=True)),
                ]
                for page, pl, sc in comparison.table()
            ),
            widths=[50, 200, *([95] * len(names))],
        )
        self.methods_table.set_rows(
            ["Method", "Iterations", "Settled", "Time (ms)"],
            (
                [
                    result.method.name,
                    result.scores.iterations,
                    "yes" if result.scores.converged else "NO",
                    f"{result.seconds * 1000:.1f}",
                ]
                for result in comparison.results
            ),
            widths=[150, 80, 70],
        )
        self.agreement.set_rows(
            ["Methods compared", "Kendall tau"],
            ([f"{a} vs {b}", format_tau(tau)] for a, b, tau in comparison.agreement()),
            widths=[260],
        )
        self.chart.show(
            convergence_figure(
                {result.method.name: result.scores.history for result in comparison.results}
            )
        )
        note = (
            "" if self.graph.texts else " This crawl has no saved content: word cascade is empty."
        )
        self.app.set_status(
            "Ranked with every method. 'Show' sizes the pages on the Graph tab by score." + note
        )

    def show_on_graph(self) -> None:
        result = next(r for r in self.comparison.results if r.method.name == self.on_graph.get())
        scores = dict(zip(self.graph.pages, result.scores.values.tolist(), strict=True))
        self.app.graph_tab.show_prestige(scores)
        self.app.notebook.select(self.app.graph_tab)

    def save_rankings(self) -> None:
        path = self.crawl_file.with_name(f"{self.crawl_file.stem}-ranking.csv")
        write_ranking_csv(self.comparison, path)
        self.app.set_status(f"Saved {path}")

    def save_matrices(self) -> None:
        labels = short_labels(self.graph)
        stem = self.crawl_file.with_name(self.crawl_file.stem)
        write_matrix_csv(adjacency_matrix(self.graph), labels, Path(f"{stem}-A.csv"))
        write_matrix_csv(
            adjacency_matrix(self.graph, weighted=True), labels, Path(f"{stem}-A-weighted.csv")
        )
        write_legend_csv(self.graph, Path(f"{stem}-pages.csv"))
        self.app.set_status(f"Saved {stem.name}-A.csv, -A-weighted.csv and -pages.csv")
