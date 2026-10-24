from pathlib import Path

import pytest

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.experiments import comparison_table
from exploreit.models import CrawledPage, Edge, LinkKind
from exploreit.plots import (
    comparison_figure,
    graph_figure,
    levels_figure,
    out_links_figure,
    save_figure,
)

PNG_SIGNATURE = b"\x89PNG"
START = "https://example.com/"


def result(strategy: str = "bfs", scope: str = "server") -> CrawlResult:
    pages = [
        CrawledPage(url=START, depth=0, status_code=200, content_type="text/html"),
        CrawledPage(url=f"{START}a", depth=1, status_code=200, content_type="text/html"),
        CrawledPage(url=f"{START}gone", depth=1, status_code=404, content_type="text/html"),
    ]
    edges = [
        Edge(source=START, target=f"{START}a", kind=LinkKind.ANCHOR),
        Edge(source=START, target=f"{START}gone", kind=LinkKind.ANCHOR),
        Edge(source=f"{START}a", target="https://other.org/", kind=LinkKind.ANCHOR),
    ]
    config = CrawlConfig.model_validate({"start_url": START, "strategy": strategy, "scope": scope})
    return CrawlResult(config=config, pages=pages, edges=edges, failed={})


def test_single_crawl_charts(tmp_path: Path) -> None:
    save_figure(levels_figure(result()), tmp_path / "levels.png")
    save_figure(out_links_figure(result()), tmp_path / "charts" / "out.png")

    assert (tmp_path / "levels.png").read_bytes().startswith(PNG_SIGNATURE)
    assert (tmp_path / "charts" / "out.png").read_bytes().startswith(PNG_SIGNATURE)


def test_comparison_chart(tmp_path: Path) -> None:
    results = [
        result(strategy, scope) for strategy in ("bfs", "dfs") for scope in ("server", "web")
    ]

    save_figure(comparison_figure(comparison_table(results)), tmp_path / "comparison.png")

    assert (tmp_path / "comparison.png").read_bytes().startswith(PNG_SIGNATURE)


@pytest.mark.parametrize("layout", ["levels", "spring"])
def test_graph_drawing_places_every_page(layout: str) -> None:
    drawing = graph_figure(result(), layout)  # type: ignore[arg-type]

    assert drawing.urls == [START, f"{START}a", f"{START}gone"]
    assert drawing.positions.shape == (3, 2)


def test_levels_layout_puts_each_level_in_its_own_column() -> None:
    drawing = graph_figure(result(), "levels")
    x = dict(zip(drawing.urls, drawing.positions[:, 0], strict=True))

    assert x[START] < x[f"{START}a"] == x[f"{START}gone"]


def test_graph_drawing_can_include_unvisited_pages() -> None:
    drawing = graph_figure(result(), "levels", visited_only=False)

    assert "https://other.org/" in drawing.urls


def test_graph_drawing_of_an_empty_crawl() -> None:
    empty = CrawlResult(config=CrawlConfig(start_url=START), pages=[], edges=[], failed={})

    assert graph_figure(empty).urls == []
