from collections.abc import Iterator

import httpx
import pytest
import respx

from exploreit.fetcher import USER_AGENT, Fetcher, FetchError

SITE = "https://example.com"
PAGE = f"{SITE}/page"


@pytest.fixture
def fetcher() -> Iterator[Fetcher]:
    with Fetcher(delay=0, respect_robots=False) as fetcher:
        yield fetcher


def test_fetch_html_page(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    respx_mock.get(PAGE).respond(html="<p>Hello</p>")

    page = fetcher.fetch(PAGE)

    assert page.url == PAGE
    assert page.status_code == 200
    assert page.content_type == "text/html"
    assert page.html == "<p>Hello</p>"


def test_sends_user_agent(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    route = respx_mock.get(PAGE).respond(html="")

    fetcher.fetch(PAGE)

    assert route.calls.last.request.headers["User-Agent"] == USER_AGENT


def test_non_html_body_is_not_kept(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    respx_mock.get(f"{SITE}/logo.png").respond(content=b"\x89PNG", content_type="image/png")

    page = fetcher.fetch(f"{SITE}/logo.png")

    assert page.content_type == "image/png"
    assert page.html == ""


def test_error_page_body_is_not_kept(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    respx_mock.get(PAGE).respond(404, html="<h1>Not found</h1>")

    page = fetcher.fetch(PAGE)

    assert page.status_code == 404
    assert page.html == ""


def test_follows_redirects(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    respx_mock.get(PAGE).respond(301, headers={"Location": f"{SITE}/new"})
    respx_mock.get(f"{SITE}/new").respond(html="moved")

    page = fetcher.fetch(PAGE)

    assert page.url == f"{SITE}/new"
    assert page.html == "moved"


def test_network_error_raises_fetch_error(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    respx_mock.get(PAGE).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(FetchError, match="cannot fetch"):
        fetcher.fetch(PAGE)


def test_robots_txt_disallow(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{SITE}/robots.txt").respond(text="User-agent: *\nDisallow: /private/")
    respx_mock.get(PAGE).respond(html="ok")

    with Fetcher(delay=0) as fetcher:
        assert fetcher.fetch(PAGE).html == "ok"
        with pytest.raises(FetchError, match="disallowed"):
            fetcher.fetch(f"{SITE}/private/data")


def test_robots_txt_is_fetched_once_per_host(respx_mock: respx.MockRouter) -> None:
    robots = respx_mock.get(f"{SITE}/robots.txt").respond(text="")
    respx_mock.get(PAGE).respond(html="")

    with Fetcher(delay=0) as fetcher:
        fetcher.fetch(PAGE)
        fetcher.fetch(PAGE)

    assert robots.call_count == 1


@pytest.mark.parametrize(
    ("status", "allowed"),
    [(404, True), (500, True), (401, False), (403, False)],
)
def test_robots_txt_status(respx_mock: respx.MockRouter, status: int, allowed: bool) -> None:
    respx_mock.get(f"{SITE}/robots.txt").respond(status)

    with Fetcher(delay=0) as fetcher:
        assert fetcher.is_allowed(PAGE) is allowed


def test_unreachable_robots_txt_allows_everything(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{SITE}/robots.txt").mock(side_effect=httpx.ConnectTimeout("timeout"))

    with Fetcher(delay=0) as fetcher:
        assert fetcher.is_allowed(PAGE)


def test_waits_between_requests_to_the_same_host(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    respx_mock.get(url__startswith=SITE).respond(html="")
    sleeps: list[float] = []
    monkeypatch.setattr("exploreit.fetcher.time.sleep", sleeps.append)

    with Fetcher(delay=5, respect_robots=False) as fetcher:
        fetcher.fetch(f"{SITE}/a")
        fetcher.fetch(f"{SITE}/b")

    assert len(sleeps) == 1
    assert 4 < sleeps[0] <= 5


def test_charset_from_meta_tag_when_header_has_none(
    respx_mock: respx.MockRouter, fetcher: Fetcher
) -> None:
    html = '<meta charset="windows-1250"><p>Zażółć gęślą jaźń</p>'
    respx_mock.get(PAGE).respond(
        content=html.encode("cp1250"), headers={"Content-Type": "text/html"}
    )

    assert "Zażółć gęślą jaźń" in fetcher.fetch(PAGE).html


def test_invalid_url_raises_fetch_error(fetcher: Fetcher) -> None:
    with pytest.raises(FetchError, match="cannot fetch"):
        fetcher.fetch("https://exa mple.com/")
