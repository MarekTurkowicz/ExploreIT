from pathlib import Path

import pytest

from exploreit.compare import comparison_rows, load_database

A = """url,keywords
https://example.com/,"love, life"
https://example.com/a,love
https://other.org/,
"""

B = """url;title;description;keywords;body
https://example.com/;Home;Welcome;love;one two three
https://example.com/b;B;;books;four five
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8-sig")
    return path


def rows(tmp_path: Path) -> dict[str, tuple[str, str]]:
    first = load_database(write(tmp_path, "a.csv", A))
    second = load_database(write(tmp_path, "b.csv", B))
    return {label: (a, b) for label, a, b in comparison_rows(first, second)}


def test_database_is_read_with_its_own_separator(tmp_path: Path) -> None:
    database = load_database(write(tmp_path, "b.csv", B))

    assert database.separator == ";"
    assert database.columns == ["url", "title", "description", "keywords", "body"]
    assert len(database.records) == 2
    assert database.keywords == {"love": 1, "books": 1}


def test_structure_is_compared(tmp_path: Path) -> None:
    compared = rows(tmp_path)

    assert compared["Columns"] == ("url, keywords", "url, title, description, keywords, body")
    assert compared["Separator"] == ("comma", "semicolon")
    assert compared["Records (pages)"] == ("3", "2")


def test_content_is_compared(tmp_path: Path) -> None:
    compared = rows(tmp_path)

    assert compared["Hosts"] == ("2", "1")
    assert compared["Pages on other hosts"] == ("1", "0")
    assert compared["With title"] == ("no column", "2")
    assert compared["With keywords"] == ("2", "2")
    assert compared["Distinct keywords"] == ("2", "2")
    assert compared["Mean body length (words)"] == ("no column", "2.5")
    assert compared["Pages in both"] == ("1", "1")
    assert compared["Pages only here"] == ("2", "1")
    assert compared["Keywords in both"][0] == "1 (33% of all)"


def test_single_column_database(tmp_path: Path) -> None:
    database = load_database(write(tmp_path, "urls.csv", "url\nhttps://example.com/\n"))

    assert database.columns == ["url"]
    assert database.urls == {"https://example.com/"}


@pytest.mark.parametrize("text", ["", "title,body\nA,B\n"])
def test_files_that_are_not_databases(tmp_path: Path, text: str) -> None:
    with pytest.raises(ValueError):
        load_database(write(tmp_path, "x.csv", text))
