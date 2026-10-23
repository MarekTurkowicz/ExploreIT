from pathlib import Path

import respx
from typer.testing import CliRunner

from exploreit import __version__
from exploreit.cli import app
from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.models import CrawledPage, Edge, LinkKind

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


def test_stats_command_prints_graph_structure(tmp_path: Path) -> None:
    page = CrawledPage(
        url="https://example.com/", depth=0, status_code=200, content_type="text/html"
    )
    edge = Edge(source=page.url, target="https://example.com/about", kind=LinkKind.ANCHOR)
    crawl_file = tmp_path / "crawl.json"
    CrawlResult(config=CrawlConfig(start_url=page.url), pages=[page], edges=[edge], failed={}).save(
        crawl_file
    )

    result = runner.invoke(app, ["stats", str(crawl_file)])

    assert result.exit_code == 0, result.output
    assert "Graph depth" in result.output
    assert "Links on start page" in result.output


def test_stats_command_requires_existing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["stats", str(tmp_path / "missing.json")])

    assert result.exit_code == 2


def test_graph_command_writes_html_and_gexf(tmp_path: Path) -> None:
    page = CrawledPage(
        url="https://example.com/", depth=0, status_code=200, content_type="text/html"
    )
    crawl_file = tmp_path / "crawl.json"
    CrawlResult(config=CrawlConfig(start_url=page.url), pages=[page], edges=[], failed={}).save(
        crawl_file
    )

    result = runner.invoke(app, ["graph", str(crawl_file), "--gexf"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "crawl.html").exists()
    assert (tmp_path / "crawl.gexf").exists()


def test_plots_command_saves_charts(tmp_path: Path) -> None:
    page = CrawledPage(
        url="https://example.com/", depth=0, status_code=200, content_type="text/html"
    )
    crawl_file = tmp_path / "crawl.json"
    CrawlResult(config=CrawlConfig(start_url=page.url), pages=[page], edges=[], failed={}).save(
        crawl_file
    )

    result = runner.invoke(app, ["plots", str(crawl_file)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "crawl-levels.png").exists()
    assert (tmp_path / "crawl-out-links.png").exists()


def test_experiment_command_compares_crawls(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    respx_mock.get("https://example.com/").respond(html='<a href="/a">A</a>')
    respx_mock.get("https://example.com/a").respond(html="<p>A</p>")
    args = ["experiment", "https://example.com", "--strategy", "bfs", "--strategy", "dfs"]
    args += ["--scope", "server", "--links", "hyperlinks", "--delay", "0", "--ignore-robots"]

    result = runner.invoke(app, [*args, "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "2/2 dfs-server-hyperlinks" in result.output
    assert (tmp_path / "summary.csv").read_text().count("\n") == 3
    assert (tmp_path / "comparison.png").exists()

    rerun = runner.invoke(app, ["compare", str(tmp_path)])
    assert rerun.exit_code == 0, rerun.output


def test_experiment_command_rejects_invalid_options() -> None:
    result = runner.invoke(app, ["experiment", "not-a-url", "--scope", "server"])

    assert result.exit_code == 2
    assert "start_url" in result.output
