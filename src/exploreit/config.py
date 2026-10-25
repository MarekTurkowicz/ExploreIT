"""Crawl configuration."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from exploreit.fetcher import USER_AGENT
from exploreit.frontier import Strategy
from exploreit.parser import LinkMode
from exploreit.urls import Scope, normalize_url


def parse_headers(lines: str | list[str]) -> dict[str, str]:
    """Turn "Name: value" lines into a dict; blank lines are skipped.

    Raises:
        ValueError: If a line has no colon.
    """
    text = "\n".join(lines) if isinstance(lines, list) else lines
    headers = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        name, colon, value = line.partition(":")
        if not colon:
            raise ValueError(f"expected 'Name: value', got {line!r}")
        headers[name.strip()] = value.strip()
    return headers


HEADER_NAME = re.compile(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+")  # an HTTP token


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
    user_agent: str = Field(default=USER_AGENT, min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)  # extra request headers

    def describe(self) -> str:
        """One-line summary of the parameters, e.g. "bfs · server · hyperlinks · depth 3"."""
        return f"{self.strategy} · {self.scope} · {self.link_mode} · depth {self.max_depth}"

    @field_validator("headers")
    @classmethod
    def _check_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        for name, value in headers.items():
            if not HEADER_NAME.fullmatch(name):
                raise ValueError(f"invalid header name: {name!r}")
            if "\n" in value or "\r" in value:
                raise ValueError(f"header {name!r} must fit on one line")
            if name.lower() in ("user-agent", "host", "content-length"):
                raise ValueError(f"header {name!r} is set by the crawler")
        return headers

    @field_validator("start_url")
    @classmethod
    def _normalize_start_url(cls, url: str) -> str:
        return normalize_url(url)
