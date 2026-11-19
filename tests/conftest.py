"""Shared pytest fixtures."""

import importlib.util
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


# Python builds without Tk cannot even import the desktop application tests.
collect_ignore = [] if importlib.util.find_spec("tkinter") else ["test_gui.py"]
