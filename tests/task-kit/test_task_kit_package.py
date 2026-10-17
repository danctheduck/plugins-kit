"""task-kit's packaging for the dashboard: manifests, skill routing, PATH exposure.

These pin the facts that make `task-kit` typed in any terminal reach the
launcher and that `/task dashboard` routes to it without colliding with the
review verb's keywords.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

import pytest
import yaml
from dashboard_support import PLUGIN_ROOT, REPO_ROOT

PLUGIN_JSON = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
BOOTSTRAP = json.loads((PLUGIN_ROOT / "bootstrap.json").read_text(encoding="utf-8"))
PYPROJECT = tomllib.loads((PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
SKILL = (PLUGIN_ROOT / "skills" / "task" / "SKILL.md").read_text(encoding="utf-8")


def skill_capabilities() -> dict[str, dict]:
    blocks = re.findall(r"```yaml\n(.*?)```", SKILL, re.S)
    for block in blocks:
        data = yaml.safe_load(block)
        if isinstance(data, dict) and "capability_skill" in data:
            return {c["id"]: c for c in data["capability_skill"]["capabilities"]}
    raise AssertionError("no capability_skill block in SKILL.md")


# The last version published before the dashboard (the extraction release).
LAST_PUBLISHED = (0, 1, 0)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_versions_agree_and_are_past_the_last_published_version():
    assert PLUGIN_JSON["version"] == PYPROJECT["project"]["version"]
    assert _version(PLUGIN_JSON["version"]) > LAST_PUBLISHED


def test_psutil_is_declared_for_install_and_for_verification():
    assert any(d.startswith("psutil") for d in PYPROJECT["project"]["dependencies"])
    assert "psutil" in BOOTSTRAP["venv"]["check_imports"]


def test_bin_is_synced_to_the_data_directory_that_path_entries_names():
    assert BOOTSTRAP["sync_to_data"] == [{"src": "bin", "dst": "bin"}]
    (entry,) = BOOTSTRAP["path_entries"]
    assert entry == "~/.claude/plugins/data/plugins-kit/task-kit/bin"
    for name in ("task-kit", "task-kit.cmd", "task_kit_entrypoint.py"):
        assert (PLUGIN_ROOT / "bin" / name).is_file()


def test_the_posix_shim_is_executable_in_git():
    import subprocess

    out = subprocess.run(["git", "ls-files", "-s", "plugins/task-kit/bin/task-kit"], cwd=REPO_ROOT,
                         capture_output=True, text=True).stdout
    if out:  # untracked in a pre-commit run is checked once it is staged
        assert out.startswith("100755")


def test_dashboard_routing_owns_the_task_dashboard_keyword_and_review_does_not():
    caps = skill_capabilities()
    assert "task dashboard" in caps["dashboard"]["keywords"]
    assert "/task dashboard" in caps["dashboard"]["keywords"]
    assert "task dashboard" not in caps["review"]["keywords"]
    keyword_owners = [i for i, c in caps.items() if "task dashboard" in c["keywords"]]
    assert keyword_owners == ["dashboard"]
    step = caps["dashboard"]["steps"][0]["action"]
    assert 'bin/task-kit' in step and "CLAUDE_PLUGIN_ROOT" in step


def test_dashboard_is_not_a_task_py_verb():
    cli = (PLUGIN_ROOT / "skills" / "task" / "scripts" / "task.py").read_text(encoding="utf-8")
    assert "dashboard" not in cli.lower()


def test_the_dashboard_adds_no_llm_kit_install_edge():
    """No plugin dependency and no auto/manual install entry for llm-kit. (llm_kit may
    appear in shared_lib_imports for the pre-existing summary-repair import.)"""
    assert not any("llm-kit" in p["ref"] for p in BOOTSTRAP["plugins"])
    assert "llm-kit" not in PLUGIN_JSON["dependencies"]
