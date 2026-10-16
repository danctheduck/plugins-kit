"""Legacy-engine guard: an older engine must never touch a tiered plugin.

Review finding R1 (profile-tiers plan). Every tiered plugins[] entry is authored
with install "manual", so an engine that predates tiers only ever UPDATES such a
plugin that is already installed; it never installs, enables, disables or
uninstalls one. This test runs the pre-tier engine's real ``_phase_plugins``
(read from git, the parent of the tier-schema commit, never the live file) over
a fixture copy of the proposed Spirit Crossing manifest with every lifecycle
call mocked, and asserts that.
"""

import copy
import importlib
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from bootstrap_lib.profiles import validate_plugin_entries

REPO = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "spiritcrossing_tiered_bootstrap.json"
LEGACY_REV = "4e366554^"
LIB_PATH = "plugins/bootstrap/bootstrap_lib"
LEGACY_PKG = "legacy_bootstrap_lib_pre_tiers"

# Calls that change what is installed or enabled; none may name a tiered ref.
MUTATORS = (
    "install_plugin", "enable_plugin_in_claude", "enable_plugin_at_scope",
    "disable_plugin_at_scope", "disable_plugin_in_claude", "ensure_registry_scope",
    "uninstall_plugin", "uninstall_installs",
)


@pytest.fixture(scope="module")
def legacy_pkg(tmp_path_factory):
    """Import the pre-tier bootstrap_lib from git under a private package name."""
    proc = subprocess.run(
        ["git", "-C", str(REPO), "archive", LEGACY_REV, LIB_PATH],
        capture_output=True,
    )
    assert proc.returncode == 0, "git archive failed: %s" % proc.stderr.decode()
    root = tmp_path_factory.mktemp("legacy_lib")
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(root, filter="data")
    pkg_dir = root / LIB_PATH
    spec = importlib.util.spec_from_file_location(
        LEGACY_PKG, pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[LEGACY_PKG] = module
    spec.loader.exec_module(module)
    engine = importlib.import_module(LEGACY_PKG + ".engine")
    lifecycle = importlib.import_module(LEGACY_PKG + ".marketplace_lifecycle")
    assert not hasattr(lifecycle, "uninstall_plugin"), "not the pre-tier lifecycle"
    yield engine, lifecycle
    for name in [n for n in sys.modules
                 if n == LEGACY_PKG or n.startswith(LEGACY_PKG + ".")]:
        del sys.modules[name]


class _Ctx:
    def __init__(self, manifest):
        self.manifest = manifest
        self.project_dir = "/proj"
        self.unusable_marketplaces = ()
        self.actions, self.oks, self.failures = [], [], []

    def action(self, message, display=None, detail=None):
        self.actions.append(message)

    def ok(self, message):
        self.oks.append(message)

    def quiet(self, message):
        pass

    def fail(self, entry, display=None, detail=None, **failure):
        self.failures.append(entry)


def _load_fixture():
    return json.loads(FIXTURE.read_text(encoding="ascii"))


def _tiered_entries(manifest):
    entries = [e for e in manifest["plugins"] if "tier" in e]
    for body in manifest.get("profiles", {}).values():
        entries.extend(e for e in body.get("plugins", []) if "tier" in e)
    return entries


def _all_lint_errors(manifest):
    errors = validate_plugin_entries(manifest["plugins"], "plugins")
    for name, body in manifest.get("profiles", {}).items():
        errors.extend(validate_plugin_entries(body.get("plugins"), "profile " + name))
    return errors


def _legacy_view(manifest):
    """What an old engine sees: the base list, plus every profile entry merged in.

    An old engine reads only ``plugins``; merging the profile entries too is the
    worst case, a manifest where every tiered entry reached the legacy path.
    """
    merged = copy.deepcopy(manifest["plugins"])
    seen = {e["ref"] for e in merged}
    for body in manifest.get("profiles", {}).values():
        for entry in body.get("plugins", []):
            if entry["ref"] not in seen:
                seen.add(entry["ref"])
                merged.append(copy.deepcopy(entry))
    return {"plugins": merged}


def _run_legacy(engine, lifecycle, monkeypatch, manifest, installed, enabled=True):
    """Run the legacy plugin phase with every lifecycle call mocked; return calls."""
    calls = []
    result = lifecycle.LifecycleResult
    version = lifecycle.VersionCheckResult

    def rec(name, make):
        def fn(ref, *args, **kwargs):
            calls.append((name, ref))
            return make(ref)
        monkeypatch.setattr(lifecycle, name, fn, raising=False)

    def ok(ref):
        return result(True, ref, "ok")

    rec("check_plugin_installed", lambda r: result(r in installed, r, ""))
    rec("check_plugin_enabled_at_scope", lambda r: result(enabled, r, ""))
    rec("check_plugin_version", lambda r: version(True, r, "1.0.0", "1.0.0", ""))
    rec("check_plugin_min_version", lambda r: version(True, r, "1.0.0", "1.0.0", ""))
    rec("update_plugin", ok)
    rec("pinned_marketplace_sha", lambda r: "")
    for name in MUTATORS:
        if name == "ensure_registry_scope":
            rec(name, lambda r: lifecycle.ScopeSyncResult(True, r, False, False, ""))
        else:
            rec(name, ok)
    monkeypatch.setattr(lifecycle, "resolve_claude_cli", lambda: "/fake/claude")
    monkeypatch.setitem(engine._marketplace_pass, "unusable", set())

    ctx = _Ctx(manifest)
    engine._phase_plugins(ctx)
    assert ctx.failures == []
    return calls


def test_fixture_is_the_proposed_shape():
    manifest = _load_fixture()
    assert _all_lint_errors(manifest) == []
    assert sorted(manifest["profiles"]) == ["artist", "custom", "designer", "engineer"]
    tiered = _tiered_entries(manifest)
    assert tiered and all(e["install"] == "manual" for e in tiered)
    base_tiered = [e for e in manifest["plugins"] if "tier" in e]
    assert {e["ref"] for e in base_tiered} == {
        "plugins-kit:bootstrap-stuck-fix", "spryfox-plugins:claude-sandbox", "spryfox-plugins:godot-kit"}
    assert all(e["install"] == "auto" for e in manifest["plugins"] if "tier" not in e)


@pytest.mark.parametrize("installed_all", [False, True], ids=["nothing_installed", "all_installed"])
@pytest.mark.parametrize("enabled", [True, False], ids=["enabled", "disabled"])
def test_legacy_engine_never_touches_tiered_plugins(
        legacy_pkg, monkeypatch, installed_all, enabled):
    engine, lifecycle = legacy_pkg
    manifest = _load_fixture()
    tiered_refs = {e["ref"] for e in _tiered_entries(manifest)}
    untiered_refs = {e["ref"] for e in manifest["plugins"] if "tier" not in e}
    installed = (tiered_refs | untiered_refs) if installed_all else set()

    calls = _run_legacy(
        engine, lifecycle, monkeypatch, _legacy_view(manifest), installed, enabled)

    touched = [(n, r) for n, r in calls if r in tiered_refs and n in MUTATORS]
    assert touched == []
    # Control: the mocks are live and every tiered ref went through the phase.
    assert {r for n, r in calls if n == "check_plugin_installed"} >= tiered_refs
    if not installed_all:
        # Untiered base plugins are still installed, so the mocks would show one.
        assert {r for n, r in calls if n == "install_plugin"} == untiered_refs


def test_lint_rejects_a_tiered_entry_without_install_manual():
    manifest = _load_fixture()
    assert _all_lint_errors(manifest) == []
    del manifest["plugins"][-1]["install"]
    errors = _all_lint_errors(manifest)
    assert len(errors) == 1 and "install" in errors[0] and "godot-kit" in errors[0]

    manifest = _load_fixture()
    manifest["profiles"]["designer"]["plugins"][1]["install"] = "auto"
    assert any("install" in e for e in _all_lint_errors(manifest))


def test_legacy_engine_would_install_if_the_lint_were_bypassed(legacy_pkg, monkeypatch):
    """Red control: an auto tiered entry IS installed by the old engine."""
    engine, lifecycle = legacy_pkg
    manifest = _load_fixture()
    manifest["plugins"][-1]["install"] = "auto"
    calls = _run_legacy(engine, lifecycle, monkeypatch, _legacy_view(manifest), set())
    assert ("install_plugin", "spryfox-plugins:godot-kit") in calls
