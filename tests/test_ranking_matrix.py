import csv
from pathlib import Path

import numpy as np

from exploreit.ranking.graph import LinkGraph
from exploreit.ranking.matrix import (
    adjacency_matrix,
    dangling_pages,
    short_labels,
    write_legend_csv,
    write_matrix_csv,
)

#   a -> b, a -> c, b -> c, c -> a, d -> a        (d has no incoming links)
#   e has no outgoing links
GRAPH = LinkGraph(
    pages=("a", "b", "c", "d", "e"),
    links=(("a", "b"), ("a", "c"), ("b", "c"), ("c", "a"), ("d", "a"), ("b", "e")),
)


def read(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.reader(file))


def test_adjacency_matrix_rows_are_sources_columns_are_targets() -> None:
    matrix = adjacency_matrix(GRAPH)

    assert matrix.shape == (5, 5)
    assert matrix[0, 1] == 1  # a -> b
    assert matrix[1, 0] == 0  # no b -> a
    assert matrix.sum() == len(GRAPH.links)
    assert matrix.sum(axis=0).tolist() == [2, 1, 2, 0, 1]  # incoming links per page


def test_weighted_matrix_shares_each_page_vote() -> None:
    matrix = adjacency_matrix(GRAPH, weighted=True)

    assert matrix[0, 1] == matrix[0, 2] == 0.5  # a has two links
    assert matrix[2, 0] == 1.0  # c has one link
    assert np.allclose(matrix.sum(axis=1), [1, 1, 1, 1, 0])  # e votes for nobody


def test_dangling_pages() -> None:
    assert dangling_pages(GRAPH) == ["e"]


def test_matrix_and_legend_csv(tmp_path: Path) -> None:
    labels = short_labels(GRAPH)

    write_matrix_csv(adjacency_matrix(GRAPH, weighted=True), labels, tmp_path / "a.csv")
    write_legend_csv(GRAPH, tmp_path / "legend.csv")

    rows = read(tmp_path / "a.csv")
    assert rows[0] == ["", "P1", "P2", "P3", "P4", "P5"]
    assert rows[1] == ["P1", "0", "0.5000", "0.5000", "0", "0"]
    assert rows[2] == ["P2", "0", "0", "0.5000", "0", "0.5000"]
    assert read(tmp_path / "legend.csv")[1] == ["P1", "a", "2", "2"]
