"""The crawl frontier: URLs waiting to be visited."""

from collections import deque
from enum import StrEnum


class Strategy(StrEnum):
    """The order in which the crawler visits discovered pages."""

    BFS = "bfs"
    DFS = "dfs"


class Frontier:
    """A queue (BFS) or stack (DFS) of URLs that admits each URL only once."""

    def __init__(self, strategy: Strategy) -> None:
        self.strategy = strategy
        self._pending: deque[tuple[str, int]] = deque()
        self._seen: set[str] = set()

    def add(self, url: str, depth: int) -> bool:
        """Schedule a URL found at the given depth. Return False if it was already added."""
        if url in self._seen:
            return False
        self._seen.add(url)
        self._pending.append((url, depth))
        return True

    def pop(self) -> tuple[str, int]:
        """Remove and return the next (url, depth) pair.

        Raises:
            IndexError: If the frontier is empty.
        """
        if self.strategy is Strategy.BFS:
            return self._pending.popleft()
        return self._pending.pop()

    def __len__(self) -> int:
        return len(self._pending)
