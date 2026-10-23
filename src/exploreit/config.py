"""Crawl configuration."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from exploreit.frontier import Strategy
from exploreit.parser import LinkMode
from exploreit.urls import Scope, normalize_url


class CrawlConfig(BaseModel):
    """Parameters of a single crawl."""

    model_config = ConfigDict(frozen=True)

    start_url: str
    strategy: Strategy = Strategy.BFS
    scope: Scope = Scope.SERVER
    link_mode: LinkMode = LinkMode.HYPERLINKS
    max_depth: int = Field(default=3, ge=0)
    max_pages: int = Field(default=100, ge=1)
    delay: float = Field(default=1.0, ge=0)
    timeout: float = Field(default=10.0, gt=0)
    respect_robots: bool = True
    store_content: bool = False

    @field_validator("start_url")
    @classmethod
    def _normalize_start_url(cls, url: str) -> str:
        return normalize_url(url)
