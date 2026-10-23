import pytest
from pydantic import ValidationError

from exploreit.config import CrawlConfig
from exploreit.frontier import Strategy
from exploreit.parser import LinkMode
from exploreit.urls import Scope


def test_defaults() -> None:
    config = CrawlConfig(start_url="https://example.com")

    assert config.start_url == "https://example.com/"
    assert config.strategy is Strategy.BFS
    assert config.scope is Scope.SERVER
    assert config.link_mode is LinkMode.HYPERLINKS


def test_options_accept_strings() -> None:
    config = CrawlConfig.model_validate(
        {"start_url": "https://example.com", "strategy": "dfs", "scope": "web", "link_mode": "all"}
    )

    assert config.strategy is Strategy.DFS
    assert config.scope is Scope.WEB
    assert config.link_mode is LinkMode.ALL


@pytest.mark.parametrize(
    "fields",
    [
        {"start_url": "example.com"},
        {"start_url": "ftp://example.com/"},
        {"start_url": "https://example.com", "max_depth": -1},
        {"start_url": "https://example.com", "max_pages": 0},
        {"start_url": "https://example.com", "strategy": "random"},
    ],
)
def test_invalid_config_is_rejected(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CrawlConfig.model_validate(fields)
