from exploreit.compare import summarize, url_overlap
from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.models import PageContent

START = "https://example.com/"


def database(*contents: PageContent) -> CrawlResult:
    return CrawlResult(
        config=CrawlConfig(start_url=START), pages=[], edges=[], failed={}, contents=list(contents)
    )


FIRST = database(
    PageContent(url=START, title="Home", keywords=["Python", "web"], body="one two three"),
    PageContent(url="https://other.org/", description="Other", keywords=["python"], body="four"),
)
SECOND = database(PageContent(url=START), PageContent(url=f"{START}new"))


def test_summary_of_a_database() -> None:
    summary = summarize(FIRST)

    assert summary.pages == 2
    assert summary.hosts == 2
    assert summary.external_pages == 1
    assert (summary.with_title, summary.with_description, summary.with_keywords) == (1, 1, 2)
    assert summary.mean_body_words == 2
    assert summary.top_keywords[0] == ("python", 2)
    assert len(summary.rows()) == 9


def test_summary_of_an_empty_database() -> None:
    summary = summarize(database())

    assert summary.pages == 0
    assert summary.mean_body_words == 0
    assert dict(summary.rows())["Most common keywords"] == "-"


def test_url_overlap() -> None:
    overlap = url_overlap(FIRST, SECOND)

    assert (overlap.common, overlap.only_first, overlap.only_second) == (1, 1, 1)
