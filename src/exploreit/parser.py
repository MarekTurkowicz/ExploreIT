"""Link extraction from HTML pages."""

import re
from enum import StrEnum
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from exploreit.models import Link, LinkKind, Region
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


def extract_links(html: str | BeautifulSoup, page_url: str, mode: LinkMode) -> list[Link]:
    """Return unique, normalized http(s) links found on a page, in document order."""
    soup = html if isinstance(html, BeautifulSoup) else BeautifulSoup(html, "lxml")
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
        region = page_region(tag)
        known = links.get(url)
        # A URL linked both from the menu and from the text counts where it stands out most.
        if known is None or REGION_ORDER[region] < REGION_ORDER[known.region]:
            links[url] = Link(url=url, kind=kind, region=region)
    return list(links.values())


REGION_ORDER = {region: position for position, region in enumerate(Region)}
FOOTER_TAGS = frozenset({"footer"})
NAVIGATION_TAGS = frozenset({"nav", "header", "aside", "menu"})
FOOTER_ROLES = frozenset({"contentinfo"})
NAVIGATION_ROLES = frozenset({"navigation", "banner", "complementary", "menu", "menubar"})
FOOTER_NAME = re.compile(r"footer|copyright")
NAVIGATION_NAME = re.compile(r"\bnav|menu|header|sidebar|breadcrumb|topbar|navbar")


def page_region(tag: Tag) -> Region:
    """Where on the page a tag stands: in a footer, in navigation or in the content.

    Decided by the enclosing elements: HTML5 tags (<footer>, <nav>, <header>, <aside>),
    ARIA roles, and class or id names such as "footer", "menu" or "sidebar". A footer
    anywhere above the tag wins, since footers often hold a menu of their own.
    """
    region = Region.CONTENT
    for parent in tag.parents:
        if parent.name in ("body", "html", "[document]"):
            break
        role = str(parent.get("role", "")).lower()
        names = " ".join([*parent.get_attribute_list("class"), str(parent.get("id", ""))]).lower()
        if parent.name in FOOTER_TAGS or role in FOOTER_ROLES or FOOTER_NAME.search(names):
            return Region.FOOTER
        if (
            parent.name in NAVIGATION_TAGS
            or role in NAVIGATION_ROLES
            or NAVIGATION_NAME.search(names)
        ):
            region = Region.NAVIGATION
    return region


def _base_url(soup: BeautifulSoup, page_url: str) -> str:
    """Return the URL that relative links resolve against, honouring <base href>."""
    base = soup.find("base", href=True)
    if isinstance(base, Tag):
        href = base.get("href")
        if isinstance(href, str):
            return urljoin(page_url, href.strip())
    return page_url
