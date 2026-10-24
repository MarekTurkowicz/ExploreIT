"""Structure statistics of a crawled link graph."""

from collections import Counter, defaultdict, deque
from statistics import fmean
from urllib.parse import urlsplit

from pydantic import BaseModel

from exploreit.crawler import CrawlResult


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
    crawl_seconds: float

    def summary(self) -> list[tuple[str, str]]:
        """Return the statistics as human-readable (label, value) rows."""
        levels = ", ".join(f"{level}: {count}" for level, count in self.pages_per_level.items())
        rows = [
            ("Pages visited", f"{self.pages} ({self.html_pages} HTML)"),
            ("Error pages / failed", f"{self.error_pages} / {self.failed}"),
            ("Linked but not visited", str(self.unvisited_targets)),
            (
                "Links",
                f"{self.links} ({self.internal_links} internal, {self.external_links} external)",
            ),
            ("Graph depth", str(self.depth)),
            ("Pages per level", levels),
            ("Links on start page", str(self.start_page_links)),
            (
                "Links on subpages",
                f"{self.subpage_links_mean:.1f} mean, {self.subpage_links_max} max",
            ),
            ("Pages without links", str(self.dead_ends)),
            ("Crawl time", format_duration(self.crawl_seconds)),
        ]
        rows += [(f"Linked from {count} pages", url) for url, count in self.most_linked]
        return rows


def compute_stats(result: CrawlResult, top: int = 5) -> GraphStats:
    """Describe the link graph of a crawl.

    Levels are shortest click distances from the start page, so they do not depend
    on the order in which the crawler happened to discover pages.
    """
    start = result.config.start_url
    visited = {page.url for page in result.pages}
    html = [page for page in result.pages if page.is_html]
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
        crawl_seconds=round(result.duration, 1),
    )


def format_duration(seconds: float) -> str:
    """Format seconds as "m:ss", e.g. 75.4 -> "1:15"."""
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes}:{rest:02d}"


def click_tree(result: CrawlResult) -> dict[str, list[str]]:
    """Return a breadth-first spanning tree of visited pages, rooted at the start page.

    Each page maps to the pages first reached from it, so the path from the root to
    any page is a shortest path. Pages are listed parents first.
    """
    visited = {page.url for page in result.pages}
    start = result.config.start_url
    if start not in visited:
        return {}

    links: defaultdict[str, list[str]] = defaultdict(list)
    for edge in result.edges:
        links[edge.source].append(edge.target)

    children: dict[str, list[str]] = {start: []}
    queue = deque([start])
    while queue:
        url = queue.popleft()
        for target in links[url]:
            if target in visited and target not in children:
                children[url].append(target)
                children[target] = []
                queue.append(target)
    return children


def shortest_levels(result: CrawlResult) -> dict[str, int]:
    """Return the fewest clicks from the start page to every visited page."""
    levels: dict[str, int] = {}
    for url, children in click_tree(result).items():
        level = levels.setdefault(url, 0)
        for child in children:
            levels[child] = level + 1
    return levels
