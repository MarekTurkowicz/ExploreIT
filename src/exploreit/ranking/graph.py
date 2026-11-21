"""The link graph that pages are ranked on, and the checks it has to pass."""

import hashlib
from collections import Counter, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from urllib.parse import urlsplit

from pydantic import BaseModel

from exploreit.crawler import CrawlResult
from exploreit.models import Region

MIN_PAGES = 20
MIN_CYCLE = 3


@dataclass(frozen=True)
class LinkGraph:
    """Visited pages and the links between them, in a fixed order.

    The order of `pages` is the row and column order of every matrix built from the
    graph, so results can always be matched back to a page.
    """

    pages: tuple[str, ...]
    links: tuple[tuple[str, str], ...]
    # Title, description, keywords and body of every page, when the crawl kept content.
    texts: Mapping[str, str] = field(default_factory=dict)
    # Where on the source page each link stands; links not listed are in the content.
    regions: Mapping[tuple[str, str], Region] = field(default_factory=dict)
    # Duplicate URL -> the page it was merged into.
    merged: Mapping[str, str] = field(default_factory=dict)

    @cached_property
    def out_links(self) -> dict[str, list[str]]:
        targets: dict[str, list[str]] = {page: [] for page in self.pages}
        for source, target in self.links:
            targets[source].append(target)
        return targets

    @cached_property
    def in_degree(self) -> Counter[str]:
        return Counter(target for _, target in self.links)


class Requirement(BaseModel):
    """One condition the graph must meet, with what it actually has."""

    description: str
    required: int
    actual: int

    @property
    def met(self) -> bool:
        return self.actual >= self.required


def link_graph(
    result: CrawlResult, html_only: bool = True, merge_duplicates: bool = False
) -> LinkGraph:
    """Build the ranking graph from a crawl.

    Only visited pages become nodes (by default only HTML pages, since images and
    other files have no links of their own). Links to unvisited pages, repeated links
    and links from a page to itself are left out: a page cannot vote for itself.

    With `merge_duplicates`, addresses of one page become one node (see `duplicates`).
    """
    pages = tuple(dict.fromkeys(page.url for page in result.pages if page.is_html or not html_only))
    visited = set(pages)
    texts = {
        content.url: " ".join(
            [content.title, content.description, " ".join(content.keywords), content.body]
        )
        for content in result.contents
        if content.url in visited
    }
    merged = duplicates(pages, texts) if merge_duplicates else {}
    pages = tuple(page for page in pages if page not in merged)
    known = set(pages)
    for duplicate, kept in merged.items():
        if duplicate in texts and kept not in texts:
            texts[kept] = texts[duplicate]
    regions: dict[tuple[str, str], Region] = {}
    for edge in result.edges:
        source, target = merged.get(edge.source, edge.source), merged.get(edge.target, edge.target)
        if source not in known or target not in known or source == target:
            continue
        # Two addresses of one page may link to the same target from different places.
        if (source, target) not in regions or _more_prominent(edge.region, regions[source, target]):
            regions[source, target] = edge.region
    links = tuple(regions)
    texts = {page: text for page, text in texts.items() if page in known}
    return LinkGraph(pages, links, texts, regions, merged)


def duplicates(pages: Iterable[str], texts: Mapping[str, str]) -> dict[str, str]:
    """Map every duplicate address to the page it is a copy of.

    Two addresses are one page when they differ only in http/https or a leading
    "www.", or when the crawl stored exactly the same text for both (for example
    "/" and "/page/1/"). The kept address is the https one, then the shortest.
    """
    groups: dict[str, str] = {}  # union-find: page -> a page of the same group

    def root(page: str) -> str:
        while groups.setdefault(page, page) != page:
            page = groups[page]
        return page

    first_with: dict[str, str] = {}
    for page in pages:
        root(page)
        keys = [_address_key(page)]
        if text := texts.get(page, "").strip():
            keys.append("text:" + hashlib.sha1(text.encode()).hexdigest())
        for key in keys:
            if key in first_with:
                groups[root(page)] = root(first_with[key])
            else:
                first_with[key] = page

    members: dict[str, list[str]] = {}
    for page in groups:
        members.setdefault(root(page), []).append(page)
    result: dict[str, str] = {}
    for group in members.values():
        kept = min(group, key=lambda page: (not page.startswith("https:"), len(page), page))
        result.update({page: kept for page in group if page != kept})
    return result


def _address_key(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.removeprefix("www.")
    return f"url:{host}{parts.path}?{parts.query}"


def _more_prominent(region: Region, than: Region) -> bool:
    order = list(Region)
    return order.index(region) < order.index(than)


def check_requirements(graph: LinkGraph) -> list[Requirement]:
    """Whether the graph is rich enough to rank: pages, popular pages and a long cycle."""
    in_degree = graph.in_degree
    return [
        Requirement(
            description=f"pages (at least {MIN_PAGES})",
            required=MIN_PAGES,
            actual=len(graph.pages),
        ),
        Requirement(
            description="pages with at least 2 incoming links",
            required=3,
            actual=sum(count >= 2 for count in in_degree.values()),
        ),
        Requirement(
            description="pages with at least 3 incoming links",
            required=1,
            actual=sum(count >= 3 for count in in_degree.values()),
        ),
        Requirement(
            description=f"length of the shortest cycle of {MIN_CYCLE}+ pages",
            required=MIN_CYCLE,
            actual=len(shortest_cycle(graph)),
        ),
    ]


def shortest_cycle(graph: LinkGraph, min_length: int = MIN_CYCLE) -> list[str]:
    """Return the shortest cycle with at least `min_length` pages, or [] if there is none.

    For every link u -> v, a breadth-first search looks for the shortest way back from
    v to u that does not jump straight back (that would be a two-page cycle). Plain DFS
    back edges are not enough: they can report only a two-page cycle while a longer one
    exists through the same pages.
    """
    best: list[str] = []
    for source, target in graph.links:
        path = _shortest_path(graph, target, source, first_step_not=source)
        cycle = [source, *path[:-1]]
        if len(cycle) >= min_length and (not best or len(cycle) < len(best)):
            best = cycle
            if len(best) == min_length:
                break  # cannot get any shorter
    return best


def _shortest_path(graph: LinkGraph, start: str, goal: str, first_step_not: str) -> list[str]:
    """Shortest path start -> ... -> goal whose first step is not `first_step_not`."""
    previous: dict[str, str] = {}
    queue = deque([start])
    seen = {start}
    while queue:
        page = queue.popleft()
        for target in graph.out_links[page]:
            if page == start and target == first_step_not:
                continue
            if target in seen:
                continue
            previous[target] = page
            if target == goal:
                path = [goal]
                while path[-1] != start:
                    path.append(previous[path[-1]])
                return path[::-1]
            seen.add(target)
            queue.append(target)
    return []
