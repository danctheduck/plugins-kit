"""The dashboard inventory: discovery, caching, deduplication, read-only.

Hypothesis tested here: the task system's own discovery and validation can feed
the dashboard without changing ``task_system`` -- the inventory must agree with
``collect_listing`` (what ``task.py list --scope all`` projects) on which tasks
exist and how they classify.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from dashboard_support import link_dir, make_task, tree_digest

from task_system.dashboard.inventory import (
    Inventory,
    InventorySnapshot,
    project_id_for,
)
from task_system.discovery import discover
from task_system.listing import collect_listing

ITEMS = [
    {"id": "later-item", "title": "Later item", "state": "available", "priority": "P3"},
    {"id": "first-item", "title": "First item", "state": "available", "priority": "P1"},
    {"id": "mid-flight", "title": "Mid flight", "state": "in-flight"},
    {"id": "needs-me", "title": "Needs me", "state": "blocked-user", "note": "decide the loop length"},
    {"id": "parked", "title": "Parked", "state": "deferred"},
]


def make_world(tmp_path: Path) -> Path:
    devroot = tmp_path / "devroot"
    for name in ("alpha", "beta", "empty"):
        (devroot / name).mkdir(parents=True)
    make_task(devroot / "alpha", "dev/tasks", "open-one", title="Open one", items=ITEMS)
    make_task(devroot / "alpha", "tmp", "scratch", title="Scratch", status="deferred")
    make_task(devroot / "alpha", "dev/tasks", "done-one", title="Done", status="closed")
    make_task(devroot / "beta", "dev/tasks", "blocked-one", title="Blocked one", status="blocked",
              blocked_by=["dev/tasks/open-one"])
    return devroot


def snapshot_of(devroot: Path, **kw) -> tuple[Inventory, InventorySnapshot]:
    inventory = Inventory(parents=(devroot,), min_interval=0.0, **kw)
    return inventory, inventory.snapshot()


def tasks_by_id(snap: InventorySnapshot) -> dict[tuple[str, str], object]:
    return {(p.name, t.id): t for p in snap.projects for t in p.tasks}


def test_enumerates_projects_tasks_and_items(tmp_path):
    devroot = make_world(tmp_path)
    _inv, snap = snapshot_of(devroot)
    assert [p.name for p in snap.projects] == ["alpha", "beta"]  # `empty` has no tasks
    tasks = tasks_by_id(snap)
    assert set(tasks) == {
        ("alpha", "dev/tasks/open-one"), ("alpha", "tmp/scratch"), ("alpha", "dev/tasks/done-one"),
        ("beta", "dev/tasks/blocked-one"),
    }
    core = tasks[("alpha", "dev/tasks/open-one")].core
    assert core.classification == "active"
    assert core.title == "Open one"
    # Items are in plan.md priority order (P1 < P3; unprioritised last, block order kept).
    assert [i.id for i in core.items] == ["first-item", "later-item", "mid-flight", "needs-me", "parked"]
    assert {i.id: i.ui_state for i in core.items} == {
        "first-item": "available", "later-item": "available", "mid-flight": "in-flight",
        "needs-me": "blocked", "parked": "deferred",
    }
    assert tasks[("beta", "dev/tasks/blocked-one")].core.classification == "blocked"
    assert tasks[("beta", "dev/tasks/blocked-one")].core.blocked_by == ("dev/tasks/open-one",)
    assert tasks[("alpha", "tmp/scratch")].core.classification == "deferred"


def test_project_identity_is_a_hash_of_the_canonical_root(tmp_path):
    devroot = make_world(tmp_path)
    _inv, snap = snapshot_of(devroot)
    alpha = next(p for p in snap.projects if p.name == "alpha")
    assert alpha.id == project_id_for(devroot / "alpha")
    assert len(alpha.id) == 64
    assert alpha.id != next(p for p in snap.projects if p.name == "beta").id


def test_skips_parked_archives_and_noncanonical_folders(tmp_path):
    devroot = make_world(tmp_path)
    make_task(devroot / "alpha", "dev/tasks/archived-tasks", "gone", title="Parked")
    make_task(devroot / "alpha", "dev/tasks/group", "nested", title="Nested too deep")
    (devroot / "alpha" / "dev" / "tasks" / "no-yaml").mkdir()
    _inv, snap = snapshot_of(devroot)
    ids = {t.id for p in snap.projects for t in p.tasks}
    assert not any("archived-tasks" in i or "nested" in i or "no-yaml" in i for i in ids)


def test_unchanged_poll_reads_nothing_and_a_change_reads_one_folder(tmp_path):
    devroot = make_world(tmp_path)
    inv, first = snapshot_of(devroot)
    loads = inv.loads
    assert loads == 4
    again = inv.snapshot()
    assert inv.loads == loads and again.revision == first.revision
    # Edit ONE task's plan.md (size changes): exactly that folder is re-read.
    plan = devroot / "alpha" / "dev" / "tasks" / "open-one" / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    inv.snapshot()
    assert inv.loads == loads + 1
    # An explicit refresh re-validates everything (git state is not in a fingerprint).
    inv.snapshot(force=True)
    assert inv.loads == loads + 1 + 4


def test_revision_tracks_what_is_shown(tmp_path):
    devroot = make_world(tmp_path)
    inv, first = snapshot_of(devroot)
    plan = devroot / "alpha" / "dev" / "tasks" / "open-one" / "plan.md"
    plan.write_text(plan.read_text(encoding="utf-8").replace("id: parked\n    title: Parked\n    state: deferred",
                                                             "id: parked\n    title: Parked\n    state: available"),
                    encoding="utf-8")
    assert inv.snapshot().revision != first.revision


def test_min_interval_throttles_the_walk(tmp_path):
    devroot = make_world(tmp_path)
    now = [100.0]
    inv = Inventory(parents=(devroot,), min_interval=5.0, clock=lambda: now[0])
    first = inv.snapshot()
    (devroot / "alpha" / "dev" / "tasks" / "open-one" / "log.md").write_text("changed\n", encoding="utf-8")
    assert inv.snapshot() is first  # inside the interval: the cached snapshot
    now[0] += 6
    assert inv.snapshot() is not first
    assert inv.snapshot(force=True) is not first


def test_refreshing_never_writes_a_task_folder(tmp_path):
    """RED CHECK input: a refresh, forced or not, leaves every byte unchanged."""
    devroot = make_world(tmp_path)
    before = tree_digest(devroot)
    inv = Inventory(parents=(devroot,), min_interval=0.0)
    for force in (False, False, True, False, True):
        inv.snapshot(force=force)
    assert tree_digest(devroot) == before


def test_folder_reached_through_two_projects_is_owned_once(tmp_path):
    """A linked dev/tasks is walked once and assigned to the shortest project name."""
    devroot = tmp_path / "devroot"
    shared = tmp_path / "shared-tasks"
    make_task(shared.parent, "shared-tasks", "shared-task", title="Shared")
    for name in ("plugins-kit", "plugins-kit3"):
        (devroot / name / "dev").mkdir(parents=True)
        link_dir(devroot / name / "dev" / "tasks", shared)
    _inv, snap = snapshot_of(devroot)
    owners = [(p.name, t.id) for p in snap.projects for t in p.tasks]
    assert owners == [("plugins-kit", "dev/tasks/shared-task")]


def test_inventory_agrees_with_the_task_system_listing(tmp_path):
    """The hypothesis: same task set, same classification as `list --scope all`."""
    devroot = make_world(tmp_path)
    for name in ("plugins-kit", "plugins-kit3"):
        (devroot / name / "dev").mkdir(parents=True)
    shared = tmp_path / "shared-tasks"
    make_task(shared.parent, "shared-tasks", "shared-task", title="Shared")
    for name in ("plugins-kit", "plugins-kit3"):
        link_dir(devroot / name / "dev" / "tasks", shared)
    _inv, snap = snapshot_of(devroot)
    mine = {(p.name, t.id): t.core.classification for p in snap.projects for t in p.tasks}
    listing = collect_listing("all", devroot, devroot=devroot)
    theirs = {(v.project_name, v.id): v.status for v in listing.views if v.status != "archived"}
    records = discover("all", devroot, devroot=devroot)
    assert mine == theirs
    assert {(r.project_name, r.id) for r in records} == set(mine)


def test_findings_are_carried_per_task(tmp_path):
    devroot = make_world(tmp_path)
    # A pre-contract folder: no task_items block in plan.md -> validate warns.
    folder = make_task(devroot / "alpha", "tmp", "old-style")
    (folder / "plan.md").write_text("# Plan\n\nno block here\n", encoding="utf-8")
    _inv, snap = snapshot_of(devroot)
    core = tasks_by_id(snap)[("alpha", "tmp/old-style")].core
    assert core.has_items_block is False
    assert any("task_items" in w for w in core.warnings)


def test_missing_project_directories_is_reported_not_raised(tmp_path):
    config = tmp_path / "task.local.yaml"
    config.write_text("project_directories: []\n", encoding="utf-8")
    old = os.environ.pop("DEVROOT", None)
    try:
        inv = Inventory(config_path=config, min_interval=0.0)
        snap = inv.snapshot()
    finally:
        if old is not None:
            os.environ["DEVROOT"] = old
    assert snap.projects == ()
    assert [e["code"] for e in snap.errors] == ["discovery"]
    assert "project directories" in snap.errors[0]["message"]


def test_configured_project_directories_are_read_from_the_config(tmp_path):
    devroot = make_world(tmp_path)
    config = tmp_path / "task.local.yaml"
    config.write_text(f"project_directories:\n  - '{devroot.as_posix()}'\n", encoding="utf-8")
    snap = Inventory(config_path=config, min_interval=0.0).snapshot()
    assert [p.name for p in snap.projects] == ["alpha", "beta"]


def test_a_removed_task_folder_leaves_the_inventory(tmp_path):
    import shutil

    devroot = make_world(tmp_path)
    inv, _first = snapshot_of(devroot)
    shutil.rmtree(devroot / "alpha" / "tmp" / "scratch")
    snap = inv.snapshot()
    assert ("alpha", "tmp/scratch") not in tasks_by_id(snap)
