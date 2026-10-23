"""Command-line interface."""

import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from exploreit import __version__
from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult, crawl
from exploreit.experiments import (
    PARAMETERS,
    comparison_table,
    experiment_configs,
    experiment_name,
    load_results,
    run_experiments,
)
from exploreit.export import write_gexf, write_html
from exploreit.frontier import Strategy
from exploreit.graph import GraphStats, compute_stats
from exploreit.models import CrawledPage
from exploreit.parser import LinkMode
from exploreit.plots import plot_comparison, plot_levels, plot_out_links
from exploreit.tui import ExploreApp
from exploreit.urls import Scope

app = typer.Typer(help="ExploreIT: web structure exploration toolkit.", no_args_is_help=True)
console = Console()


@app.callback()
def main() -> None:
    """Crawl websites, analyse their link graph and store page content."""


@app.command()
def version() -> None:
    """Show the application version."""
    typer.echo(f"exploreit {__version__}")


@app.command()
def ui() -> None:
    """Open the interactive terminal interface."""
    ExploreApp().run()


@app.command("crawl")
def crawl_command(
    start_url: Annotated[str, typer.Argument(help="URL to start crawling from.")],
    strategy: Annotated[Strategy, typer.Option(help="Order of visiting pages.")] = Strategy.BFS,
    scope: Annotated[Scope, typer.Option(help="How far from the start URL to go.")] = Scope.SERVER,
    links: Annotated[LinkMode, typer.Option(help="Which links to follow.")] = LinkMode.HYPERLINKS,
    max_depth: Annotated[int, typer.Option(help="Deepest level to visit.")] = 3,
    max_pages: Annotated[int, typer.Option(help="Stop after this many pages.")] = 100,
    delay: Annotated[float, typer.Option(help="Seconds between requests to a host.")] = 1.0,
    ignore_robots: Annotated[
        bool, typer.Option("--ignore-robots", help="Do not check robots.txt.")
    ] = False,
    output: Annotated[
        Path, typer.Option("--output", "-o", help="Where to save the result.")
    ] = Path("data/crawl.json"),
) -> None:
    """Crawl a website and save its link graph as JSON."""
    try:
        config = CrawlConfig(
            start_url=start_url,
            strategy=strategy,
            scope=scope,
            link_mode=links,
            max_depth=max_depth,
            max_pages=max_pages,
            delay=delay,
            respect_robots=not ignore_robots,
        )
    except ValidationError as error:
        _print_errors(error)
        raise typer.Exit(code=2) from error

    result = crawl(config, on_page=_print_page)
    result.save(output)
    console.print(_summary(result, output))


@app.command()
def stats(
    crawl_file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="Result of the crawl command.")
    ] = Path("data/crawl.json"),
) -> None:
    """Show the structure of a crawled link graph."""
    result = CrawlResult.load(crawl_file)
    console.print(_stats_table(compute_stats(result), result.config))


@app.command()
def graph(
    crawl_file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="Result of the crawl command.")
    ] = Path("data/crawl.json"),
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
def plots(
    crawl_file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="Result of the crawl command.")
    ] = Path("data/crawl.json"),
) -> None:
    """Save PNG charts of a crawl next to the crawl file."""
    result = CrawlResult.load(crawl_file)
    for suffix, plot in (("levels", plot_levels), ("out-links", plot_out_links)):
        path = crawl_file.with_name(f"{crawl_file.stem}-{suffix}.png")
        plot(result, path)
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
    max_depth: Annotated[int, typer.Option(help="Deepest level to visit.")] = 3,
    max_pages: Annotated[int, typer.Option(help="Stop each crawl after this many pages.")] = 100,
    delay: Annotated[float, typer.Option(help="Seconds between requests to a host.")] = 1.0,
    ignore_robots: Annotated[
        bool, typer.Option("--ignore-robots", help="Do not check robots.txt.")
    ] = False,
    output: Annotated[Path, typer.Option("--output", "-o", help="Directory for results.")] = Path(
        "data/experiments"
    ),
) -> None:
    """Crawl a site with every parameter combination and compare the link graphs.

    Each option can be repeated to pick a subset, e.g. --scope server --scope web.
    """
    try:
        configs = experiment_configs(
            start_url,
            strategies,
            scopes,
            link_modes,
            max_depth=max_depth,
            max_pages=max_pages,
            delay=delay,
            respect_robots=not ignore_robots,
        )
    except ValidationError as error:
        _print_errors(error)
        raise typer.Exit(code=2) from error

    total = len(configs)
    done = 0

    def report(config: CrawlConfig, result: CrawlResult) -> None:
        nonlocal done
        done += 1
        console.print(
            f"[dim]{done}/{total}[/] {experiment_name(config)}: "
            f"{len(result.pages)} pages, {len(result.edges)} links"
        )

    run_experiments(configs, output, on_crawl=report)
    _print_comparison(output)


@app.command()
def compare(
    directory: Annotated[
        Path, typer.Argument(exists=True, file_okay=False, help="Directory of crawl results.")
    ] = Path("data/experiments"),
) -> None:
    """Compare saved crawl results and draw a comparison chart."""
    _print_comparison(directory)


def _print_comparison(directory: Path) -> None:
    table = comparison_table(load_results(directory))
    table.to_csv(directory / "summary.csv", index=False)
    plot_comparison(table, directory / "comparison.png")

    view = Table(title="Crawl parameters compared")
    columns = ["strategy", "scope", "link_mode", "pages", "links", "external_links", "depth"]
    columns += ["start_page_links", "subpage_links_mean", "dead_ends"]
    for column in columns:
        view.add_column(
            column.replace("_", " "), justify="left" if column in PARAMETERS else "right"
        )
    for row in table[columns].itertuples(index=False):
        view.add_row(*(f"{value:.1f}" if isinstance(value, float) else str(value) for value in row))
    console.print(view)
    console.print(f"Saved {directory / 'summary.csv'} and {directory / 'comparison.png'}")


def _print_errors(error: ValidationError) -> None:
    for problem in error.errors():
        field = ".".join(str(part) for part in problem["loc"])
        console.print(f"[red]Invalid {field}:[/] {escape(problem['msg'])}")


def _print_page(page: CrawledPage) -> None:
    colour = "green" if page.status_code < 400 else "red"
    console.print(
        f"[dim]{page.depth}[/] [{colour}]{page.status_code}[/] {escape(page.url)}", soft_wrap=True
    )


def _summary(result: CrawlResult, output: Path) -> Table:
    table = Table(title="Crawl summary", show_header=False)
    table.add_row("Pages visited", str(len(result.pages)))
    table.add_row("Links found", str(len(result.edges)))
    table.add_row("Failed", str(len(result.failed)))
    table.add_row("Deepest level", str(max((page.depth for page in result.pages), default=0)))
    table.add_row("Saved to", str(output))
    return table


def _stats_table(stats: GraphStats, config: CrawlConfig) -> Table:
    table = Table(title=f"Link graph of {escape(config.start_url)}", show_header=False)
    table.add_row(
        "Crawl",
        f"{config.strategy} · {config.scope} · {config.link_mode} · depth {config.max_depth}",
    )
    table.add_section()
    for label, value in stats.summary():
        table.add_row(label, escape(value))
    return table
