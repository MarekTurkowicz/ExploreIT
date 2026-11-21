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
    size = len(graph.pages)
    index = {page: position for position, page in enumerate(graph.pages)}
    out_links = [[index[target] for target in graph.out_links[page]] for page in graph.pages]
    score = [0.0] * size
    for source in range(size):
        # Breadth-first search: distance and number of shortest paths from `source`.
        order: list[int] = []
        parents: list[list[int]] = [[] for _ in range(size)]
        paths = [0] * size
        distance = [-1] * size
        paths[source], distance[source] = 1, 0
        queue = deque([source])
        while queue:
            page = queue.popleft()
            order.append(page)
            step = distance[page] + 1
            for target in out_links[page]:
                if distance[target] < 0:
                    distance[target] = step
                    queue.append(target)
                if distance[target] == step:
                    paths[target] += paths[page]
                    parents[target].append(page)
        # Walk back from the farthest pages, handing each page its share of the paths.
        credit = [0.0] * size
        for page in reversed(order):
            share = (1 + credit[page]) / paths[page]
            for parent in parents[page]:
                credit[parent] += paths[parent] * share
            if page != source:
                score[page] += credit[page]
    pairs = (size - 1) * (size - 2)  # ordered pairs of other pages in a directed graph
    values = np.array(score)
    return values / pairs if pairs else values
