"""The dashboard UI contract: what the static page may contain, and what it draws.

Static checks pin the CSP-compatible shape of the shipped assets (no inline
script or style, nothing remote, only same-origin API reads). The rendering
checks run the real app.js under Node against a fake DOM fed by the real API
payload builders, and are skipped when Node is not installed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from dashboard_support import DASHBOARD_DIR, make_task

from task_system.dashboard import snapshot
from task_system.dashboard.inventory import Inventory

STATIC = DASHBOARD_DIR / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
HARNESS = Path(__file__).with_name("ui_harness.js")

# The actions that will change shared state in a later increment. Each must be
# drawn, disabled, in every place the design shows it.
LATER_ACTIONS = {"queue", "cancel", "retry", "newtask", "additem", "pause", "recheck", "defer", "queueall"}


@pytest.mark.parametrize("name", ["index.html", "app.js", "app.css"])
def test_static_assets_are_ascii(name):
    (STATIC / name).read_text(encoding="utf-8").encode("ascii")


def test_index_has_no_inline_script_style_handlers_or_remote_references():
    assert re.findall(r"<script\b[^>]*>(.*?)</script>", HTML, re.S) == [""]
    assert re.findall(r"<script\b[^>]*\bsrc=\"([^\"]+)\"", HTML) == ["/static/app.js"]
    assert re.findall(r"<link\b[^>]*\bhref=\"([^\"]+)\"", HTML) == ["/static/app.css"]
    assert "<style" not in HTML.lower()
    assert not re.search(r"\sstyle\s*=", HTML)
    assert not re.search(r"\son[a-z]+\s*=", HTML)
    assert not re.search(r"(https?:)?//", re.sub(r"<!doctype[^>]*>", "", HTML, flags=re.I))


def test_css_pulls_in_nothing_remote():
    assert "@import" not in CSS
    assert not re.search(r"url\(\s*['\"]?(https?:)?//", CSS)


def test_app_js_makes_only_same_origin_api_reads_with_the_fragment_token():
    assert not re.search(r"\b(eval|XMLHttpRequest|WebSocket|EventSource|sendBeacon|localStorage|sessionStorage)\b", JS)
    assert "new Function" not in JS and "document.write" not in JS
    assert not re.search(r"https?://", JS)
    fetches = re.findall(r"fetch\(([^,)]+)", JS)
    assert fetches == ["path"]
    assert re.findall(r"api\(\s*'(/api/v1/[^']*)'", JS)
    assert "X-Task-Kit-Token" in JS and "location.hash" in JS
    assert not re.search(r"method\s*:", JS) and "'POST'" not in JS  # read-only in this increment


def test_app_js_never_emits_markup_the_csp_would_block():
    assert not re.search(r"""style\s*=\s*\\?['"]""", JS)
    assert not re.search(r"\bon[a-z]+\s*=", JS)
    assert "setAttribute('style'" not in JS and "cssText" not in JS


def test_the_project_filter_is_a_dropdown_not_chips():
    assert '<select class="proj-select" id="projectSelect"' in HTML and "All projects" in HTML
    assert 'id="chips"' not in HTML and "fchip" in HTML  # the Needs-you toggle keeps the chip look


def test_the_prototype_scaffolding_is_gone():
    for text in (HTML, JS, CSS):
        assert "Prototype" not in text and "Mock data" not in text and "demo" not in text.lower()


def test_header_actions_that_change_state_are_present_and_disabled():
    for action in ("pause", "newtask"):
        button = re.search(rf"<button[^>]*data-later=\"{action}\"[^>]*>", HTML)
        assert button and " disabled" in button.group(0) and "aria-disabled=\"true\"" in button.group(0)


def test_every_later_action_the_script_can_draw_goes_through_the_disabled_helpers():
    ids = set(re.findall(r"later(?:Button|Pill)\(.*?'(\w+)'\)", JS))
    ids |= set(re.findall(r'data-later="(\w+)"', JS))
    assert LATER_ACTIONS - {"pause", "newtask"} <= ids
    for helper in ("laterButton", "laterPill"):
        body = re.search(rf"function {helper}\(.*?\n}}", JS, re.S).group(0)
        assert "disabled" in body and 'aria-disabled="true"' in body and "data-later" in body
    # No action handler exists for any later action: a click could do nothing even if enabled.
    handlers = set(re.findall(r"^\s{2}(\w+): function", JS.split("var ACTIONS = {")[1].split("};")[0], re.M))
    assert not handlers & LATER_ACTIONS


# ---------------------------------------------------------------------------
# rendering, under Node
# ---------------------------------------------------------------------------

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ui")
    devroot = tmp / "devroot"
    project = devroot / "alpha"
    project.mkdir(parents=True)
    make_task(project, "dev/tasks", "open-one", title="Open <one>", summary="Does the open thing.",
              items=[{"id": "go", "title": "Go & do", "state": "available", "priority": "P1"},
                     {"id": "go-too", "title": "Go too", "state": "available"},
                     {"id": "wait", "title": "Wait", "state": "blocked-user", "note": "pick <one> or two"},
                     {"id": "mid", "title": "Mid", "state": "in-flight"},
                     {"id": "later", "title": "Later", "state": "deferred"}],
              sections={"go": "Do the thing."}, log="- 2026-10-01 09:00: began\n")
    make_task(project, "tmp", "stuck", title="Stuck", status="blocked", blocked_by=["dev/tasks/open-one"])
    make_task(project, "dev/tasks", "old", title="Old", status="closed")
    make_task(project, "tmp", "parked-task", title="Parked", status="deferred")
    snap = Inventory(parents=(devroot,), min_interval=0).snapshot()
    payload = snapshot.dashboard_payload(snap)
    task = snap.find_task(payload["projects"][0]["id"], "dev/tasks/open-one")
    detail = snapshot.item_detail(task, "wait")
    (tmp / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp / "detail.json").write_text(json.dumps(detail), encoding="utf-8")
    pid = payload["projects"][0]["id"]
    result = subprocess.run(
        [NODE, str(HARNESS), str(STATIC / "app.js"), str(tmp / "payload.json"), str(tmp / "detail.json"),
         f"{pid}|dev/tasks/open-one|wait", f"{pid}|dev/tasks/open-one"],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _buttons(html: str, attr: str) -> list[str]:
    return re.findall(rf"<button\b[^>]*\b{attr}=\"[^\"]*\"[^>]*>", html)


@needs_node
def test_app_js_runs_and_sends_the_token_on_every_request(rendered):
    assert rendered["requests"], "no API request was made"
    for request in rendered["requests"]:
        assert request["url"].startswith("/api/v1/")
        assert request["headers"] == {"X-Task-Kit-Token": "test-token"}
    assert rendered["pollDelays"] and rendered["pollDelays"][0] == 2000


@needs_node
def test_main_view_shows_pipelines_needs_you_in_flight_and_activity(rendered):
    main = rendered["main"]
    for text in ("In flight", "Needs you", "Pipelines", "Recent activity", "Open &lt;one&gt;", "Go &amp; do",
                 "Resolve in Claude Code", "needs you", "in flight", "Closed tasks", "Deferred tasks"):
        assert text in main, text
    assert "Open <one>" not in main and "pick <one>" not in main  # task text is escaped
    assert "alpha" in rendered["select"] and 'value=""' in rendered["select"]


@needs_node
def test_every_state_changing_action_is_drawn_and_disabled(rendered):
    """Queue, Cancel run, Retry, New task, Add item, ... are visible and cannot be clicked."""
    for surface in ("main", "itemPanel", "taskPanel"):
        for tag in _buttons(rendered[surface], "data-later"):
            assert " disabled" in tag and 'aria-disabled="true"' in tag, (surface, tag)
    drawn = {m for surface in ("main", "itemPanel") for m in re.findall(r'data-later="(\w+)"', rendered[surface])}
    assert {"queue", "cancel", "retry", "additem", "queueall", "recheck"} <= drawn
    assert "arrives in a later increment" in rendered["main"]
    assert "Read-only dashboard" in rendered["banners"]


@needs_node
def test_no_rendered_markup_carries_a_style_attribute_or_handler(rendered):
    for surface in ("main", "banners", "overview", "itemPanel", "itemResolve", "taskPanel", "taskResolve", "select"):
        html = rendered[surface]
        assert not re.search(r"\sstyle\s*=", html), surface
        assert not re.search(r"\son[a-z]+\s*=", html), surface


@needs_node
def test_resolve_in_claude_code_only_shows_commands_to_copy(rendered):
    assert "cmdbox" not in rendered["itemPanel"]
    box = rendered["itemResolve"]
    assert "cmdbox" in box and "/task work dev/tasks/open-one" in box and "claude" in box
    assert box.count('data-action="copy"') >= 3
    for surface in ("itemResolve", "taskResolve"):
        assert "data-action=\"queue\"" not in rendered[surface] and "POST" not in rendered[surface]
    assert "/task work dev/tasks/open-one" in rendered["taskResolve"]


@needs_node
def test_item_drawer_shows_state_note_plan_section_and_disabled_run_controls(rendered):
    panel = rendered["itemPanel"]
    assert "Waiting for you" in panel and "pick &lt;one&gt; or two" in panel
    assert "Run controls" in panel and "Run controls arrive in a later increment" in panel
    assert "plan.md section" in panel
    assert "No section for this item" in panel  # 'wait' has no section in the fixture
    assert "Open &lt;one&gt;" not in panel or "Open <one>" not in panel


@needs_node
def test_closing_the_drawer_returns_to_the_overview(rendered):
    assert "Projects" in rendered["afterClose"] and "How blocked work behaves" in rendered["afterClose"]
