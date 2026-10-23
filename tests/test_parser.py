import pytest

from exploreit.models import Link, LinkKind
from exploreit.parser import LinkMode, extract_links

PAGE_URL = "https://example.com/blog/post"

HTML = """
<html>
  <head>
    <link rel="stylesheet" href="/static/style.css">
    <script src="app.js"></script>
  </head>
  <body>
    <a href="/about">About</a>
    <a href="other-post#comments">Other post</a>
    <img src="../img/logo.png">
    <a href="mailto:john@example.com">Mail</a>
    <a href="javascript:void(0)">Menu</a>
    <a href="https://other.org/">Partner</a>
    <a>No href</a>
  </body>
</html>
"""


def urls(links: list[Link]) -> list[str]:
    return [link.url for link in links]


def test_hyperlinks_mode_returns_anchors_only() -> None:
    links = extract_links(HTML, PAGE_URL, LinkMode.HYPERLINKS)

    assert urls(links) == [
        "https://example.com/about",
        "https://example.com/blog/other-post",
        "https://other.org/",
    ]
    assert {link.kind for link in links} == {LinkKind.ANCHOR}


def test_images_mode_adds_images() -> None:
    links = extract_links(HTML, PAGE_URL, LinkMode.IMAGES)

    assert Link(url="https://example.com/img/logo.png", kind=LinkKind.IMAGE) in links
    assert len(links) == 4


def test_all_mode_adds_resources() -> None:
    links = extract_links(HTML, PAGE_URL, LinkMode.ALL)

    assert urls(links) == [
        "https://example.com/static/style.css",
        "https://example.com/blog/app.js",
        "https://example.com/about",
        "https://example.com/blog/other-post",
        "https://example.com/img/logo.png",
        "https://other.org/",
    ]


def test_duplicate_links_are_returned_once() -> None:
    html = '<a href="/a">1</a> <a href="/a#top">2</a> <a href="https://EXAMPLE.com/a">3</a>'

    assert urls(extract_links(html, PAGE_URL, LinkMode.HYPERLINKS)) == ["https://example.com/a"]


def test_base_tag_changes_how_relative_links_resolve() -> None:
    html = '<base href="https://cdn.example.com/v2/"><a href="page">Page</a>'

    assert urls(extract_links(html, PAGE_URL, LinkMode.HYPERLINKS)) == [
        "https://cdn.example.com/v2/page"
    ]


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<p>No links here</p>",
        '<a href="http://[::1">Broken</a><a href="http://example.com:abc/">Bad port</a>',
    ],
)
def test_pages_without_valid_links(html: str) -> None:
    assert extract_links(html, PAGE_URL, LinkMode.ALL) == []


def test_empty_href_points_to_the_page_itself() -> None:
    assert urls(extract_links('<a href="">Top</a>', PAGE_URL, LinkMode.ALL)) == [PAGE_URL]


def test_link_is_immutable() -> None:
    link = Link(url="https://example.com/", kind=LinkKind.ANCHOR)

    with pytest.raises(ValueError, match="frozen"):
        link.url = "https://other.org/"  # type: ignore[misc]
