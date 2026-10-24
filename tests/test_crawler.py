from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult, crawl
from exploreit.models import CrawledPage, Edge, LinkKind

SITE = "https://example.com"

#   /  ->  /a  ->  /a/1
#      ->  /b  ->  /b/1
#      ->  https://other.org/
PAGES = {
    "/": '<a href="/a">A</a> <a href="/b">B</a> <a href="https://other.org/">Out</a>',
    "/a": '<a href="/a/1">1</a> <a href="/">Home</a> <img src="/logo.png">',
    "/b": '<a href="/b/1">1</a>',
    "/a/1": "<p>Leaf</p>",
    "/b/1": "<p>Leaf</p>",
}


@pytest.fixture
def site() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        for path, html in PAGES.items():
            router.get(SITE + path).respond(html=html)
        router.get(f"{SITE}/logo.png").respond(content=b"", content_type="image/png")
        router.get("https://other.org/").respond(html="<p>Other</p>")
        yield router


def run(**options: Any) -> CrawlResult:
    config = CrawlConfig(start_url=SITE, delay=0, respect_robots=False, **options)
    return crawl(config)


def visited(result: CrawlResult) -> list[tuple[str, int]]:
    return [(page.url.removeprefix(SITE), page.depth) for page in result.pages]


@pytest.mark.usefixtures("site")
def test_bfs_visits_pages_level_by_level() -> None:
    assert visited(run(strategy="bfs")) == [
        ("/", 0),
        ("/a", 1),
        ("/b", 1),
        ("/a/1", 2),
        ("/b/1", 2),
    ]


@pytest.mark.usefixtures("site")
def test_dfs_goes_deep_first() -> None:
    assert visited(run(strategy="dfs")) == [
        ("/", 0),
        ("/b", 1),
        ("/b/1", 2),
        ("/a", 1),
        ("/a/1", 2),
    ]


@pytest.mark.usefixtures("site")
def test_max_depth_limits_levels() -> None:
    assert visited(run(max_depth=1)) == [("/", 0), ("/a", 1), ("/b", 1)]


@pytest.mark.usefixtures("site")
def test_max_pages_limits_visited_pages() -> None:
    assert len(run(max_pages=2).pages) == 2


@pytest.mark.usefixtures("site")
def test_edges_include_back_and_external_links() -> None:
    edges = run().edges

    assert Edge(source=f"{SITE}/a", target=f"{SITE}/", kind=LinkKind.ANCHOR) in edges
    assert Edge(source=f"{SITE}/", target="https://other.org/", kind=LinkKind.ANCHOR) in edges
    assert len(edges) == 6


@pytest.mark.usefixtures("site")
def test_web_scope_visits_external_pages() -> None:
    urls = [page.url for page in run(scope="web").pages]

    assert "https://other.org/" in urls


@pytest.mark.usefixtures("site")
def test_images_mode_visits_images() -> None:
    result = run(link_mode="images")

    logo = next(page for page in result.pages if page.url.endswith("/logo.png"))
    assert logo.content_type == "image/png"
    assert Edge(source=f"{SITE}/a", target=logo.url, kind=LinkKind.IMAGE) in result.edges


def test_failed_pages_are_recorded(site: respx.MockRouter) -> None:
    site.get(f"{SITE}/b").mock(side_effect=httpx.ConnectError("refused"))

    result = run()

    assert f"{SITE}/b" in result.failed
    assert f"{SITE}/b" not in [page.url for page in result.pages]


@pytest.mark.usefixtures("site")
def test_on_page_is_called_for_every_visited_page() -> None:
    seen: list[CrawledPage] = []
    config = CrawlConfig(start_url=SITE, delay=0, respect_robots=False)

    result = crawl(config, on_page=seen.append)

    assert seen == result.pages


@pytest.mark.usefixtures("site")
def test_result_survives_json_round_trip(tmp_path: Path) -> None:
    result = run()
    path = tmp_path / "crawl.json"

    result.save(path)

    assert CrawlResult.load(path) == result


@pytest.mark.usefixtures("site")
def test_content_is_stored_only_when_asked() -> None:
    assert run().contents == []

    contents = run(store_content=True).contents

    assert [content.url for content in contents] == [page.url for page in run().pages]
    assert contents[3].body == "Leaf"


def test_redirected_start_page_becomes_the_start() -> None:
    with respx.mock() as router:
        router.get("http://example.com/").respond(
            301, headers={"Location": "https://www.example.com/"}
        )
        router.get("https://www.example.com/").respond(
            html='<a href="/a">A</a> <a href="#top">Top</a> <a href="https://www.example.com/">Home</a>'
        )
        router.get("https://www.example.com/a").respond(html="<p>A</p>")

        result = crawl(CrawlConfig(start_url="http://example.com", delay=0, respect_robots=False))

    assert result.config.start_url == "https://www.example.com/"
    assert [page.url for page in result.pages] == [
        "https://www.example.com/",
        "https://www.example.com/a",
    ]
    assert [edge.target for edge in result.edges] == ["https://www.example.com/a"]


@pytest.mark.usefixtures("site")
def test_crawl_can_be_stopped() -> None:
    visited: list[CrawledPage] = []
    config = CrawlConfig(start_url=SITE, delay=0, respect_robots=False)

    result = crawl(config, on_page=visited.append, should_stop=lambda: len(visited) >= 2)

    assert result.stopped
    assert len(result.pages) == 2
    assert not run().stopped
