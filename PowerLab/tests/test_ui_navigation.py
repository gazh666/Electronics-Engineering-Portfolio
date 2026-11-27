"""页面导航结构测试（第九阶段 Task 5）。"""

from __future__ import annotations

from ui.navigation import GROUP_ORDER, PAGES
from ui.views import (
    about,
    batch,
    circuit_lab,
    closed_loop,
    dashboard,
    history,
    performance,
    validation,
)

EXPECTED_KEYS = (
    "dashboard",
    "circuit_lab",
    "performance",
    "closed_loop",
    "batch",
    "validation",
    "history",
    "about",
)


def test_eight_pages_registered():
    assert len(PAGES) == 8
    assert tuple(page.key for page in PAGES) == EXPECTED_KEYS


def test_page_keys_are_unique():
    keys = [page.key for page in PAGES]
    assert len(keys) == len(set(keys))


def test_page_labels_are_unique():
    labels = [page.label for page in PAGES]
    assert len(labels) == len(set(labels))


def test_groups_cover_all_pages():
    groups = {page.group for page in PAGES}
    assert groups == set(GROUP_ORDER)


def test_every_page_has_description():
    assert all(page.description.strip() for page in PAGES)


def test_every_page_has_renderer():
    renderers = (dashboard, circuit_lab, performance, closed_loop, batch, validation, history, about)
    assert all(callable(module.render) for module in renderers)
