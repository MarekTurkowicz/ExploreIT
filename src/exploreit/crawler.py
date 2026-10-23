"""The crawl loop: fetch pages, extract links and record the link graph."""

from collections.abc import Callable
from pathlib import Path
from typing import Self

from pydantic import BaseModel

from exploreit.config import CrawlConfig
from exploreit.fetcher import Fetcher, FetchError
from exploreit.frontier import Frontier
from exploreit.models import CrawledPage, Edge
from exploreit.parser import extract_links
from exploreit.urls import is_in_scope


class CrawlResult(BaseModel):
    """Everything a crawl produced: visited pages, links between them and failures."""

    config: CrawlConfig
    pages: list[CrawledPage]
    edges: list[Edge]
    failed: dict[str, str]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def crawl(
    config: CrawlConfig, on_page: Callable[[CrawledPage], object] = lambda _: None
) -> CrawlResult:
    """Crawl from the start URL until the frontier is empty or max_pages is reached.

    Every link found on a visited page becomes an edge, including links that lead
    outside the scope. Only in-scope links within max_depth are visited.
    """
    frontier = Frontier(config.strategy)
    frontier.add(config.start_url, depth=0)
    pages: list[CrawledPage] = []
    edges: list[Edge] = []
    failed: dict[str, str] = {}

    with Fetcher(
        delay=config.delay, timeout=config.timeout, respect_robots=config.respect_robots
    ) as fetcher:
        while frontier and len(pages) < config.max_pages:
            url, depth = frontier.pop()
            try:
                page = fetcher.fetch(url)
            except FetchError as error:
                failed[url] = str(error)
                continue

            crawled = CrawledPage(
                url=url,
                depth=depth,
                status_code=page.status_code,
                content_type=page.content_type,
            )
            pages.append(crawled)
            on_page(crawled)

            if not page.html:
                continue
            for link in extract_links(page.html, page.url, config.link_mode):
                edges.append(Edge(source=url, target=link.url, kind=link.kind))
                if depth < config.max_depth and is_in_scope(
                    link.url, config.start_url, config.scope
                ):
                    frontier.add(link.url, depth + 1)

    return CrawlResult(config=config, pages=pages, edges=edges, failed=failed)
