from pathlib import Path

import respx
from typer.testing import CliRunner

from exploreit import __version__
from exploreit.cli import app
from exploreit.crawler import CrawlResult

runner = CliRunner()


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_crawl_command_saves_result(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    respx_mock.get("https://example.com/").respond(html='<a href="/about">About</a>')
    respx_mock.get("https://example.com/about").respond(html="<p>About</p>")
    output = tmp_path / "crawl.json"

    args = ["crawl", "https://example.com", "--strategy", "dfs", "--delay", "0"]
    result = runner.invoke(app, [*args, "--ignore-robots", "-o", str(output)])

    assert result.exit_code == 0, result.output
    assert "Crawl summary" in result.output
    saved = CrawlResult.load(output)
    assert [page.url for page in saved.pages] == [
        "https://example.com/",
        "https://example.com/about",
    ]
    assert saved.config.strategy == "dfs"


def test_crawl_command_rejects_invalid_options() -> None:
    result = runner.invoke(app, ["crawl", "not-a-url", "--max-pages", "0"])

    assert result.exit_code == 2
    assert "start_url" in result.output
    assert "max_pages" in result.output
