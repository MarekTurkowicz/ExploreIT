import pytest

from exploreit.frontier import Frontier, Strategy


def drain(frontier: Frontier) -> list[str]:
    urls = []
    while frontier:
        url, _ = frontier.pop()
        urls.append(url)
    return urls


def test_strategy_from_string() -> None:
    assert Strategy("dfs") is Strategy.DFS


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        (Strategy.BFS, ["a", "b", "c"]),
        (Strategy.DFS, ["c", "b", "a"]),
    ],
)
def test_pop_order(strategy: Strategy, expected: list[str]) -> None:
    frontier = Frontier(strategy)
    for url in ["a", "b", "c"]:
        frontier.add(url, depth=1)

    assert drain(frontier) == expected


def test_pop_returns_depth() -> None:
    frontier = Frontier(Strategy.BFS)
    frontier.add("a", depth=3)

    assert frontier.pop() == ("a", 3)


def test_duplicate_url_is_added_once() -> None:
    frontier = Frontier(Strategy.BFS)

    assert frontier.add("a", depth=0)
    assert not frontier.add("a", depth=1)
    assert len(frontier) == 1


def test_popped_url_is_not_added_again() -> None:
    frontier = Frontier(Strategy.DFS)
    frontier.add("a", depth=0)
    frontier.pop()

    assert not frontier.add("a", depth=1)
    assert len(frontier) == 0


def test_pop_from_empty_frontier_raises() -> None:
    with pytest.raises(IndexError):
        Frontier(Strategy.BFS).pop()


def test_bfs_visits_level_by_level() -> None:
    site = {"/": ["/a", "/b"], "/a": ["/a/1", "/a/2"], "/b": [], "/a/1": [], "/a/2": []}
    frontier = Frontier(Strategy.BFS)
    frontier.add("/", depth=0)

    visited = []
    while frontier:
        url, depth = frontier.pop()
        visited.append((url, depth))
        for child in site[url]:
            frontier.add(child, depth + 1)

    assert visited == [("/", 0), ("/a", 1), ("/b", 1), ("/a/1", 2), ("/a/2", 2)]
