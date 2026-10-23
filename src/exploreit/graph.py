"""Structure statistics of a crawled link graph."""

from collections import Counter, defaultdict, deque
from statistics import fmean
from urllib.parse import urlsplit

from pydantic import BaseModel

from exploreit.crawler import CrawlResult
from exploreit.fetcher import HTML_TYPES
from exploreit.models import CrawledPage


class GraphStats(BaseModel):
    """Numbers that describe the shape of a crawled site."""

    pages: int
    html_pages: int
    error_pages: int
    failed: int
    unvisited_targets: int
    links: int
    internal_links: int
    external_links: int
    depth: int
    pages_per_level: dict[int, int]
    start_page_links: int
    subpage_links_mean: float
    subpage_links_max: int
    dead_ends: int
    most_linked: list[tuple[str, int]]


def compute_stats(result: CrawlResult, top: int = 5) -> GraphStats:
    """Describe the link graph of a crawl.

    Levels are shortest click distances from the start page, so they do not depend
    on the order in which the crawler happened to discover pages.
    """
    start = result.config.start_url
    visited = {page.url for page in result.pages}
    html = [page for page in result.pages if _is_html(page)]
    out_degree = Counter(edge.source for edge in result.edges)
    in_degree = Counter(edge.target for edge in result.edges)

    levels = shortest_levels(result)
    subpage_links = [out_degree[page.url] for page in html if page.url != start]
    host = urlsplit(start).netloc
    external = sum(urlsplit(edge.target).netloc != host for edge in result.edges)

    return GraphStats(
        pages=len(result.pages),
        html_pages=len(html),
        error_pages=sum(page.status_code >= 400 for page in result.pages),
        failed=len(result.failed),
        unvisited_targets=len(in_degree.keys() - visited),
        links=len(result.edges),
        internal_links=len(result.edges) - external,
        external_links=external,
        depth=max(levels.values(), default=0),
        pages_per_level=dict(sorted(Counter(levels.values()).items())),
        start_page_links=out_degree[start],
        subpage_links_mean=fmean(subpage_links) if subpage_links else 0.0,
        subpage_links_max=max(subpage_links, default=0),
        dead_ends=sum(out_degree[page.url] == 0 for page in html),
        most_linked=in_degree.most_common(top),
    )


def shortest_levels(result: CrawlResult) -> dict[str, int]:
    """Return the fewest clicks from the start page to every visited page (BFS)."""
    visited = {page.url for page in result.pages}
    start = result.config.start_url
    if start not in visited:
        return {}

    links: defaultdict[str, list[str]] = defaultdict(list)
    for edge in result.edges:
        links[edge.source].append(edge.target)

    levels = {start: 0}
    queue = deque([start])
    while queue:
        url = queue.popleft()
        for target in links[url]:
            if target in visited and target not in levels:
                levels[target] = levels[url] + 1
                queue.append(target)
    return levels


def _is_html(page: CrawledPage) -> bool:
    return page.content_type in HTML_TYPES and 200 <= page.status_code < 300
