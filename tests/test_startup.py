"""The window starts without the heavy libraries and loads them in the background."""

import subprocess
import sys

import pytest

pytest.importorskip("tkinter")

from exploreit.gui.widgets import Preloader

HEAVY = ["numpy", "pandas", "matplotlib", "networkx", "scipy", "pydantic", "httpx", "bs4", "lxml"]


def test_opening_the_window_module_loads_no_heavy_library() -> None:
    check = f"import sys, exploreit.gui.app; print([m for m in {HEAVY!r} if m in sys.modules])"

    loaded = subprocess.run(
        [sys.executable, "-c", check], capture_output=True, text=True, check=True
    ).stdout.strip()

    assert loaded == "[]"


def test_preloader_imports_preferred_modules_first(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []
    monkeypatch.setattr("exploreit.gui.widgets.importlib.import_module", imported.append)
    preloader = Preloader()
    preloader._start = lambda: None  # type: ignore[method-assign]

    preloader.load(["fake.a", "fake.b", "fake.c"])
    preloader.prefer(["fake.c"])
    preloader.load(["fake.a", "fake.d"])
    preloader._run()

    assert imported == ["fake.c", "fake.a", "fake.b", "fake.d"]
    assert preloader.loaded == imported


def test_preloader_skips_modules_that_fail_to_import() -> None:
    preloader = Preloader()
    preloader.load(["exploreit.no_such_module", "json"])
    assert preloader._thread is not None
    preloader._thread.join(timeout=10)

    assert "exploreit.no_such_module" not in preloader.loaded
