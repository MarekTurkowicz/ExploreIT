from pathlib import Path

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.experiments import comparison_table
from exploreit.models import CrawledPage, Edge, LinkKind
from exploreit.plots import (
    comparison_figure,
    levels_figure,
    network_figure,
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


def test_network_figure_draws_saved_positions(tmp_path: Path) -> None:
    positions = {"a": (0.0, 0.0), "b": (1.0, 1.0)}

    figure = network_figure(
        [("a", "b")], positions, {"a": "#000000", "b": "#ffffff"}, {"a": 5, "b": 8}, {"a": "A"}, "t"
    )
    save_figure(figure, tmp_path / "graph.png")

    assert (tmp_path / "graph.png").read_bytes().startswith(PNG_SIGNATURE)
    assert figure.axes[0].yaxis_inverted()


def test_network_figure_of_nothing() -> None:
    assert len(network_figure([], {}, {}, {}, {}, "empty").axes[0].collections) == 0
