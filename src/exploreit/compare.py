"""Comparison of two content databases saved as CSV.

A database is the CSV file written for a crawl: whichever fields were chosen (for
example only URL and keywords) and whichever separator. Both its structure (columns,
separator, size) and its content (pages, hosts, keywords) are compared.
"""

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from urllib.parse import urlsplit

SEPARATOR_NAMES = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}
KEYWORD_SPLIT = ","
TOP_KEYWORDS = 5


@dataclass(frozen=True)
class Database:
    path: Path
    columns: list[str]
    separator: str
    records: list[dict[str, str]]

    def column(self, name: str) -> list[str]:
        return [record.get(name, "") for record in self.records]

    def has(self, name: str) -> bool:
        return name in (column.lower() for column in self.columns)

    @property
    def urls(self) -> set[str]:
        return {url for url in self.column("url") if url}

    @property
    def keywords(self) -> Counter[str]:
        return Counter(
            keyword.strip().lower()
            for value in self.column("keywords")
            for keyword in value.split(KEYWORD_SPLIT)
            if keyword.strip()
        )


def load_database(path: Path) -> Database:
    """Read a CSV database; the separator is detected from the file.

    Raises:
        ValueError: If the file is empty or has no url column.
    """
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError(f"{path.name} is empty")
    try:
        separator = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t|").delimiter
    except csv.Error:
        separator = ","
    rows = list(csv.reader(text.splitlines(), delimiter=separator))
    columns = rows[0]
    names = [column.strip().lower() for column in columns]
    if "url" not in names:
        raise ValueError(f"{path.name} has no url column, so it is not a content database")
    records = [dict(zip(names, row, strict=False)) for row in rows[1:] if any(row)]
    return Database(path, columns, separator, records)


def comparison_rows(first: Database, second: Database) -> list[tuple[str, str, str]]:
    """(what, first database, second database) rows: structure first, then content."""
    rows = [
        ("STRUCTURE", "", ""),
        ("Columns", ", ".join(first.columns), ", ".join(second.columns)),
        ("Separator", _separator(first), _separator(second)),
        ("Records (pages)", str(len(first.records)), str(len(second.records))),
        ("File size", _size(first.path), _size(second.path)),
        ("CONTENT", "", ""),
    ]
    rows += _paired(_content(first), _content(second))
    common = first.urls & second.urls
    rows.append(("Pages in both", str(len(common)), str(len(common))))
    rows.append(("Pages only here", str(len(first.urls - common)), str(len(second.urls - common))))
    first_words, second_words = set(first.keywords), set(second.keywords)
    if first.has("keywords") and second.has("keywords"):
        shared = first_words & second_words
        union = first_words | second_words
        similarity = f"{len(shared)} ({len(shared) / len(union):.0%} of all)" if union else "0"
        rows.append(("Keywords in both", similarity, similarity))
    return rows


def _content(database: Database) -> list[tuple[str, str]]:
    hosts = Counter(urlsplit(url).netloc for url in database.column("url") if url)
    main_host = hosts.most_common(1)[0][0] if hosts else ""
    rows = [
        ("Hosts", str(len(hosts))),
        ("Most common host", main_host or "-"),
        ("Pages on other hosts", str(sum(hosts.values()) - hosts[main_host])),
    ]
    for column, label in (("title", "With title"), ("description", "With description")):
        rows.append((label, _filled(database, column)))
    keywords = database.keywords
    rows.append(("With keywords", _filled(database, "keywords")))
    rows.append(
        ("Distinct keywords", str(len(keywords)) if database.has("keywords") else "no column")
    )
    top = ", ".join(f"{word} ({count})" for word, count in keywords.most_common(TOP_KEYWORDS))
    rows.append(("Most common keywords", top or "-"))
    if database.has("body"):
        words = [len(body.split()) for body in database.column("body")]
        rows.append(("Mean body length (words)", f"{fmean(words):.1f}" if words else "0"))
    else:
        rows.append(("Mean body length (words)", "no column"))
    return rows


def _filled(database: Database, column: str) -> str:
    if not database.has(column):
        return "no column"
    return str(sum(bool(value.strip()) for value in database.column(column)))


def _paired(
    first: list[tuple[str, str]], second: list[tuple[str, str]]
) -> list[tuple[str, str, str]]:
    return [(label, a, b) for (label, a), (_, b) in zip(first, second, strict=True)]


def _separator(database: Database) -> str:
    return SEPARATOR_NAMES.get(database.separator, repr(database.separator))


def _size(path: Path) -> str:
    return f"{path.stat().st_size / 1024:.1f} KB"
