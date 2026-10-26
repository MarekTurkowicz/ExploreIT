"""Bridges: how many shortest click paths between other pages pass through a page.

A page can matter without many incoming links when it connects parts of a site that
would otherwise be far apart, like a category index. This is betweenness centrality,
computed with Brandes' algorithm: one breadth-first search per page counts the shortest
paths, then a walk back from the farthest pages shares the credit out.
"""

from collections import deque

import numpy as np

from exploreit.ranking.graph import LinkGraph


def betweenness(graph: LinkGraph) -> np.ndarray:
    """Share of shortest paths between other pages that run through each page (0 to 1)."""
    pages = graph.pages
    size = len(pages)
    score = dict.fromkeys(pages, 0.0)
    for source in pages:
        # Breadth-first search: distance and number of shortest paths from `source`.
        order: list[str] = []
        parents: dict[str, list[str]] = {page: [] for page in pages}
        paths = dict.fromkeys(pages, 0)
        distance = dict.fromkeys(pages, -1)
        paths[source], distance[source] = 1, 0
        queue = deque([source])
        while queue:
            page = queue.popleft()
            order.append(page)
            for target in graph.out_links[page]:
                if distance[target] < 0:
                    distance[target] = distance[page] + 1
                    queue.append(target)
                if distance[target] == distance[page] + 1:
                    paths[target] += paths[page]
                    parents[target].append(page)
        # Walk back from the farthest pages, handing each page its share of the paths.
        credit = dict.fromkeys(pages, 0.0)
        for page in reversed(order):
            for parent in parents[page]:
                credit[parent] += paths[parent] / paths[page] * (1 + credit[page])
            if page != source:
                score[page] += credit[page]
    pairs = (size - 1) * (size - 2)  # ordered pairs of other pages in a directed graph
    values = np.array([score[page] for page in pages])
    return values / pairs if pairs else values
