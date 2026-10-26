"""Command-line interface."""

import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from exploreit import __version__
from exploreit.compare import comparison_rows
from exploreit.config import CrawlConfig, parse_headers
from exploreit.crawler import CrawlResult, crawl
from exploreit.experiments import (
    CHART_FILE,
    PARAMETERS,
    SUMMARY_COLUMNS,
    SUMMARY_FILE,
    experiment_configs,
    experiment_name,
    load_results,
    run_experiments,
    save_comparison,
)
from exploreit.export import write_gexf, write_html
from exploreit.fetcher import USER_AGENT
from exploreit.frontier import Strategy
from exploreit.graph import compute_stats
from exploreit.models import CrawledPage
from exploreit.parser import LinkMode
from exploreit.ranking.prestige import Dangling, Normalization
from exploreit.storage import ContentField, write_csv, write_sqlite
from exploreit.urls import Scope

app = typer.Typer(help="ExploreIT: web structure exploration toolkit.", no_args_is_help=True)
console = Console()

# Options shared by `crawl` and `experiment`.
MaxDepth = Annotated[int, typer.Option(help="Deepest level to visit (0 = start page only).")]
MaxPages = Annotated[int, typer.Option(help="Stop a crawl after this many pages.")]
Delay = Annotated[float, typer.Option(help="Seconds between requests to the same host.")]
IgnoreRobots = Annotated[bool, typer.Option("--ignore-robots", help="Do not check robots.txt.")]
UserAgent = Annotated[str, typer.Option(help="User-Agent sent with every request.")]
Headers = Annotated[
    list[str],
    typer.Option(
        "--header",
        default_factory=list,
        help="Extra request header 'Name: value'. Repeat for more. "
        "This does not get past anti-bot services such as DataDome or Cloudflare.",
    ),
]
CrawlFile = Annotated[
    Path, typer.Argument(exists=True, dir_okay=False, help="A crawl result (JSON).")
]


@app.callback()
def main() -> None:
    """Crawl websites, analyse their link graph and store page content."""


@app.command()
def version() -> None:
    """Show the application version."""
    typer.echo(f"exploreit {__version__}")


@app.command()
def ui(
    data_dir: Annotated[Path, typer.Option("--data", help="Where crawl results are saved.")] = Path(
        "data"
    ),
) -> None:
    """Open the desktop application."""
    from exploreit.gui.app import run_app  # Tk and the charts load only for this command

    run_app(data_dir)


@app.command("crawl")
def crawl_command(
    start_url: Annotated[str, typer.Argument(help="URL to start crawling from.")],
    header: Headers,
    strategy: Annotated[Strategy, typer.Option(help="Order of visiting pages.")] = Strategy.BFS,
    scope: Annotated[Scope, typer.Option(help="How far from the start URL to go.")] = Scope.SERVER,
    links: Annotated[LinkMode, typer.Option(help="Which links to follow.")] = LinkMode.HYPERLINKS,
    max_depth: MaxDepth = 3,
    max_pages: MaxPages = 100,
    delay: Delay = 1.0,
    ignore_robots: IgnoreRobots = False,
    user_agent: UserAgent = USER_AGENT,
    content: Annotated[
        bool, typer.Option("--content", help="Also keep title, meta tags and body text.")
    ] = False,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Where to save the result.")
    ] = Path("data/crawl.json"),
) -> None:
    """Crawl a website and save its link graph (and optionally page content) as JSON."""
    config = _validated(
        lambda: CrawlConfig(
            start_url=start_url,
            strategy=strategy,
            scope=scope,
            link_mode=links,
            max_depth=max_depth,
            max_pages=max_pages,
            delay=delay,
            respect_robots=not ignore_robots,
            store_content=content,
            user_agent=user_agent,
            headers=_headers(header),
        )
    )
    result = crawl(config, on_page=_print_page)
    for url, reason in result.failed.items():
        console.print(f"[red]failed[/] {escape(url)}: {escape(reason)}", soft_wrap=True)
    result.save(output)
    console.print(_stats_table(result))
    console.print(f"Saved to {output}")


@app.command()
def stats(crawl_file: CrawlFile = Path("data/crawl.json")) -> None:
    """Show the structure of a crawled link graph."""
    console.print(_stats_table(CrawlResult.load(crawl_file)))


@app.command()
def graph(
    crawl_file: CrawlFile = Path("data/crawl.json"),
    all_links: Annotated[
        bool, typer.Option("--all-links", help="Also show linked pages that were not visited.")
    ] = False,
    gexf: Annotated[bool, typer.Option("--gexf", help="Also save a GEXF file for Gephi.")] = False,
    open_browser: Annotated[
        bool, typer.Option("--open", help="Open the graph in the web browser.")
    ] = False,
) -> None:
    """Draw the link graph as an interactive HTML page next to the crawl file."""
    result = CrawlResult.load(crawl_file)
    html_file = crawl_file.with_suffix(".html")
    write_html(result, html_file, visited_only=not all_links)
    console.print(f"Graph saved to {html_file}")
    if gexf:
        gexf_file = crawl_file.with_suffix(".gexf")
        write_gexf(result, gexf_file)
        console.print(f"GEXF saved to {gexf_file}")
    if open_browser:
        webbrowser.open(html_file.resolve().as_uri())


@app.command()
def plots(crawl_file: CrawlFile = Path("data/crawl.json")) -> None:
    """Save PNG charts of a crawl next to the crawl file."""
    from exploreit.plots import levels_figure, out_links_figure, save_figure

    result = CrawlResult.load(crawl_file)
    for suffix, figure in (("levels", levels_figure), ("out-links", out_links_figure)):
        path = crawl_file.with_name(f"{crawl_file.stem}-{suffix}.png")
        save_figure(figure(result), path)
        console.print(f"Chart saved to {path}")


@app.command()
def experiment(
    start_url: Annotated[str, typer.Argument(help="URL to start every crawl from.")],
    strategies: Annotated[
        list[Strategy],
        typer.Option(
            "--strategy",
            default_factory=lambda: list(Strategy),
            show_default="all",
            help="Strategies to try.",
        ),
    ],
    scopes: Annotated[
        list[Scope],
        typer.Option(
            "--scope",
            default_factory=lambda: list(Scope),
            show_default="all",
            help="Scopes to try.",
        ),
    ],
    link_modes: Annotated[
        list[LinkMode],
        typer.Option(
            "--links",
            default_factory=lambda: list(LinkMode),
            show_default="all",
            help="Link modes to try.",
        ),
    ],
    max_depth: MaxDepth = 3,
    max_pages: MaxPages = 100,
    delay: Delay = 1.0,
    ignore_robots: IgnoreRobots = False,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Directory for the results.")
    ] = Path("data/experiments"),
) -> None:
    """Crawl a site with every parameter combination and compare the link graphs.

    Each option can be repeated to pick a subset, e.g. --scope server --scope web.
    """
    configs = _validated(
        lambda: experiment_configs(
            start_url,
            strategies,
            scopes,
            link_modes,
            max_depth=max_depth,
            max_pages=max_pages,
            delay=delay,
            respect_robots=not ignore_robots,
        )
    )

    def report(config: CrawlConfig, result: CrawlResult) -> None:
        console.print(
            f"{experiment_name(config)}: {len(result.pages)} pages, {len(result.edges)} links"
        )

    run_experiments(configs, output, on_crawl=report)
    _print_comparison(output)


@app.command()
def rank(
    crawl_file: CrawlFile = Path("data/crawl.json"),
    normalization: Annotated[
        Normalization, typer.Option(help="How prestige is rescaled after every step.")
    ] = Normalization.SUM,
    dangling: Annotated[
        Dangling, typer.Option(help="What happens to the vote of pages without links out.")
    ] = Dangling.LOST,
    smoothing: Annotated[
        float, typer.Option(min=0, max=0.99, help="Part of the old value kept each step.")
    ] = 0.0,
    max_iterations: Annotated[int, typer.Option(min=1, help="Stop after this many steps.")] = 200,
    top: Annotated[int, typer.Option(min=1, help="How many pages to list.")] = 20,
    words: Annotated[
        int, typer.Option(min=1, help="Words in the first round of the word cascade.")
    ] = 10,
    weight_links: Annotated[float, typer.Option(min=0, help="ExploreIT rank: links.")] = 0.5,
    weight_text: Annotated[float, typer.Option(min=0, help="ExploreIT rank: text.")] = 0.3,
    weight_bridges: Annotated[float, typer.Option(min=0, help="ExploreIT rank: bridges.")] = 0.2,
) -> None:
    """Rank the pages of a crawl by their links with every method and compare them.

    Saves the ranking, both adjacency matrices and a page legend as CSV next to the
    crawl file.
    """
    from exploreit.ranking.graph import check_requirements, link_graph, shortest_cycle
    from exploreit.ranking.matrix import (
        adjacency_matrix,
        short_labels,
        write_legend_csv,
        write_matrix_csv,
    )
    from exploreit.ranking.methods import Settings, compare, format_tau, write_ranking_csv

    graph = link_graph(CrawlResult.load(crawl_file))
    labels = dict(zip(graph.pages, short_labels(graph), strict=True))
    checks = Table(title="Graph requirements", show_header=False)
    for check in check_requirements(graph):
        checks.add_row(
            "[green]✔[/]" if check.met else "[red]✘[/]", check.description, str(check.actual)
        )
    if cycle := shortest_cycle(graph):
        checks.add_row("", "cycle", " → ".join(labels[page] for page in [*cycle, cycle[0]]))
    console.print(checks)
    if not graph.pages:
        raise typer.Exit(code=1)

    settings = Settings(
        normalization=normalization,
        dangling=dangling,
        smoothing=smoothing,
        max_iterations=max_iterations,
        cascade_words=words,
        weight_links=weight_links,
        weight_text=weight_text,
        weight_bridges=weight_bridges,
    )
    if not graph.texts:
        console.print("[yellow]No page content in this crawl:[/] the word cascade is empty.")
    comparison = compare(graph, settings)
    methods = Table(title="Methods")
    for column in ("method", "iterations", "settled", "ms"):
        methods.add_column(column, justify="left" if column == "method" else "right")
    for result in comparison.results:
        methods.add_row(
            result.method.name,
            str(result.scores.iterations),
            "yes" if result.scores.converged else "[red]no[/]",
            f"{result.seconds * 1000:.1f}",
        )
    console.print(methods)

    ranking = Table(title=f"Top {top} pages (place and score per method)")
    ranking.add_column("page")
    ranking.add_column("url", overflow="fold")
    for result in comparison.results:
        ranking.add_column(result.method.name, justify="right")
    for page, page_places, scores in comparison.table()[:top]:
        cells = (f"{p}. {s:.4g}" for p, s in zip(page_places, scores, strict=True))
        ranking.add_row(labels[page], escape(page), *cells)
    console.print(ranking)

    agreement = Table(title="Agreement (Kendall tau: 1 same order, -1 reversed)")
    agreement.add_column("methods")
    agreement.add_column("tau", justify="right")
    for first, second, tau in comparison.agreement():
        agreement.add_row(f"{first} vs {second}", format_tau(tau))
    console.print(agreement)

    stem = crawl_file.with_name(crawl_file.stem)
    write_ranking_csv(comparison, Path(f"{stem}-ranking.csv"))
    write_matrix_csv(adjacency_matrix(graph), list(labels.values()), Path(f"{stem}-A.csv"))
    write_matrix_csv(
        adjacency_matrix(graph, weighted=True),
        list(labels.values()),
        Path(f"{stem}-A-weighted.csv"),
    )
    write_legend_csv(graph, Path(f"{stem}-pages.csv"))
    console.print(f"Saved {stem.name}-ranking.csv, -A.csv, -A-weighted.csv and -pages.csv")


@app.command()
def summarize(
    directory: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="Directory of crawl results.")
    ] = Path("data/experiments"),
) -> None:
    """Compare the link graphs of saved crawls, e.g. the results of `experiment`."""
    _print_comparison(directory)


@app.command()
def store(
    crawl_file: CrawlFile,
    fields: Annotated[
        list[ContentField],
        typer.Option(
            "--field",
            default_factory=lambda: list(ContentField),
            show_default="all",
            help="Columns to save, in order. Repeat to pick several.",
        ),
    ],
    separator: Annotated[
        str, typer.Option(help="One-character CSV separator, e.g. ';'. Use '\\t' for tab.")
    ] = ",",
    sqlite: Annotated[bool, typer.Option("--sqlite", help="Also save a SQLite database.")] = False,
) -> None:
    """Save page content of a crawl as CSV (and SQLite) next to the crawl file."""
    separator = separator.replace("\\t", "\t")
    if len(separator) != 1:
        raise typer.BadParameter("must be a single character", param_hint="--separator")
    result = CrawlResult.load(crawl_file)
    if not result.contents:
        console.print("[red]No page content in this crawl.[/] Run crawl with --content first.")
        raise typer.Exit(code=1)

    csv_file = crawl_file.with_suffix(".csv")
    write_csv(result.contents, csv_file, fields, separator)
    console.print(f"{len(result.contents)} pages saved to {csv_file}")
    if sqlite:
        sqlite_file = crawl_file.with_suffix(".sqlite")
        write_sqlite(result, sqlite_file)
        console.print(f"Database saved to {sqlite_file}")


@app.command()
def diff(first: CrawlFile, second: CrawlFile) -> None:
    """Compare the page content stored by two crawls."""
    table = Table(title="Content databases compared")
    table.add_column("")
    table.add_column(first.stem, overflow="fold")
    table.add_column(second.stem, overflow="fold")
    for row in comparison_rows(CrawlResult.load(first), CrawlResult.load(second)):
        table.add_row(*map(escape, row))
    console.print(table)


def _headers(lines: list[str]) -> dict[str, str]:
    try:
        return parse_headers(lines)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint="--header") from error


def _validated[T](build: Callable[[], T]) -> T:
    """Build a config, turning validation errors into readable messages and exit code 2."""
    try:
        return build()
    except ValidationError as error:
        for problem in error.errors():
            field = ".".join(str(part) for part in problem["loc"])
            console.print(f"[red]Invalid {field}:[/] {escape(problem['msg'])}")
        raise typer.Exit(code=2) from error


def _print_page(page: CrawledPage) -> None:
    colour = "green" if page.status_code < 400 else "red"
    blocked = f" [red]blocked by {page.blocked_by}[/]" if page.blocked_by else ""
    console.print(
        f"[dim]{page.depth}[/] [{colour}]{page.status_code}[/] {escape(page.url)}{blocked}",
        soft_wrap=True,
    )


def _print_comparison(directory: Path) -> None:
    try:
        table = save_comparison(load_results(directory), directory)
    except ValueError as error:
        console.print(f"[red]{error}[/]")
        raise typer.Exit(code=1) from error

    view = Table(title="Crawl parameters compared")
    for column in SUMMARY_COLUMNS:
        view.add_column(
            column.replace("_", " "), justify="left" if column in PARAMETERS else "right"
        )
    for row in table[SUMMARY_COLUMNS].itertuples(index=False):
        view.add_row(*(f"{value:.1f}" if isinstance(value, float) else str(value) for value in row))
    console.print(view)
    console.print(f"Saved {directory / SUMMARY_FILE} and {directory / CHART_FILE}")


def _stats_table(result: CrawlResult) -> Table:
    table = Table(title=f"Link graph of {escape(result.config.start_url)}", show_header=False)
    table.add_row("Crawl", result.config.describe())
    table.add_section()
    for label, value in compute_stats(result).summary():
        table.add_row(label, escape(value))
    return table
