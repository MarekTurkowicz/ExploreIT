"""Comparison of two content databases built from crawls."""

from collections import Counter
from statistics import fmean
from urllib.parse import urlsplit

from pydantic import BaseModel

from exploreit.crawler import CrawlResult


class ContentSummary(BaseModel):
    """What a content database holds and how complete it is."""

    pages: int
    hosts: int
    external_pages: int
    with_title: int
    with_description: int
    with_keywords: int
    mean_body_words: float
    unique_keywords: int
    top_keywords: list[tuple[str, int]]

    def rows(self) -> list[tuple[str, str]]:
        """Return the summary as human-readable (label, value) rows."""
        keywords = ", ".join(f"{word} ({count})" for word, count in self.top_keywords)
        return [
            ("Pages with content", str(self.pages)),
            ("Hosts", str(self.hosts)),
            ("Pages on other hosts", str(self.external_pages)),
            ("With title", str(self.with_title)),
            ("With meta description", str(self.with_description)),
            ("With meta keywords", str(self.with_keywords)),
            ("Mean body length (words)", f"{self.mean_body_words:.0f}"),
            ("Distinct keywords", str(self.unique_keywords)),
            ("Most common keywords", keywords or "-"),
        ]


class Overlap(BaseModel):
    """How many pages two databases share."""

    common: int
    only_first: int
    only_second: int


def summarize(result: CrawlResult, top: int = 5) -> ContentSummary:
    """Describe the content stored by a crawl."""
    contents = result.contents
    start_host = urlsplit(result.config.start_url).netloc
    hosts = [urlsplit(content.url).netloc for content in contents]
    keywords = Counter(keyword.lower() for content in contents for keyword in content.keywords)
    body_words = [len(content.body.split()) for content in contents]

    return ContentSummary(
        pages=len(contents),
        hosts=len(set(hosts)),
        external_pages=sum(host != start_host for host in hosts),
        with_title=sum(bool(content.title) for content in contents),
        with_description=sum(bool(content.description) for content in contents),
        with_keywords=sum(bool(content.keywords) for content in contents),
        mean_body_words=fmean(body_words) if body_words else 0.0,
        unique_keywords=len(keywords),
        top_keywords=keywords.most_common(top),
    )


def url_overlap(first: CrawlResult, second: CrawlResult) -> Overlap:
    """Count pages stored in both databases and in only one of them."""
    first_urls = {content.url for content in first.contents}
    second_urls = {content.url for content in second.contents}
    return Overlap(
        common=len(first_urls & second_urls),
        only_first=len(first_urls - second_urls),
        only_second=len(second_urls - first_urls),
    )
