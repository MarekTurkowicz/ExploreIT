"""Adjacency matrices of the ranking graph."""

import csv
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from exploreit.ranking.graph import LinkGraph

type Matrix = NDArray[np.float64]


def adjacency_matrix(graph: LinkGraph, weighted: bool = False) -> Matrix:
    """Return A where A[v, u] = 1 if page v links to page u, else 0.

    Rows are where a link starts, columns where it ends, both in `graph.pages` order.
    With `weighted`, every link of page v counts 1/Nv, where Nv is the number of links
    leaving v, so each page shares one vote among the pages it links to. Rows of pages
    without outgoing links stay all zero.
    """
    index = {page: position for position, page in enumerate(graph.pages)}
    matrix = np.zeros((len(graph.pages), len(graph.pages)))
    for source, target in graph.links:
        matrix[index[source], index[target]] = 1.0
    if weighted:
        out_links = matrix.sum(axis=1, keepdims=True)
        matrix = np.divide(matrix, out_links, out=np.zeros_like(matrix), where=out_links > 0)
    return matrix


MUTUAL_LINK_WEIGHT = 0.5  # a link returned by its target counts half
MENU_LINK_DISCOUNT = 0.9  # a link to a page every page links to keeps a tenth


def trusted_matrix(graph: LinkGraph) -> Matrix:
    """Weighted matrix that resists link spam, rows summing to 1 like 1/Nv.

    Two kinds of links are trusted less before each page shares out its vote:
    - mutual links (v -> u and u -> v), the classic "link to me and I link to you";
    - links to pages that nearly every page links to, which are navigation (menus,
      login, footer) rather than a recommendation: weight 1 - 0.9 * share of pages
      linking to the target.
    """
    matrix = adjacency_matrix(graph)
    size = max(len(graph.pages), 1)
    mutual = (matrix > 0) & (matrix.T > 0)
    matrix = np.where(mutual, matrix * MUTUAL_LINK_WEIGHT, matrix)
    linked_from = (adjacency_matrix(graph) > 0).sum(axis=0) / size
    matrix = matrix * (1 - MENU_LINK_DISCOUNT * linked_from)  # scales each column (target)
    out_links = matrix.sum(axis=1, keepdims=True)
    result: Matrix = np.divide(matrix, out_links, out=np.zeros_like(matrix), where=out_links > 0)
    return result


def dangling_pages(graph: LinkGraph) -> list[str]:
    """Pages that link to no other page in the graph; their votes go nowhere."""
    return [page for page in graph.pages if not graph.out_links[page]]


def short_labels(graph: LinkGraph) -> list[str]:
    """Compact names P1, P2, ... for matrix headers; long URLs make a matrix unreadable."""
    return [f"P{position}" for position in range(1, len(graph.pages) + 1)]


def write_matrix_csv(matrix: Matrix, labels: Sequence[str], path: Path) -> None:
    """Save a matrix with row and column labels, e.g. for a spreadsheet or a report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["", *labels])
        for label, row in zip(labels, matrix, strict=True):
            writer.writerow([label, *(_format(value) for value in row)])


def write_legend_csv(graph: LinkGraph, path: Path) -> None:
    """Save which short label stands for which page."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["label", "url", "links out", "links in"])
        for label, page in zip(short_labels(graph), graph.pages, strict=True):
            writer.writerow([label, page, len(graph.out_links[page]), graph.in_degree[page]])


def _format(value: float) -> str:
    """1 and 0 stay short; fractions such as 1/3 keep four decimals."""
    return f"{value:g}" if float(value).is_integer() else f"{value:.4f}"
