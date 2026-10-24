"""Saving crawled page content to CSV and SQLite."""

import csv
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from enum import StrEnum
from pathlib import Path

from exploreit.crawler import CrawlResult
from exploreit.models import PageContent

KEYWORD_SEPARATOR = ", "

SCHEMA = """
CREATE TABLE crawl (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE pages (
    url TEXT PRIMARY KEY,
    depth INTEGER NOT NULL,
    status_code INTEGER NOT NULL,
    content_type TEXT NOT NULL
);
CREATE TABLE contents (
    url TEXT PRIMARY KEY REFERENCES pages (url),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    keywords TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE links (
    source TEXT NOT NULL REFERENCES pages (url),
    target TEXT NOT NULL,
    kind TEXT NOT NULL
);
CREATE INDEX links_target ON links (target);
"""


class ContentField(StrEnum):
    """A column that can be saved for every page."""

    URL = "url"
    TITLE = "title"
    DESCRIPTION = "description"
    KEYWORDS = "keywords"
    BODY = "body"


def write_csv(
    contents: Sequence[PageContent],
    path: Path,
    fields: Sequence[ContentField] = tuple(ContentField),
    separator: str = ",",
) -> None:
    """Save the chosen fields of every page as CSV (UTF-8 with BOM, so Excel reads it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=separator)
        writer.writerow(fields)
        for content in contents:
            values = content.model_dump() | {"keywords": KEYWORD_SEPARATOR.join(content.keywords)}
            writer.writerow(values[field] for field in fields)


def write_sqlite(result: CrawlResult, path: Path) -> None:
    """Save the whole crawl, including links and content, as a new SQLite database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with closing(sqlite3.connect(path)) as database, database:
        database.executescript(SCHEMA)
        database.execute(
            "INSERT INTO crawl VALUES ('config', ?)", (result.config.model_dump_json(),)
        )
        database.executemany(
            "INSERT INTO pages VALUES (?, ?, ?, ?)",
            ((p.url, p.depth, p.status_code, p.content_type) for p in result.pages),
        )
        database.executemany(
            "INSERT INTO contents VALUES (?, ?, ?, ?, ?)",
            (
                (c.url, c.title, c.description, KEYWORD_SEPARATOR.join(c.keywords), c.body)
                for c in result.contents
            ),
        )
        database.executemany(
            "INSERT INTO links VALUES (?, ?, ?)",
            ((e.source, e.target, e.kind.value) for e in result.edges),
        )
