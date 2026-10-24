"""Polite HTTP fetching: robots.txt, a delay between requests and HTML-only bodies."""

import math
import time
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import UnicodeDammit

from exploreit import __version__
from exploreit.models import HTML_TYPES, Page
from exploreit.urls import normalize_url

USER_AGENT = f"ExploreIT/{__version__}"
ALLOW_ALL: list[str] = []
DISALLOW_ALL = ["User-agent: *", "Disallow: /"]


class FetchError(Exception):
    """Raised when a page cannot be fetched or robots.txt forbids it."""


class Fetcher:
    """Downloads pages over HTTP, one host at a time, honouring robots.txt."""

    def __init__(
        self,
        *,
        delay: float = 1.0,
        timeout: float = 10.0,
        respect_robots: bool = True,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.delay = delay
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        self._client = httpx.Client(
            headers={"User-Agent": user_agent}, timeout=timeout, follow_redirects=True
        )
        self._robots: dict[str, RobotFileParser] = {}
        self._last_request: dict[str, float] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def fetch(self, url: str) -> Page:
        """Download a page. The body is read only for successful HTML responses.

        Raises:
            FetchError: If robots.txt disallows the URL or the request fails.
        """
        if self.respect_robots and not self.is_allowed(url):
            raise FetchError(f"disallowed by robots.txt: {url}")

        self._wait(url)
        try:
            with self._client.stream("GET", url) as response:
                content_type = _media_type(response.headers.get("content-type", ""))
                html = ""
                if response.is_success and content_type in HTML_TYPES:
                    response.read()
                    html = _decode(response)
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise FetchError(f"cannot fetch {url}: {error}") from error

        return Page(
            url=normalize_url(str(response.url)),
            status_code=response.status_code,
            content_type=content_type,
            html=html,
        )

    def is_allowed(self, url: str) -> bool:
        """Return True if robots.txt of the URL's host lets us fetch it."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        return self._robots[origin].can_fetch(self.user_agent, url)

    def _load_robots(self, origin: str) -> RobotFileParser:
        """Fetch and parse robots.txt, following the standard library's rules.

        A missing or unreachable file allows everything; 401 and 403 forbid everything.
        """
        self._wait(origin)
        try:
            response = self._client.get(f"{origin}/robots.txt")
        except (httpx.HTTPError, httpx.InvalidURL):
            rules = ALLOW_ALL
        else:
            if response.status_code in (401, 403):
                rules = DISALLOW_ALL
            elif response.is_success:
                rules = response.text.splitlines()
            else:
                rules = ALLOW_ALL

        robots = RobotFileParser()
        robots.parse(rules)
        return robots

    def _wait(self, url: str) -> None:
        """Sleep so that requests to the same host are at least `delay` seconds apart."""
        host = urlsplit(url).netloc
        elapsed = time.monotonic() - self._last_request.get(host, -math.inf)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request[host] = time.monotonic()


def _decode(response: httpx.Response) -> str:
    """Decode an HTML body using the charset from the header, else from <meta charset>."""
    if response.charset_encoding:
        return response.text
    return UnicodeDammit(response.content, is_html=True).unicode_markup or ""


def _media_type(content_type: str) -> str:
    """Return the media type of a Content-Type header, e.g. "text/html; charset=utf-8"."""
    return content_type.split(";")[0].strip().lower()
