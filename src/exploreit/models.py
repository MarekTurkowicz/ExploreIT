"""Data models shared across the crawler."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


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
