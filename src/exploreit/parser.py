"""Link extraction from HTML pages."""

from enum import StrEnum
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from exploreit.models import Link, LinkKind
from exploreit.urls import normalize_url


class LinkMode(StrEnum):
    """Which kinds of links the crawler follows."""

    HYPERLINKS = "hyperlinks"
    IMAGES = "images"
    ALL = "all"


# Element name -> (attribute holding the URL, kind of link).
LINK_ATTRIBUTES: dict[str, tuple[str, LinkKind]] = {
    "a": ("href", LinkKind.ANCHOR),
    "area": ("href", LinkKind.ANCHOR),
    "img": ("src", LinkKind.IMAGE),
    "link": ("href", LinkKind.RESOURCE),
    "script": ("src", LinkKind.RESOURCE),
    "iframe": ("src", LinkKind.RESOURCE),
    "frame": ("src", LinkKind.RESOURCE),
    "embed": ("src", LinkKind.RESOURCE),
    "source": ("src", LinkKind.RESOURCE),
}

KINDS_BY_MODE: dict[LinkMode, frozenset[LinkKind]] = {
    LinkMode.HYPERLINKS: frozenset({LinkKind.ANCHOR}),
    LinkMode.IMAGES: frozenset({LinkKind.ANCHOR, LinkKind.IMAGE}),
    LinkMode.ALL: frozenset(LinkKind),
}


def extract_links(html: str, page_url: str, mode: LinkMode) -> list[Link]:
    """Return unique, normalized http(s) links found on a page, in document order."""
    soup = BeautifulSoup(html, "lxml")
    base_url = _base_url(soup, page_url)
    kinds = KINDS_BY_MODE[mode]
    names = [name for name, (_, kind) in LINK_ATTRIBUTES.items() if kind in kinds]

    links: dict[str, Link] = {}
    for tag in soup.find_all(names):
        attribute, kind = LINK_ATTRIBUTES[tag.name]
        value = tag.get(attribute)
        if not isinstance(value, str):
            continue
        try:
            url = normalize_url(value.strip(), base_url)
        except ValueError:
            continue
        links.setdefault(url, Link(url=url, kind=kind))
    return list(links.values())


def _base_url(soup: BeautifulSoup, page_url: str) -> str:
    """Return the URL that relative links resolve against, honouring <base href>."""
    base = soup.find("base", href=True)
    if isinstance(base, Tag):
        href = base.get("href")
        if isinstance(href, str):
            return urljoin(page_url, href.strip())
    return page_url
