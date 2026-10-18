"""Command-line interface."""

import typer

from exploreit import __version__

app = typer.Typer(help="ExploreIT: web structure exploration toolkit.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Show the application version."""
    typer.echo(f"exploreit {__version__}")


@app.callback()
def main() -> None:
    """Crawl websites, analyse their link graph and store page content."""
