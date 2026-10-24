import csv
import sqlite3
from contextlib import closing
from pathlib import Path

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.models import CrawledPage, Edge, LinkKind, PageContent
from exploreit.storage import ContentField, write_csv, write_sqlite

START = "https://example.com/"
CONTENTS = [
    PageContent(url=START, title="Home", keywords=["a", "b"], body='Says "hi", twice'),
    PageContent(url=f"{START}about", title="About; us", description="Who we are"),
]


def test_csv_round_trip_with_all_fields(tmp_path: Path) -> None:
    path = tmp_path / "content.csv"

    write_csv(CONTENTS, path)

    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    assert list(rows[0]) == ["url", "title", "description", "keywords", "body"]
    assert rows[0]["keywords"] == "a, b"
    assert rows[0]["body"] == 'Says "hi", twice'
    assert rows[1]["description"] == "Who we are"


def test_csv_with_chosen_fields_and_separator(tmp_path: Path) -> None:
    path = tmp_path / "content.csv"

    write_csv(CONTENTS, path, [ContentField.URL, ContentField.KEYWORDS], separator=";")

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    assert lines == ["url;keywords", f"{START};a, b", f"{START}about;"]


def test_sqlite_holds_pages_links_and_content(tmp_path: Path) -> None:
    result = CrawlResult(
        config=CrawlConfig(start_url=START, store_content=True),
        pages=[
            CrawledPage(url=START, depth=0, status_code=200, content_type="text/html"),
            CrawledPage(url=f"{START}about", depth=1, status_code=200, content_type="text/html"),
        ],
        edges=[Edge(source=START, target=f"{START}about", kind=LinkKind.ANCHOR)],
        failed={},
        contents=CONTENTS,
    )
    path = tmp_path / "crawl.sqlite"
    path.write_text("old file")

    write_sqlite(result, path)

    with closing(sqlite3.connect(path)) as database:
        assert database.execute("SELECT COUNT(*) FROM pages").fetchone() == (2,)
        assert database.execute("SELECT kind FROM links").fetchall() == [("anchor",)]
        assert database.execute(
            "SELECT p.depth, c.title FROM pages p JOIN contents c USING (url) ORDER BY p.depth"
        ).fetchall() == [(0, "Home"), (1, "About; us")]
