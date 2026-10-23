from pathlib import Path

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.experiments import comparison_table
from exploreit.models import CrawledPage, Edge, LinkKind
from exploreit.plots import plot_comparison, plot_levels, plot_out_links

PNG_SIGNATURE = b"\x89PNG"


def result(strategy: str, scope: str) -> CrawlResult:
    start = "https://example.com/"
    pages = [
        CrawledPage(url=start, depth=0, status_code=200, content_type="text/html"),
        CrawledPage(url=f"{start}a", depth=1, status_code=200, content_type="text/html"),
    ]
    edges = [Edge(source=start, target=f"{start}a", kind=LinkKind.ANCHOR)]
    config = CrawlConfig.model_validate({"start_url": start, "strategy": strategy, "scope": scope})
    return CrawlResult(config=config, pages=pages, edges=edges, failed={})


def test_single_crawl_charts(tmp_path: Path) -> None:
    plot_levels(result("bfs", "server"), tmp_path / "levels.png")
    plot_out_links(result("bfs", "server"), tmp_path / "out.png")

    assert (tmp_path / "levels.png").read_bytes().startswith(PNG_SIGNATURE)
    assert (tmp_path / "out.png").read_bytes().startswith(PNG_SIGNATURE)


def test_comparison_chart(tmp_path: Path) -> None:
    results = [
        result(strategy, scope) for strategy in ("bfs", "dfs") for scope in ("server", "web")
    ]

    plot_comparison(comparison_table(results), tmp_path / "charts" / "comparison.png")

    assert (tmp_path / "charts" / "comparison.png").read_bytes().startswith(PNG_SIGNATURE)
