"""Streamlit 应用冒烟测试（第九阶段 Task 17）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = str(PROJECT_ROOT / "app.py")

PAGE_KEYS = (
    "dashboard",
    "circuit_lab",
    "performance",
    "closed_loop",
    "batch",
    "validation",
    "history",
    "about",
)


@pytest.mark.parametrize("page", PAGE_KEYS)
def test_page_renders_without_exception(page):
    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.session_state["page"] = page
    app.run()
    assert not app.exception, [str(item.value) for item in app.exception]
    assert app.session_state["page"] == page


def test_first_render_defaults_to_dashboard():
    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    assert not app.exception
    assert app.session_state["page"] == "dashboard"
    assert app.session_state["session_id"]


def test_footer_states_simulation_only():
    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.run()
    text = " ".join(str(item.value) for item in app.markdown)
    assert "simulation-only" in text


def test_unknown_page_falls_back_to_dashboard():
    app = AppTest.from_file(APP_PATH, default_timeout=120)
    app.session_state["page"] = "not-a-page"
    app.run()
    assert not app.exception
    assert app.session_state["page"] == "not-a-page"
