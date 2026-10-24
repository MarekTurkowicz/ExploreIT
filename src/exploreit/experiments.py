"""Crawl one site with every combination of parameters and compare the results."""

from collections.abc import Callable, Iterable
from itertools import product
from pathlib import Path

import pandas as pd

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult, crawl
from exploreit.frontier import Strategy
from exploreit.graph import GraphStats, compute_stats
from exploreit.parser import LinkMode
from exploreit.plots import comparison_figure, save_figure
from exploreit.urls import Scope

PARAMETERS = ["strategy", "scope", "link_mode"]
SUMMARY_COLUMNS = [
    *PARAMETERS,
    "pages",
    "links",
    "external_links",
    "depth",
    "start_page_links",
    "subpage_links_mean",
    "dead_ends",
]
SUMMARY_FILE = "summary.csv"
CHART_FILE = "comparison.png"


def experiment_configs(
    start_url: str,
    strategies: Iterable[Strategy] = Strategy,
    scopes: Iterable[Scope] = Scope,
    link_modes: Iterable[LinkMode] = LinkMode,
    **limits: object,
) -> list[CrawlConfig]:
    """Return a crawl config for every combination of strategy, scope and link mode."""
    return [
        CrawlConfig.model_validate(
            {
                "start_url": start_url,
                "strategy": strategy,
                "scope": scope,
                "link_mode": link_mode,
                **limits,
            }
        )
        for strategy, scope, link_mode in product(strategies, scopes, link_modes)
    ]


def experiment_name(config: CrawlConfig) -> str:
    return f"{config.strategy}-{config.scope}-{config.link_mode}"


def run_experiments(
    configs: list[CrawlConfig],
    out_dir: Path,
    on_crawl: Callable[[CrawlConfig, CrawlResult], object] = lambda *_: None,
) -> list[CrawlResult]:
    """Run every crawl and save each result as `<strategy>-<scope>-<link_mode>.json`."""
    results = []
    for config in configs:
        result = crawl(config)
        result.save(out_dir / f"{experiment_name(config)}.json")
        on_crawl(config, result)
        results.append(result)
    return results


def comparison_table(results: Iterable[CrawlResult]) -> pd.DataFrame:
    """One row per crawl: its parameters followed by the statistics of its link graph."""
    rows = []
    for result in sorted(results, key=_parameter_order):
        config = result.config
        stats = compute_stats(result).model_dump(exclude={"pages_per_level", "most_linked"})
        rows.append(
            {
                "strategy": str(config.strategy),
                "scope": str(config.scope),
                "link_mode": str(config.link_mode),
                **stats,
            }
        )
    return pd.DataFrame(rows, columns=[*PARAMETERS, *GraphStats.model_fields])


def save_comparison(results: Iterable[CrawlResult], directory: Path) -> pd.DataFrame:
    """Build the comparison table and save it as CSV and as a chart in the directory.

    Raises:
        ValueError: If there are no results to compare.
    """
    table = comparison_table(results)
    if table.empty:
        raise ValueError(f"no crawl results in {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    table.to_csv(directory / SUMMARY_FILE, index=False)
    save_figure(comparison_figure(table), directory / CHART_FILE)
    return table


def load_results(directory: Path) -> list[CrawlResult]:
    """Load every crawl result saved in a directory, in name order."""
    return [CrawlResult.load(path) for path in sorted(directory.glob("*.json"))]


def _parameter_order(result: CrawlResult) -> tuple[int, int, int]:
    """Sort key that lists crawls in the order the parameters are declared."""
    config = result.config
    return (
        list(Strategy).index(config.strategy),
        list(Scope).index(config.scope),
        list(LinkMode).index(config.link_mode),
    )
