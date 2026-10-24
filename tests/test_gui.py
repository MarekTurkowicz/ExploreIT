import time
import tkinter as tk
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.gui import ExploreApp
from exploreit.gui.widgets import Table
from exploreit.models import CrawledPage, Edge, LinkKind, PageContent
from exploreit.storage import ContentField

SITE = "https://example.com"


@pytest.fixture
def root() -> Iterator[tk.Tk]:
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def app(root: tk.Tk, tmp_path: Path) -> ExploreApp:
    return ExploreApp(root, tmp_path)


@pytest.fixture
def errors(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    shown: list[str] = []
    for module in ("crawl_tab", "experiments_tab", "compare_tab", "results_tab", "widgets"):
        monkeypatch.setattr(
            f"exploreit.gui.{module}.messagebox.showerror",
            lambda title, message: shown.append(f"{title}: {message}"),
        )
    return shown


@pytest.fixture
def site(respx_mock: respx.MockRouter) -> respx.MockRouter:
    respx_mock.get(f"{SITE}/").respond(
        html='<meta name="keywords" content="home"><a href="/a">A</a> <a href="/b">B</a>'
    )
    respx_mock.get(f"{SITE}/a").respond(html='<a href="/a/1">1</a>')
    respx_mock.get(f"{SITE}/b").respond(html="<p>B</p>")
    respx_mock.get(f"{SITE}/a/1").respond(html="<p>1</p>")
    return respx_mock


def settle(app: ExploreApp, timeout: float = 120) -> None:
    """Process window events until background work and its follow-up calls are done."""
    deadline = time.monotonic() + timeout
    app.root.update()
    while app.tasks.busy:
        assert time.monotonic() < deadline, "background work did not finish"
        app.root.update()
        time.sleep(0.01)
    app.root.update()


def fill_form(app: ExploreApp) -> None:
    app.crawl_tab.url.set(SITE)
    app.crawl_tab.delay.set("0")
    app.crawl_tab.respect_robots.set(False)


def save_crawl(path: Path, keywords: list[str]) -> None:
    pages = [
        CrawledPage(url=f"{SITE}/", depth=0, status_code=200, content_type="text/html"),
        CrawledPage(url=f"{SITE}/a", depth=1, status_code=200, content_type="text/html"),
    ]
    CrawlResult(
        config=CrawlConfig(start_url=SITE),
        pages=pages,
        edges=[Edge(source=f"{SITE}/", target=f"{SITE}/a", kind=LinkKind.ANCHOR)],
        failed={},
        contents=[PageContent(url=f"{SITE}/", title="Home", keywords=keywords)],
    ).save(path)


@pytest.mark.usefixtures("site")
def test_crawl_fills_every_tab_and_saves_outputs(app: ExploreApp, tmp_path: Path) -> None:
    fill_form(app)
    app.crawl_tab.store_content.set(True)
    for field, ticked in app.crawl_tab.fields.items():
        ticked.set(field in (ContentField.URL, ContentField.KEYWORDS))
    app.crawl_tab.separator.set("semicolon ( ; )")

    app.crawl_tab.start()
    settle(app)

    assert app.notebook.select() == str(app.results_tab)
    assert len(app.pages_tab.table.rows()) == 4
    assert len(app.content_tab.table.rows()) == 4
    assert app.graph_tab.drawing.urls[0] == f"{SITE}/"
    (csv_file,) = tmp_path.glob("crawl-*.csv")
    assert csv_file.read_text(encoding="utf-8-sig").splitlines()[:2] == [
        "url;keywords",
        f"{SITE}/;home",
    ]
    assert len(list(tmp_path.glob("crawl-*.sqlite"))) == 1


def test_invalid_settings_are_reported(app: ExploreApp, errors: list[str]) -> None:
    app.crawl_tab.url.set("not a url")

    app.crawl_tab.start()
    settle(app)

    assert len(errors) == 1
    assert "start_url" in errors[0]


def test_open_saved_crawl_and_export(app: ExploreApp, tmp_path: Path) -> None:
    crawl_file = tmp_path / "old.json"
    save_crawl(crawl_file, ["a"])

    app.results_tab.open_file(crawl_file)
    settle(app)
    app.results_tab.save_charts()
    app.results_tab.export_gexf()

    assert dict(app.results_tab.stats.rows())["Graph depth"] == "1"
    assert (tmp_path / "old-levels.png").exists()
    assert (tmp_path / "old-out-links.png").exists()
    assert (tmp_path / "old.gexf").exists()


def test_graph_hover_finds_the_nearest_page(app: ExploreApp, tmp_path: Path) -> None:
    crawl_file = tmp_path / "old.json"
    save_crawl(crawl_file, [])
    app.results_tab.open_file(crawl_file)
    settle(app)

    drawing = app.graph_tab.drawing
    x, y = drawing.axes.transData.transform(drawing.positions[1])

    assert app.graph_tab.url_at(x + 2, y - 2) == f"{SITE}/a"
    assert app.graph_tab.url_at(x + 500, y + 500) == ""


@pytest.mark.usefixtures("site")
def test_experiments_compare_chosen_combinations(app: ExploreApp, tmp_path: Path) -> None:
    fill_form(app)
    tab = app.experiments_tab
    for scope, ticked in tab.scopes.items():
        ticked.set(scope == "server")
    for mode, ticked in tab.link_modes.items():
        ticked.set(mode == "hyperlinks")

    tab.run()
    settle(app)

    assert len(tab.table.rows()) == 2
    (out_dir,) = tmp_path.glob("experiments-*")
    assert sorted(path.name for path in out_dir.iterdir()) == [
        "bfs-server-hyperlinks.json",
        "comparison.png",
        "dfs-server-hyperlinks.json",
        "summary.csv",
    ]


def test_experiments_need_a_value_in_every_group(app: ExploreApp, errors: list[str]) -> None:
    fill_form(app)
    for ticked in app.experiments_tab.strategies.values():
        ticked.set(False)

    app.experiments_tab.run()

    assert errors == ["Experiments: Tick at least one value in every group."]


def test_compare_two_saved_crawls(app: ExploreApp, tmp_path: Path) -> None:
    save_crawl(tmp_path / "a.json", ["x", "y"])
    save_crawl(tmp_path / "b.json", [])
    tab = app.compare_tab
    tab.refresh()

    tab.first.set("a.json")
    tab.second.set(str(tmp_path / "b.json"))
    tab.compare()

    rows = {row[0]: row[1:] for row in tab.table.rows()}
    assert rows["Distinct keywords"] == ("2", "0")
    assert sorted(tab.pickers[0]["values"]) == ["a.json", "b.json"]


def test_table_sorts_numbers_numerically(root: tk.Tk) -> None:
    table = Table(root)
    table.set_rows(["Name", "Links"], [("a", 10), ("b", 9), ("c", 100)])

    table._sort("Links")
    assert [row[1] for row in table.rows()] == ["9", "10", "100"]
    table._sort("Links")
    assert [row[1] for row in table.rows()] == ["100", "10", "9"]
