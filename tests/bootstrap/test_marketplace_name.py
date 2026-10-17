"""Marketplace name derived from a bootstrap plugin root.

Dev checkout: ``<checkout>/plugins/bootstrap``, named by ``name`` in
``<checkout>/.claude-plugin/marketplace.json`` (the directory name is whatever
the checkout was cloned as). Cache: ``cache/<marketplace>/bootstrap/<version>``,
named by the directory.

Three owners must agree, and each is covered here:

- ``bootstrap_lib.marketplace_name.marketplace_name_for`` (the engine's value),
- ``hooks/marketplace-name.sh`` (the two hook scripts, which run before Python
  exists and so cannot call the helper),
- the engine, which labels its log with the value.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bootstrap_lib.marketplace_name import (
    MarketplaceManifestError,
    marketplace_name_for,
)
from bootstrap.link_compat import link_tree
from bootstrap.test_engine_multiplugin import (
    BOOTSTRAP_ROOT,
    _isolated_env,
    _write_minimal_defaults,
    run_engine,
)
from bootstrap.test_sessionstart_interpreter_env import BASH, needs_bash

HOOK_LIB = Path(BOOTSTRAP_ROOT) / "hooks" / "marketplace-name.sh"

REAL_NAME = "real-marketplace"
CHECKOUT_DIR = "checkout-clone"


def _dev_layout(tmp_path: Path, manifest_text: str | None) -> Path:
    """``<tmp>/checkout-clone/plugins/bootstrap``, manifest text as given."""
    checkout = tmp_path / CHECKOUT_DIR
    root = checkout / "plugins" / "bootstrap"
    root.mkdir(parents=True)
    if manifest_text is not None:
        manifest = checkout / ".claude-plugin" / "marketplace.json"
        manifest.parent.mkdir()
        manifest.write_text(manifest_text, encoding="utf-8")
    return root


def _cache_layout(tmp_path: Path) -> Path:
    root = tmp_path / "plugins" / "cache" / REAL_NAME / "bootstrap" / "1.2.3"
    root.mkdir(parents=True)
    return root


def _manifest(**top) -> str:
    return json.dumps({"name": REAL_NAME, **top}, indent=2)


def _shell_name(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, "-c", '. "$1" && bootstrap_marketplace_name "$2"', "_",
         HOOK_LIB.as_posix(), root.as_posix()],
        capture_output=True, text=True, timeout=60,
    )


class TestHelper:
    def test_dev_checkout_yields_the_manifest_name_not_the_directory(self, tmp_path):
        root = _dev_layout(tmp_path, _manifest())
        assert marketplace_name_for(str(root)) == REAL_NAME
        assert os.path.basename(str(root.parent.parent)) == CHECKOUT_DIR

    def test_cache_layout_yields_the_directory_name(self, tmp_path):
        assert marketplace_name_for(str(_cache_layout(tmp_path))) == REAL_NAME

    def test_checkout_without_a_manifest_yields_the_directory_name(self, tmp_path):
        assert marketplace_name_for(str(_dev_layout(tmp_path, None))) == CHECKOUT_DIR

    def test_the_top_level_name_wins_over_owner_and_plugin_names(self, tmp_path):
        text = json.dumps({
            "owner": {"name": "someone"},
            "plugins": [{"name": "unreal-kit"}],
            "name": REAL_NAME,
        })
        assert marketplace_name_for(str(_dev_layout(tmp_path, text))) == REAL_NAME

    @pytest.mark.parametrize("text", [
        "{not json",
        "[]",
        json.dumps({"description": "no name"}),
        json.dumps({"name": ""}),
        json.dumps({"name": 7}),
        json.dumps({"owner": {"name": "only nested"}}),
    ], ids=["invalid-json", "not-object", "no-name", "empty-name",
            "non-string-name", "nested-name-only"])
    def test_a_manifest_without_a_name_fails_loudly(self, tmp_path, text):
        root = _dev_layout(tmp_path, text)
        with pytest.raises(MarketplaceManifestError) as err:
            marketplace_name_for(str(root))
        assert "marketplace.json" in str(err.value)

    def test_an_undecodable_manifest_fails_loudly(self, tmp_path):
        root = _dev_layout(tmp_path, "{}")
        (tmp_path / CHECKOUT_DIR / ".claude-plugin" / "marketplace.json").write_bytes(
            b'{"name": "\xff\xfe"}')
        with pytest.raises(MarketplaceManifestError):
            marketplace_name_for(str(root))


@needs_bash
class TestShellAgreesWithHelper:
    """The hooks cannot import the helper; the port must give the same answer."""

    VALID = {
        "plain": _manifest(),
        "name-last": json.dumps({"owner": {"name": "o"},
                                 "plugins": [{"name": "p"}], "name": REAL_NAME}),
        "braces-in-strings": json.dumps({
            "description": "has { and ] and \"name\": \"decoy\" inside",
            "plugins": [{"name": "p", "description": "}}"}],
            "name": REAL_NAME}),
        "single-line": json.dumps({"name": REAL_NAME, "plugins": []}),
    }

    @pytest.mark.parametrize("case", sorted(VALID))
    def test_dev_checkout_with_manifest(self, tmp_path, case):
        root = _dev_layout(tmp_path, self.VALID[case])
        result = _shell_name(root)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == marketplace_name_for(str(root)) == REAL_NAME

    def test_cache_layout(self, tmp_path):
        root = _cache_layout(tmp_path)
        result = _shell_name(root)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == marketplace_name_for(str(root)) == REAL_NAME

    def test_checkout_without_a_manifest(self, tmp_path):
        root = _dev_layout(tmp_path, None)
        result = _shell_name(root)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == marketplace_name_for(str(root)) == CHECKOUT_DIR

    @pytest.mark.parametrize("text", [
        "{not json",
        json.dumps({"description": "no name"}),
        json.dumps({"name": ""}),
        json.dumps({"name": 7}),
        json.dumps({"owner": {"name": "only nested"}, "plugins": [{"name": "p"}]}),
    ], ids=["invalid-json", "no-name", "empty-name", "non-string-name",
            "nested-name-only"])
    def test_malformed_manifest_warns_and_uses_the_directory_name(self, tmp_path, text):
        root = _dev_layout(tmp_path, text)
        with pytest.raises(MarketplaceManifestError):
            marketplace_name_for(str(root))
        result = _shell_name(root)
        assert result.returncode == 1
        assert result.stdout.strip() == CHECKOUT_DIR
        assert "marketplace.json" in result.stderr


class TestHooksUseTheSharedDerivation:
    """Text-level: neither hook may derive the name from the directory again."""

    HOOKS = (
        Path(BOOTSTRAP_ROOT) / "hooks" / "sessionstart" / "session-bootstrap.sh",
        Path(BOOTSTRAP_ROOT) / "hooks" / "userpromptsubmit" / "bootstrap-display.sh",
    )

    @pytest.mark.parametrize("hook", HOOKS, ids=lambda p: p.name)
    def test_hook_sources_the_shared_file_and_calls_it(self, hook):
        text = hook.read_text(encoding="utf-8")
        assert 'hooks/marketplace-name.sh"' in text
        assert 'MARKETPLACE_NAME="$(bootstrap_marketplace_name "$PLUGIN_ROOT"' in text
        assert 'MARKETPLACE_NAME="$(basename' not in text


def _fake_checkout_root(tmp_path: Path, manifest_text: str) -> str:
    """A bootstrap plugin root inside ``<tmp>/checkout-clone/plugins``."""
    checkout = tmp_path / CHECKOUT_DIR
    root = checkout / "plugins" / "bootstrap"
    root.mkdir(parents=True)
    link_tree(root / "bootstrap_lib", os.path.join(BOOTSTRAP_ROOT, "bootstrap_lib"))
    link_tree(root / "engine", os.path.join(BOOTSTRAP_ROOT, "engine"))
    _write_minimal_defaults(root)
    (root / "bootstrap.json").write_text("{}", encoding="utf-8")
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "bootstrap", "version": "9.9.9"}), encoding="utf-8")
    (checkout / ".claude-plugin").mkdir()
    (checkout / ".claude-plugin" / "marketplace.json").write_text(
        manifest_text, encoding="utf-8")
    return str(root)


class TestEngine:
    def test_engine_labels_its_log_with_the_manifest_name(self, tmp_path):
        root = _fake_checkout_root(tmp_path, _manifest())
        data_dir = tmp_path / "data" / REAL_NAME / "bootstrap"
        data_dir.mkdir(parents=True)
        result = run_engine(str(data_dir), plugin_root=root, env=_isolated_env(tmp_path),
                            project_dir=str(tmp_path / "proj"))
        assert result.returncode == 0, result.stderr
        log = (data_dir / "bootstrap.log").read_text(encoding="utf-8")
        assert f"{REAL_NAME}:bootstrap@9.9.9" in log
        assert f"{CHECKOUT_DIR}:" not in log

    def test_engine_fails_loudly_on_a_malformed_manifest(self, tmp_path):
        root = _fake_checkout_root(tmp_path, "{not json")
        data_dir = tmp_path / "data" / CHECKOUT_DIR / "bootstrap"
        data_dir.mkdir(parents=True)
        result = run_engine(str(data_dir), plugin_root=root, env=_isolated_env(tmp_path),
                            project_dir=str(tmp_path / "proj"))
        combined = result.stdout + result.stderr
        assert "marketplace.json" in combined, combined
        assert "MarketplaceManifestError" in combined or "crashed" in combined, combined
