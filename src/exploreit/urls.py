"""URL normalization and crawl scope checks."""

from enum import StrEnum
from urllib.parse import urljoin, urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


class Scope(StrEnum):
    """How far the crawler may go from the start URL."""

    SUBTREE = "subtree"
    SERVER = "server"
    WEB = "web"


def is_crawlable(url: str) -> bool:
    """Return True if the URL is a valid absolute http(s) URL with a host."""
    try:
        normalize_url(url)
    except ValueError:
        return False
    return True


def normalize_url(url: str, base: str = "") -> str:
    """Resolve a URL against a base and return it in canonical form.

    The scheme and host are lowercased, the default port and the fragment
    are dropped, and an empty path becomes "/".

    Raises:
        ValueError: If the resolved URL is not an http(s) URL with a host.
    """
    parts = urlsplit(urljoin(base, url))
    scheme = parts.scheme.lower()
    host = parts.hostname
    if scheme not in DEFAULT_PORTS or not host:
        raise ValueError(f"not an http(s) URL: {url!r}")

    port = parts.port
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def is_in_scope(url: str, start_url: str, scope: Scope) -> bool:
    """Return True if a normalized URL falls within the scope of the start URL."""
    if scope is Scope.WEB:
        return True

    target = urlsplit(url)
    start = urlsplit(start_url)
    if target.netloc != start.netloc:
        return False
    if scope is Scope.SERVER:
        return True
    return target.path.startswith(_parent_dir(start.path))


def _parent_dir(path: str) -> str:
    """Return the directory part of a URL path, e.g. "/blog/a.html" -> "/blog/"."""
    return path[: path.rfind("/") + 1]
