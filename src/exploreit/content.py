"""Content extraction: title, meta description, meta keywords and visible body text."""

from bs4 import BeautifulSoup

from exploreit.models import PageContent

INVISIBLE_TAGS = ["script", "style", "noscript", "template", "svg"]
META_NAME_ATTRIBUTES = ("name", "property", "itemprop")


def extract_content(html: str, url: str) -> PageContent:
    """Return the text content of a page with whitespace collapsed.

    Meta tags are read from `name`, `property` (Open Graph) and `itemprop` (microdata)
    attributes; keywords from all matching tags are merged.
    """
    soup = BeautifulSoup(html, "lxml")
    title = _clean(soup.title.get_text(" ")) if soup.title else ""
    descriptions = _meta(soup, "description", "og:description")
    keywords = [
        keyword.strip() for value in _meta(soup, "keywords") for keyword in value.split(",")
    ]

    for tag in soup(INVISIBLE_TAGS):
        tag.decompose()
    body = _clean((soup.body or soup).get_text(" "))

    return PageContent(
        url=url,
        title=title,
        description=descriptions[0] if descriptions else "",
        keywords=list(dict.fromkeys(keyword for keyword in keywords if keyword)),
        body=body,
    )


def _meta(soup: BeautifulSoup, *names: str) -> list[str]:
    """Return the non-empty contents of meta tags with any of the names, in document order."""
    wanted = {name.lower() for name in names}
    values = []
    for tag in soup.find_all("meta", content=True):
        keys = {str(tag.get(attribute, "")).lower() for attribute in META_NAME_ATTRIBUTES}
        content = tag.get("content")
        if keys & wanted and isinstance(content, str) and content.strip():
            values.append(_clean(content))
    return values


def _clean(text: str) -> str:
    return " ".join(text.split())
