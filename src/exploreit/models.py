"""Data models shared across the crawler."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})


class LinkKind(StrEnum):
    """The kind of HTML element a link was found in."""

    ANCHOR = "anchor"
    IMAGE = "image"
    RESOURCE = "resource"


class Link(BaseModel):
    """A normalized link found on a page."""

    model_config = ConfigDict(frozen=True)

    url: str
    kind: LinkKind


class Page(BaseModel):
    """A fetched page. The HTML is kept only for successful HTML responses."""

    model_config = ConfigDict(frozen=True)

    url: str
    status_code: int
    content_type: str
    html: str = ""
    blocked_by: str = ""  # anti-bot service that refused the request, e.g. "DataDome"


class CrawledPage(BaseModel):
    """A page visited during a crawl: a node of the link graph."""

    model_config = ConfigDict(frozen=True)

    url: str
    depth: int
    status_code: int
    content_type: str
    blocked_by: str = ""

    @property
    def is_html(self) -> bool:
        """True for a successful HTML response, the only kind whose links are followed."""
        return self.content_type in HTML_TYPES and 200 <= self.status_code < 300


class Edge(BaseModel):
    """A link from one page to another: an edge of the link graph."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    kind: LinkKind


class PageContent(BaseModel):
    """Text content of a page: its title, meta tags and visible body text."""

    model_config = ConfigDict(frozen=True)

    url: str
    title: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    body: str = ""
