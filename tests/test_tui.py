import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
import respx
from textual.pilot import Pilot
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Select,
    SelectionList,
    TabbedContent,
    Tree,
)

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.models import CrawledPage, PageContent
from exploreit.parser import LinkMode
from exploreit.storage import ContentField
from exploreit.tui import ExploreApp
from exploreit.tui.compare import ComparePane
from exploreit.tui.experiments import ExperimentsPane
from exploreit.tui.results import PagesTable, ResultsPane
from exploreit.urls import Scope

SITE = "https://example.com"
Scenario = Callable[[ExploreApp, Pilot[None]], Awaitable[None]]


@pytest.fixture
def site(respx_mock: respx.MockRouter) -> respx.MockRouter:
    respx_mock.get(f"{SITE}/").respond(
        html='<meta name="keywords" content="home"><a href="/a">A</a> <a href="/b">B</a>'
    )
    respx_mock.get(f"{SITE}/a").respond(html='<a href="/a/1">1</a>')
    respx_mock.get(f"{SITE}/b").respond(html="<p>B</p>")
    respx_mock.get(f"{SITE}/a/1").respond(html="<p>1</p>")
    return respx_mock


def run_app(data_dir: Path, scenario: Scenario) -> None:
    async def main() -> None:
        app = ExploreApp(data_dir)
        async with app.run_test(size=(180, 60)) as pilot:
            await scenario(app, pilot)

    asyncio.run(main())


async def settle(app: ExploreApp, pilot: Pilot[None]) -> None:
    """Let a button press start its worker, wait for the worker, then let the UI update."""
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def fill_form(app: ExploreApp) -> None:
    app.query_one("#url", Input).value = SITE
    app.query_one("#delay", Input).value = "0"
    app.query_one("#robots", Checkbox).value = False


def save_crawl(path: Path, keywords: list[str]) -> None:
    page = CrawledPage(url=f"{SITE}/", depth=0, status_code=200, content_type="text/html")
    content = PageContent(url=page.url, title="Home", keywords=keywords)
    CrawlResult(
        config=CrawlConfig(start_url=SITE), pages=[page], edges=[], failed={}, contents=[content]
    ).save(path)


@pytest.mark.usefixtures("site")
def test_crawl_saves_outputs_and_shows_results(tmp_path: Path) -> None:
    async def scenario(app: ExploreApp, pilot: Pilot[None]) -> None:
        fill_form(app)
        app.query_one("#store-content", Checkbox).value = True
        fields = app.query_one("#fields", SelectionList)
        fields.deselect_all()
        fields.select(ContentField.URL)
        fields.select(ContentField.KEYWORDS)
        app.query_one("#separator", Select).value = ";"

        app.query_one("#start", Button).press()
        await settle(app, pilot)

        assert app.query_one(TabbedContent).active == "results"
        tree: Tree[None] = app.query_one(ResultsPane).query_one(Tree)
        assert [str(node.label) for node in tree.root.children] == ["/a", "/b"]
        assert app.query_one(PagesTable).row_count == 4
        assert not app.query_one("#open-graph", Button).disabled

    run_app(tmp_path, scenario)

    (csv_file,) = tmp_path.glob("crawl-*.csv")
    assert csv_file.read_text(encoding="utf-8-sig").splitlines()[:2] == [
        "url;keywords",
        f"{SITE}/;home",
    ]
    assert len(list(tmp_path.glob("crawl-*.html"))) == 1
    assert len(list(tmp_path.glob("crawl-*.sqlite"))) == 1


def test_invalid_settings_are_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    async def scenario(app: ExploreApp, pilot: Pilot[None]) -> None:
        monkeypatch.setattr(app, "notify", lambda message, **_: messages.append(message))
        app.query_one("#url", Input).value = "not a url"
        app.query_one("#start", Button).press()
        await settle(app, pilot)

        assert app.query_one(TabbedContent).active == "crawl"

    run_app(tmp_path, scenario)

    assert len(messages) == 1
    assert "start_url" in messages[0]


def test_open_saved_crawl_and_save_charts(tmp_path: Path) -> None:
    crawl_file = tmp_path / "old.json"
    save_crawl(crawl_file, ["a"])

    async def scenario(app: ExploreApp, pilot: Pilot[None]) -> None:
        results = app.query_one(ResultsPane)
        results.refresh_saved()
        results.query_one("#saved", Select).value = crawl_file
        results.query_one("#open-saved", Button).press()
        await pilot.pause()

        assert results.crawl_file == crawl_file
        results.query_one("#save-charts", Button).press()
        await pilot.pause()

    run_app(tmp_path, scenario)

    assert (tmp_path / "old-levels.png").exists()
    assert (tmp_path / "old-out-links.png").exists()


@pytest.mark.usefixtures("site")
def test_experiments_compare_chosen_combinations(tmp_path: Path) -> None:
    async def scenario(app: ExploreApp, pilot: Pilot[None]) -> None:
        fill_form(app)
        pane = app.query_one(ExperimentsPane)
        _, scopes, link_modes = pane.query(SelectionList)
        scopes.deselect(Scope.SUBTREE)
        scopes.deselect(Scope.WEB)
        link_modes.deselect(LinkMode.IMAGES)
        link_modes.deselect(LinkMode.ALL)

        pane.query_one("#run", Button).press()
        await settle(app, pilot)

        assert pane.query_one(DataTable).row_count == 2
        assert not pane.query_one("#open-chart", Button).disabled

    run_app(tmp_path, scenario)

    (out_dir,) = tmp_path.glob("experiments-*")
    assert sorted(path.name for path in out_dir.iterdir()) == [
        "bfs-server-hyperlinks.json",
        "comparison.png",
        "dfs-server-hyperlinks.json",
        "summary.csv",
    ]


def test_compare_two_saved_crawls(tmp_path: Path) -> None:
    save_crawl(tmp_path / "a.json", ["x", "y"])
    save_crawl(tmp_path / "b.json", [])

    async def scenario(app: ExploreApp, pilot: Pilot[None]) -> None:
        pane = app.query_one(ComparePane)
        pane.refresh_saved()
        pane.query_one("#first", Select).value = tmp_path / "a.json"
        pane.query_one("#second", Select).value = tmp_path / "b.json"
        pane.query_one("#compare", Button).press()
        await pilot.pause()

        table = pane.query_one(DataTable)
        rows = {row[0]: row[1:] for row in map(table.get_row_at, range(table.row_count))}
        assert rows["Distinct keywords"] == ["2", "0"]
        assert rows["Pages in both"] == ["1", "1"]

    run_app(tmp_path, scenario)
