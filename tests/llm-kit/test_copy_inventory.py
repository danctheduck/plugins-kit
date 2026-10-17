"""Inventory of the quarantined copy and the per-suite disposition ledgers.

Two things are reconciled here without running the legacy suites:

* every legacy test file has exactly one ledger row, and the rows' collection
  counts add up to the 5,276 tests the three suites collect;
* every legacy module has a copy (or a recorded reason it has none), every
  legacy-root occurrence in the copy's source is classified, and the copy equals
  what the generator renders from the legacy source today.

The differential itself is test_repointed_suites.py.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import repoint

GEN = repoint.load_generator()
REPO = repoint.REPO
SUITES = repoint.SUITES
MAP = GEN.load_map()
LEDGERS = {suite: repoint.load_ledger(suite) for suite in SUITES}


def _legacy_test_files(suite: str) -> list[str]:
    return [p for p in GEN.git_files(f"tests/{suite}") if p.rsplit("/", 1)[1].startswith("test_")
            and p.endswith(".py")]


# --- the disposition ledgers ---------------------------------------------

@pytest.mark.parametrize("suite", SUITES)
def test_every_legacy_test_file_has_exactly_one_row(suite):
    rows = [r["path"] for r in LEDGERS[suite]["rows"]]
    assert len(rows) == len(set(rows)), "duplicate ledger rows: " + ", ".join(
        sorted({p for p in rows if rows.count(p) > 1}))
    legacy = set(_legacy_test_files(suite))
    assert not legacy - set(rows), f"legacy test files with no row: {sorted(legacy - set(rows))}"
    assert not set(rows) - legacy, f"rows naming no legacy test file: {sorted(set(rows) - legacy)}"


@pytest.mark.parametrize("suite", SUITES)
def test_rows_are_classified_and_explained(suite):
    for row in LEDGERS[suite]["rows"]:
        assert row["disposition"] in GEN.DISPOSITIONS, row["path"]
        assert row["reason"].strip(), f"{row['path']}: no reason recorded"
        assert row["collection_count"] >= 0
        if row["disposition"] != "rewrite":
            assert row.get("declared_differences", {}) == {}, (
                f"{row['path']}: declared differences belong to mirrored rows")
            assert row["rewrite_classes"] == []


@pytest.mark.parametrize("suite", SUITES)
def test_declared_differences_name_their_own_file(suite):
    for row in LEDGERS[suite]["rows"]:
        file_name = row["path"].rsplit("/", 1)[1]
        for node, entry in row.get("declared_differences", {}).items():
            assert node.split("::", 1)[0] == f"{suite}/{file_name}", node
            assert entry["mirror_status"] in ("skipped", "failed"), node
            assert entry["reason"].strip(), node
        for node in row.get("baseline_failures", []):
            assert node.split("::", 1)[0] == f"{suite}/{file_name}", node


def test_collection_counts_reconcile_to_every_collected_test():
    totals = {suite: sum(r["collection_count"] for r in LEDGERS[suite]["rows"]) for suite in SUITES}
    assert totals == repoint.SUITE_TOTALS
    assert sum(totals.values()) == repoint.TOTAL_TESTS
    for suite in SUITES:
        assert LEDGERS[suite]["collection_total"] == totals[suite]


def test_the_expected_baseline_failure_is_recorded():
    rows = {r["path"]: r for r in LEDGERS["content-pipeline-kit"]["rows"]}
    row = rows["tests/content-pipeline-kit/test_version_matches_plugin_json.py"]
    assert row["baseline_failures"] == [
        "content-pipeline-kit/test_version_matches_plugin_json.py::test_version_matches_plugin_json"]


def test_rewrite_classes_match_the_current_rewrite():
    """The classes a row records are what the rewriter applies today."""
    mirror = GEN.build_mirror(MAP, LEDGERS)
    for suite in SUITES:
        for row in LEDGERS[suite]["rows"]:
            if row["disposition"] != "rewrite":
                continue
            name = row["path"].rsplit("/", 1)[1]
            assert mirror[f"{suite}/{name}"][1] == row["rewrite_classes"], row["path"]


# --- the copy -------------------------------------------------------------

def test_copy_matches_the_legacy_trees_and_the_map():
    assert GEN.check_problems() == []


def test_every_legacy_package_file_is_classified():
    states = {}
    for row in GEN.legacy_package_files(MAP):
        states.setdefault(row["state"], []).append(row["legacy"])
    assert set(states) <= {"copy", "dropped", "excluded"}
    assert sorted(states["dropped"]) == sorted(MAP["dropped"])
    assert sorted(states["excluded"]) == sorted(MAP["excluded"])
    assert len(states["copy"]) + len(states["dropped"]) + len(states["excluded"]) == sum(
        len(GEN.git_files(spec["source_dir"])) for spec in MAP["packages"].values())


def test_the_copy_holds_no_legacy_import():
    rt = GEN.roots(MAP)
    offenders = {}
    for rel in GEN.build_copy(MAP):
        if rel.endswith(".py"):
            found = GEN.remaining_legacy_imports(GEN._read(REPO / rel), rt)
            if found:
                offenders[rel] = found
    assert offenders == {}


def test_root_initializers_are_empty():
    assert GEN._read(REPO / "plugins/llm-kit/lib/llm_kit/__init__.py") == b""
    assert GEN._read(REPO / "plugins/llm-kit/lib/llm_kit/_copy/__init__.py") == b""


def test_guard_is_the_canonical_bytes():
    canonical = REPO / MAP["guard"]["canonical"]
    assert GEN._read(REPO / "plugins/llm-kit/lib/llm_kit/bootstrap_guard.py") == GEN._read(canonical)


def test_no_vendored_guard_is_copied():
    assert not list((REPO / "plugins/llm-kit/lib/llm_kit/_copy").rglob("bootstrap_guard.py"))


def test_string_sites_carry_a_known_action_and_a_reason():
    for key, entry in MAP["string_sites"].items():
        assert entry["action"] in GEN.SITE_ACTIONS, key
        assert entry["reason"].strip(), key
        assert key.startswith(entry["file"] + "::"), key


def test_every_rewrite_site_names_the_copy():
    """A site classified `rewrite` renders a constant that names llm_kit._copy."""
    wanted: dict[str, int] = {}
    for entry in MAP["string_sites"].values():
        if entry["action"] == "rewrite":
            wanted[entry["file"]] = wanted.get(entry["file"], 0) + 1
    assert wanted, "no rewrite site is classified"
    for legacy, count in wanted.items():
        rewritten = GEN.rewrite_lib_source(GEN._read(REPO / legacy), legacy, MAP)
        constants = GEN.string_constants(ast.parse(rewritten.decode("utf-8")))
        named = [c for c in constants if "llm_kit._copy." in c.value or c.value.startswith("llm_kit._copy")]
        assert len(named) >= count, f"{legacy}: {len(named)} constants name the copy, {count} sites rewrite"


# --- the import-root guard --------------------------------------------------

def _child(code: str, tmp_path: Path, extra_env=None) -> subprocess.CompletedProcess:
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(GEN.render_sitecustomize(MAP), encoding="utf-8")
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": os.pathsep.join([str(site), str(REPO / "plugins/llm-kit/lib"),
                                       str(REPO / "plugins/bootstrap")]),
        "_BOOTSTRAP_GUARD_SKIP_REEXEC": "1",
        "PYTHONNOUSERSITE": "1",
    })
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=env, encoding="utf-8", errors="replace", cwd=str(REPO))


def test_every_copied_module_imports_under_the_guard(tmp_path):
    code = (
        "import importlib, pkgutil\n"
        "import llm_kit._copy as c\n"
        "n = 0\n"
        "for m in pkgutil.walk_packages(c.__path__, 'llm_kit._copy.'):\n"
        "    importlib.import_module(m.name); n += 1\n"
        "print(n)\n"
    )
    result = _child(code, tmp_path)
    assert result.returncode == 0, result.stderr[-2000:]
    assert int(result.stdout.strip()) >= 100


@pytest.mark.parametrize("legacy", ["llm_scripting_kit", "content_pipeline", "job_kit"])
def test_the_guard_rejects_a_legacy_top_level_import(tmp_path, legacy):
    result = _child(f"import {legacy}", tmp_path)
    assert result.returncode != 0
    assert "legacy package imported in a mirrored run" in result.stderr


def test_the_guard_rejects_a_legacy_library_on_sys_path(tmp_path):
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import json\n"
        "import xml.dom\n"
    ) % str(REPO / "plugins/job-kit/lib")
    result = _child(code, tmp_path)
    assert result.returncode != 0
    assert "legacy plugin directory on sys.path" in result.stderr


def test_the_guard_rejects_a_legacy_path_handed_to_a_child(tmp_path):
    code = (
        "import os, subprocess, sys\n"
        "env = dict(os.environ, PYTHONPATH=%r)\n"
        "subprocess.run([sys.executable, '-c', 'pass'], env=env)\n"
    ) % str(REPO / "plugins/content-pipeline-kit/lib")
    result = _child(code, tmp_path)
    assert result.returncode != 0
    assert "legacy plugin path handed to a child process" in result.stderr


def test_the_guard_keeps_the_mirror_on_a_child_environment(tmp_path):
    code = (
        "import os, subprocess, sys\n"
        "out = subprocess.run([sys.executable, '-c', 'import os; print(os.environ[\"PYTHONPATH\"])'],\n"
        "                     env={'PYTHONPATH': 'x', 'SystemRoot': os.environ.get('SystemRoot', '')},\n"
        "                     capture_output=True, text=True)\n"
        "print(out.stdout.strip())\n"
    )
    result = _child(code, tmp_path)
    assert result.returncode == 0, result.stderr
    assert os.path.normcase(str(REPO / "tmp")) in os.path.normcase(result.stdout)


# --- the porting ledger -----------------------------------------------------

def test_porting_ledger_is_well_formed_and_only_names_moved_modules():
    ledger = json.loads((REPO / "tests/llm-kit/porting-ledger.json").read_text(encoding="utf-8"))
    assert ledger["schema"] == 1
    for entry in ledger["entries"]:
        assert set(ledger["entry_fields"]) <= set(entry), entry
        assert entry["disposition"] in ledger["dispositions"], entry
        module = MAP["modules"].get(entry["legacy_path"])
        assert module is not None and module["state"] != "unmoved", (
            f"{entry['legacy_path']}: a legacy edit is recorded for a module that has not moved; "
            "re-run the sync instead")


def test_a_legacy_edit_after_a_move_is_refused_until_it_is_recorded(tmp_path, monkeypatch):
    """The sync keeps a moved module's baseline and refuses an unrecorded legacy edit."""
    import hashlib

    def sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    legacy_path = "plugins/x/lib/pkg/mod.py"
    legacy = tmp_path / legacy_path
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"A = 1\n")
    ledger = tmp_path / "porting-ledger.json"
    ledger.write_text(json.dumps({"schema": 1, "entries": []}), encoding="utf-8")
    monkeypatch.setattr(GEN, "REPO", tmp_path)
    monkeypatch.setattr(GEN, "PORTING_LEDGER", ledger)
    monkeypatch.setattr(GEN, "legacy_package_files", lambda _m: [
        {"legacy": legacy_path, "package": "pkg", "state": "copy", "copy": "c/mod.py"}])
    mapping = {"modules": {legacy_path: {
        "copy": "c/mod.py", "state": "moved",
        "legacy_sha256": sha(b"OLD\n"), "copy_sha256": sha(b"MOVED\n")}}}

    with pytest.raises(SystemExit, match="legacy edited after the module moved"):
        GEN.module_table(mapping, {})

    ledger.write_text(json.dumps({"schema": 1, "entries": [{
        "legacy_path": legacy_path, "legacy_sha256": sha(b"A = 1\n")}]}), encoding="utf-8")
    table = GEN.module_table(mapping, {})
    assert table[legacy_path]["legacy_sha256"] == sha(b"OLD\n")
    assert table[legacy_path]["copy_sha256"] == sha(b"MOVED\n")
