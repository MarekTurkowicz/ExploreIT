from pathlib import Path

import pytest
import respx

from exploreit.experiments import (
    comparison_table,
    experiment_configs,
    experiment_name,
    load_results,
    run_experiments,
)
from exploreit.frontier import Strategy
from exploreit.parser import LinkMode
from exploreit.urls import Scope

SITE = "https://example.com/"


def test_every_combination_is_generated() -> None:
    configs = experiment_configs(SITE, max_pages=5)

    assert len(configs) == 2 * 3 * 3
    assert len({experiment_name(config) for config in configs}) == 18
    assert all(config.max_pages == 5 for config in configs)


def test_subset_of_parameters() -> None:
    configs = experiment_configs(SITE, [Strategy.DFS], [Scope.WEB], [LinkMode.ALL, LinkMode.IMAGES])

    assert [experiment_name(config) for config in configs] == ["dfs-web-all", "dfs-web-images"]


def test_run_and_compare(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    respx_mock.get(SITE).respond(html='<a href="/a">A</a> <img src="/logo.png">')
    respx_mock.get(f"{SITE}a").respond(html="<p>A</p>")
    respx_mock.get(f"{SITE}logo.png").respond(content=b"", content_type="image/png")
    configs = experiment_configs(
        SITE,
        [Strategy.DFS, Strategy.BFS],
        [Scope.SERVER],
        [LinkMode.IMAGES, LinkMode.HYPERLINKS],
        delay=0,
        respect_robots=False,
    )

    run_experiments(configs, tmp_path)
    table = comparison_table(load_results(tmp_path))

    assert len(list(tmp_path.glob("*.json"))) == 4
    assert table[["strategy", "link_mode"]].values.tolist() == [
        ["bfs", "hyperlinks"],
        ["bfs", "images"],
        ["dfs", "hyperlinks"],
        ["dfs", "images"],
    ]
    assert table["pages"].tolist() == [2, 3, 2, 3]


def test_comparison_of_nothing_is_empty() -> None:
    table = comparison_table([])

    assert table.empty
    assert "pages" in table.columns


@pytest.mark.parametrize("value", ["-1", "0"])
def test_invalid_limits_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="max_pages"):
        experiment_configs(SITE, max_pages=value)
