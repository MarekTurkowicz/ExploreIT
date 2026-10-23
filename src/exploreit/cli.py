"""Command-line interface."""

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
from exploreit.frontier import Strategy
from exploreit.models import CrawledPage
from exploreit.parser import LinkMode
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
        for problem in error.errors():
            field = ".".join(str(part) for part in problem["loc"])
            console.print(f"[red]Invalid {field}:[/] {escape(problem['msg'])}")
        raise typer.Exit(code=2) from error

    result = crawl(config, on_page=_print_page)
    result.save(output)
    console.print(_summary(result, output))


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
