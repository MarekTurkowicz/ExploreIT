"""Helpers shared by the tabs of the interface."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import ValidationError
from textual.message import Message
from textual.widgets import Select

from exploreit.crawler import CrawlResult


class CrawlLoaded(Message):
    """A crawl result is ready to be shown, either freshly crawled or opened from disk."""

    def __init__(self, result: CrawlResult, path: Path) -> None:
        super().__init__()
        self.result = result
        self.path = path


def enum_select[E: StrEnum](options: type[E], default: E, widget_id: str) -> Select[E]:
    return Select(
        [(option.value, option) for option in options],
        value=default,
        allow_blank=False,
        id=widget_id,
    )


def saved_crawls(data_dir: Path) -> list[tuple[str, Path]]:
    """Return (label, path) options for every saved crawl result, newest first."""
    paths = sorted(data_dir.rglob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [(str(path.relative_to(data_dir)), path) for path in paths]


def timestamp() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}"


def describe_errors(error: ValidationError) -> str:
    return "\n".join(f"{problem['loc'][0]}: {problem['msg']}" for problem in error.errors())


def shorten(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"
