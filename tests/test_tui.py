import asyncio
from pathlib import Path

import pytest
import respx
from textual.widgets import Button, Checkbox, DataTable, Input, TabbedContent, Tree

from exploreit.tui import ExploreApp

SITE = "https://example.com"


@pytest.fixture
def site(respx_mock: respx.MockRouter) -> respx.MockRouter:
    respx_mock.get(f"{SITE}/").respond(html='<a href="/a">A</a> <a href="/b">B</a>')
    respx_mock.get(f"{SITE}/a").respond(html='<a href="/a/1">1</a>')
    respx_mock.get(f"{SITE}/b").respond(html="<p>B</p>")
    respx_mock.get(f"{SITE}/a/1").respond(html="<p>1</p>")
    return respx_mock


@pytest.mark.usefixtures("site")
def test_crawl_from_form_shows_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("exploreit.tui.DATA_DIR", tmp_path)

    async def scenario() -> None:
        app = ExploreApp()
        async with app.run_test(size=(160, 50)) as pilot:
            app.query_one("#url", Input).value = SITE
            app.query_one("#delay", Input).value = "0"
            app.query_one("#robots", Checkbox).value = False

            await pilot.click("#start")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert app.query_one(TabbedContent).active == "results"
            tree: Tree[None] = app.query_one("#tree", Tree)
            assert [str(node.label) for node in tree.root.children] == ["/a", "/b"]
            assert app.query_one("#pages-table", DataTable).row_count == 4
            assert not app.query_one("#start", Button).disabled
            assert not app.query_one("#open-graph", Button).disabled

    asyncio.run(scenario())

    assert len(list(tmp_path.glob("crawl-*.json"))) == 1
    assert len(list(tmp_path.glob("crawl-*.html"))) == 1


def test_invalid_settings_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    async def scenario() -> None:
        app = ExploreApp()
        monkeypatch.setattr(app, "notify", lambda message, **_: messages.append(message))
        async with app.run_test(size=(160, 50)) as pilot:
            app.query_one("#url", Input).value = "not a url"
            await pilot.click("#start")
            await pilot.pause()

            assert app.query_one(TabbedContent).active == "crawl"

    asyncio.run(scenario())

    assert len(messages) == 1
    assert "start_url" in messages[0]
