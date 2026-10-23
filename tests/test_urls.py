import pytest

from exploreit.urls import Scope, is_crawlable, is_in_scope, normalize_url


def test_scope_from_string() -> None:
    assert Scope("server") is Scope.SERVER


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com", True),
        ("HTTP://EXAMPLE.COM/page", True),
        ("mailto:john@example.com", False),
        ("javascript:void(0)", False),
        ("tel:+48123456789", False),
        ("ftp://example.com/file.txt", False),
        ("/relative/path", False),
        ("https://", False),
    ],
)
def test_is_crawlable(url: str, expected: bool) -> None:
    assert is_crawlable(url) is expected


@pytest.mark.parametrize(
    ("url", "base", "expected"),
    [
        ("HTTPS://Example.COM:443/#top", "", "https://example.com/"),
        ("https://example.com", "", "https://example.com/"),
        ("/contact", "https://example.com/blog/post", "https://example.com/contact"),
        ("../about.html", "https://example.com/blog/post", "https://example.com/about.html"),
        ("other-post", "https://example.com/blog/post", "https://example.com/blog/other-post"),
        ("http://example.com:80/a", "", "http://example.com/a"),
        ("http://example.com:8080/a", "", "http://example.com:8080/a"),
        ("https://example.com/a?id=5#x", "", "https://example.com/a?id=5"),
        ("https://other.org/", "https://example.com/", "https://other.org/"),
    ],
)
def test_normalize_url(url: str, base: str, expected: str) -> None:
    assert normalize_url(url, base) == expected


def test_normalize_url_is_idempotent() -> None:
    url = normalize_url("HTTPS://Example.com:443/blog#x")
    assert normalize_url(url) == url


@pytest.mark.parametrize("url", ["mailto:john@example.com", "javascript:void(0)", "https://"])
def test_normalize_url_rejects_non_http(url: str) -> None:
    with pytest.raises(ValueError, match="not an http"):
        normalize_url(url)


START = "https://example.com/docs/guide/"


@pytest.mark.parametrize(
    ("url", "subtree", "server", "web"),
    [
        ("https://example.com/docs/guide/", True, True, True),
        ("https://example.com/docs/guide/install", True, True, True),
        ("https://example.com/docs/guide/api/client", True, True, True),
        ("https://example.com/docs/guide-old/", False, True, True),
        ("https://example.com/docs/", False, True, True),
        ("https://example.com/pricing", False, True, True),
        ("https://blog.example.com/", False, False, True),
        ("https://other.org/", False, False, True),
    ],
)
def test_is_in_scope(url: str, subtree: bool, server: bool, web: bool) -> None:
    assert is_in_scope(url, START, Scope.SUBTREE) is subtree
    assert is_in_scope(url, START, Scope.SERVER) is server
    assert is_in_scope(url, START, Scope.WEB) is web


def test_subtree_of_file_url_uses_its_directory() -> None:
    start = "https://example.com/blog/index.html"
    assert is_in_scope("https://example.com/blog/post", start, Scope.SUBTREE)
    assert not is_in_scope("https://example.com/shop/", start, Scope.SUBTREE)


def test_other_port_is_other_server() -> None:
    assert not is_in_scope("https://example.com:8443/", "https://example.com/", Scope.SERVER)
