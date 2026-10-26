"""The link graph that pages are ranked on, and the checks it has to pass."""

from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property

from pydantic import BaseModel

from exploreit.crawler import CrawlResult

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


def link_graph(result: CrawlResult, html_only: bool = True) -> LinkGraph:
    """Build the ranking graph from a crawl.

    Only visited pages become nodes (by default only HTML pages, since images and
    other files have no links of their own). Links to unvisited pages, repeated links
    and links from a page to itself are left out: a page cannot vote for itself.
    """
    pages = tuple(dict.fromkeys(page.url for page in result.pages if page.is_html or not html_only))
    known = set(pages)
    links = tuple(
        dict.fromkeys(
            (edge.source, edge.target)
            for edge in result.edges
            if edge.source in known and edge.target in known and edge.source != edge.target
        )
    )
    texts = {
        content.url: " ".join(
            [content.title, content.description, " ".join(content.keywords), content.body]
        )
        for content in result.contents
        if content.url in known
    }
    return LinkGraph(pages, links, texts)


def check_requirements(graph: LinkGraph) -> list[Requirement]:
    """The conditions of the task: enough pages, popular pages and a long enough cycle."""
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
