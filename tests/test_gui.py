import time
import tkinter as tk
from collections.abc import Iterator
from pathlib import Path
from tkinter import ttk

import pytest

pytest.importorskip("tkinter", reason="this Python has no Tk")
import respx

from exploreit.config import CrawlConfig
from exploreit.crawler import CrawlResult
from exploreit.gui.app import DARK_THEME, ExploreApp, create_window
from exploreit.gui.widgets import Table
from exploreit.models import CrawledPage, Edge, LinkKind, PageContent
from exploreit.storage import ContentField

SITE = "https://example.com"


@pytest.fixture
def app(tmp_path: Path) -> Iterator[ExploreApp]:
    try:
        root, app = create_window(tmp_path)
    except tk.TclError:
        pytest.skip("no display available")
    root.withdraw()
    yield app
    root.destroy()


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
    assert len(app.graph_tab.canvas.data.nodes) == 4
    assert app.crawl_tab.timer.get().startswith("✔")
    assert str(app.crawl_tab.start_button["state"]) != "disabled"
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


def test_graph_hover_drag_and_zoom(app: ExploreApp, tmp_path: Path) -> None:
    crawl_file = tmp_path / "old.json"
    save_crawl(crawl_file, [])
    app.results_tab.open_file(crawl_file)
    settle(app)
    app.notebook.select(app.graph_tab)
    settle(app)
    canvas = app.graph_tab.canvas
    page = f"{SITE}/a"
    x, y = canvas.screen(page)

    assert canvas.node_at(x, y) == page
    canvas._set_hovered(page)
    assert canvas.find_withtag("tip")
    assert app.graph_tab.details.cget("text").startswith(page)

    canvas.move_node(page, 40, -10)
    assert canvas.screen(page) == pytest.approx((x + 40, y - 10))

    canvas.zoom_at(2.0, x + 40, y - 10)
    assert canvas.screen(page) == pytest.approx((x + 40, y - 10))
    canvas.fit()
    assert canvas.zoom == 1.0

    app.graph_tab.save_png()
    assert (tmp_path / "old-graph.png").exists()


def test_graph_styles_and_legend(app: ExploreApp, tmp_path: Path) -> None:
    crawl_file = tmp_path / "old.json"
    save_crawl(crawl_file, [])
    app.results_tab.open_file(crawl_file)
    settle(app)

    app.graph_tab.colour_by.set("host")
    app.graph_tab.restyle()
    app.graph_tab.unvisited.set(True)
    app.graph_tab.reload()
    settle(app)

    legend_rows = app.graph_tab.legend.winfo_children()
    assert len(legend_rows) == 1  # every page is on example.com
    assert app.graph_tab.summary.cget("text") == "2 pages · 1 link"


@pytest.mark.usefixtures("site")
def test_settings_are_locked_while_crawling(app: ExploreApp) -> None:
    fill_form(app)

    app.crawl_tab.start()

    assert app.crawl_tab.running
    assert all(widget.instate(["disabled"]) for widget in app.crawl_tab.inputs)
    assert app.experiments_tab.run_button.instate(["disabled"])
    settle(app)
    assert not any(widget.instate(["disabled"]) for widget in app.crawl_tab.inputs)


def test_theme_and_font_size(app: ExploreApp) -> None:
    app.dark.set(True)
    app.set_theme(DARK_THEME)
    app.set_font_size(40)

    assert app.font_size.get() == 30  # clamped to the largest size
    assert app.root.style.theme_use() == DARK_THEME
    colours = app.theme_colours()
    assert app.root.style.lookup("TSpinbox", "fieldbackground") == colours.inputbg
    combobox = next(w for w in app.crawl_tab.inputs if isinstance(w, ttk.Combobox))
    popdown = combobox.tk.eval(f"ttk::combobox::PopdownWindow {combobox}")
    assert combobox.tk.call(f"{popdown}.f.l", "cget", "-background") == colours.inputbg


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


def test_table_sorts_numbers_numerically(app: ExploreApp) -> None:
    table = Table(app.root)
    table.set_rows(["Name", "Links"], [("a", 10), ("b", 9), ("c", 100)])

    table._sort("Links")
    assert [row[1] for row in table.rows()] == ["9", "10", "100"]
    table._sort("Links")
    assert [row[1] for row in table.rows()] == ["100", "10", "9"]


@pytest.mark.usefixtures("site")
def test_stop_button_ends_the_crawl_early(app: ExploreApp) -> None:
    fill_form(app)
    app.crawl_tab.delay.set("0.3")

    app.crawl_tab.start()
    assert app.crawl_tab.stop_button.instate(["!disabled"])
    app.crawl_tab.stop()
    settle(app)

    assert app.crawl_tab.timer.get().startswith("■ Stopped")
    assert len(app.pages_tab.table.rows()) < 4
    assert app.crawl_tab.stop_button.instate(["disabled"])
    assert app.crawl_tab.start_button.instate(["!disabled"])


@pytest.mark.usefixtures("site")
def test_results_go_to_the_chosen_folder(app: ExploreApp, tmp_path: Path) -> None:
    fill_form(app)
    app.output_dir.set(str(tmp_path / "chosen"))

    app.crawl_tab.start()
    settle(app)

    assert len(list((tmp_path / "chosen").glob("crawl-*.json"))) == 1
    assert app.data_dir == tmp_path / "chosen"


def test_content_can_be_saved_anywhere(app: ExploreApp, tmp_path: Path) -> None:
    crawl_file = tmp_path / "old.json"
    save_crawl(crawl_file, ["a", "b"])
    app.results_tab.open_file(crawl_file)
    settle(app)
    for field, ticked in app.crawl_tab.fields.items():
        ticked.set(field in (ContentField.URL, ContentField.KEYWORDS))
    app.crawl_tab.separator.set("semicolon ( ; )")

    app.content_tab.save_csv(tmp_path / "export" / "keywords.csv")
    app.content_tab.save_sqlite(tmp_path / "export" / "crawl.db")

    lines = (tmp_path / "export" / "keywords.csv").read_text(encoding="utf-8-sig").splitlines()
    assert lines == ["url;keywords", f"{SITE}/;a, b"]
    assert (tmp_path / "export" / "crawl.db").stat().st_size > 0
