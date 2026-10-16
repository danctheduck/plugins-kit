"""bootstrap_lib.claudx: what a nested ``claude`` child of a claudx session gets.

``nested_claude_args`` returns the ``--plugin-dir`` flags for a direct child. It
raises when the child environment differs from the parent's on any of
CLAUDE_PLUGIN_TEST, CLAUDE_BOOTSTRAP_DATA_ROOT or CLAUDE_PLUGIN_TEST_DIRS
(including a DIFFERENT BUT VALID directory list), and derives the flags from the
parent after validating it. Outside claudx it returns no flags.

Revert-to-red: dropping the CLAUDE_PLUGIN_TEST_DIRS comparison from
``nested_claude_args`` turns
``test_a_different_but_valid_directory_list_is_refused`` red; dropping the
``in_claudx`` early return turns ``test_outside_claudx_returns_no_flags`` red.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bootstrap_lib import claudx
from bootstrap_lib.claudx import (
    ClaudxPropagationError,
    contract_command,
    nested_claude_args,
    refuse_supervised,
)

DATA_ROOT = "CLAUDE_BOOTSTRAP_DATA_ROOT"
DIRS = "CLAUDE_PLUGIN_TEST_DIRS"
FLAG = "CLAUDE_PLUGIN_TEST"


def _plugin_dir(base: Path, name: str) -> str:
    directory = base / name
    (directory / ".claude-plugin").mkdir(parents=True)
    (directory / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    return str(directory)


@pytest.fixture
def two_dirs(tmp_path):
    return _plugin_dir(tmp_path, "alpha"), _plugin_dir(tmp_path, "beta")


@pytest.fixture
def other_dirs(tmp_path):
    return _plugin_dir(tmp_path, "gamma"), _plugin_dir(tmp_path, "delta")


def _session(tmp_path, dirs) -> dict:
    return {
        FLAG: "1",
        DATA_ROOT: str(tmp_path / "data"),
        DIRS: os.pathsep.join(dirs),
        "PATH": "unrelated",
    }


def test_outside_claudx_returns_no_flags(tmp_path):
    assert nested_claude_args({}, parent_env={}) == []
    assert nested_claude_args(None, parent_env={"PATH": "x"}) == []
    # Stray redirect variables without the claudx flag do not make a session.
    stray = {DATA_ROOT: str(tmp_path), DIRS: "relative"}
    assert nested_claude_args(stray, parent_env=stray) == []


def test_default_parent_is_the_process_environment(monkeypatch, tmp_path, two_dirs):
    for name, value in _session(tmp_path, two_dirs).items():
        monkeypatch.setenv(name, value)
    assert nested_claude_args() == [
        "--plugin-dir", two_dirs[0], "--plugin-dir", two_dirs[1],
    ]
    monkeypatch.delenv(FLAG)
    monkeypatch.delenv(DATA_ROOT)
    monkeypatch.delenv(DIRS)
    assert nested_claude_args() == []


def test_a_faithful_child_gets_the_parents_directories_in_order(tmp_path, two_dirs):
    parent = _session(tmp_path, two_dirs)
    inheriting = nested_claude_args(None, parent_env=parent)
    explicit = nested_claude_args(dict(parent, EXTRA="1"), parent_env=parent)
    expected = ["--plugin-dir", two_dirs[0], "--plugin-dir", two_dirs[1]]
    assert inheriting == expected
    assert explicit == expected


@pytest.mark.parametrize("name", [FLAG, DATA_ROOT, DIRS])
def test_a_child_that_lost_a_claudx_variable_is_refused(tmp_path, two_dirs, name):
    parent = _session(tmp_path, two_dirs)
    child = {k: v for k, v in parent.items() if k != name}
    with pytest.raises(ClaudxPropagationError, match=name):
        nested_claude_args(child, parent_env=parent)


def test_an_empty_value_counts_as_lost(tmp_path, two_dirs):
    parent = _session(tmp_path, two_dirs)
    with pytest.raises(ClaudxPropagationError, match=DIRS):
        nested_claude_args(dict(parent, **{DIRS: ""}), parent_env=parent)


def test_a_different_data_root_is_refused(tmp_path, two_dirs):
    parent = _session(tmp_path, two_dirs)
    child = dict(parent, **{DATA_ROOT: str(tmp_path / "production-data")})
    with pytest.raises(ClaudxPropagationError, match=DATA_ROOT):
        nested_claude_args(child, parent_env=parent)


def test_a_different_but_valid_directory_list_is_refused(tmp_path, two_dirs, other_dirs):
    """MUTATION: both lists are absolute and hold plugin.json, so validation alone
    passes either. Only the equality check refuses the substituted list."""
    parent = _session(tmp_path, two_dirs)
    substituted = dict(parent, **{DIRS: os.pathsep.join(other_dirs)})
    # The substituted child, taken on its own, is a well-formed claudx session.
    assert nested_claude_args(substituted, parent_env=substituted) == [
        "--plugin-dir", other_dirs[0], "--plugin-dir", other_dirs[1],
    ]
    with pytest.raises(ClaudxPropagationError, match=DIRS):
        nested_claude_args(substituted, parent_env=parent)


def test_a_reordered_list_is_a_different_list(tmp_path, two_dirs):
    parent = _session(tmp_path, two_dirs)
    reordered = dict(parent, **{DIRS: os.pathsep.join(reversed(two_dirs))})
    with pytest.raises(ClaudxPropagationError, match=DIRS):
        nested_claude_args(reordered, parent_env=parent)


def test_a_child_that_claims_claudx_under_a_production_parent_is_refused(tmp_path, two_dirs):
    child = _session(tmp_path, two_dirs)
    with pytest.raises(ClaudxPropagationError, match=FLAG):
        nested_claude_args(child, parent_env={"PATH": "x"})


@pytest.mark.parametrize("missing", [DATA_ROOT, DIRS])
def test_an_unusable_claudx_parent_is_refused(tmp_path, two_dirs, missing):
    parent = {k: v for k, v in _session(tmp_path, two_dirs).items() if k != missing}
    with pytest.raises(ClaudxPropagationError, match=missing):
        nested_claude_args(None, parent_env=parent)


def test_a_relative_directory_is_refused(tmp_path, two_dirs):
    parent = _session(tmp_path, [two_dirs[0], "relative/plugin"])
    with pytest.raises(ClaudxPropagationError, match="absolute"):
        nested_claude_args(None, parent_env=parent)


def test_a_directory_without_a_plugin_manifest_is_refused(tmp_path, two_dirs):
    bare = tmp_path / "bare"
    bare.mkdir()
    parent = _session(tmp_path, [two_dirs[0], str(bare)])
    with pytest.raises(ClaudxPropagationError, match="plugin.json"):
        nested_claude_args(None, parent_env=parent)


def test_an_empty_list_entry_is_refused(tmp_path, two_dirs):
    parent = _session(tmp_path, [two_dirs[0], ""])
    with pytest.raises(ClaudxPropagationError, match="empty entry"):
        nested_claude_args(None, parent_env=parent)


def test_refuse_supervised_raises_only_under_claudx(tmp_path, two_dirs):
    refuse_supervised("claude --bg", parent_env={"PATH": "x"})
    parent = _session(tmp_path, two_dirs)
    with pytest.raises(ClaudxPropagationError, match="claude --bg"):
        refuse_supervised("claude --bg", parent_env=parent)
    with pytest.raises(ClaudxPropagationError, match="claude --bg"):
        refuse_supervised("claude --bg", parent_env={"PATH": "x"}, child_env=parent)


@pytest.mark.parametrize(
    "argv0, expected",
    [
        ("claude", True),
        ("/usr/local/bin/claude", True),
        ("C:\\tools\\Claude.EXE", True),
        ("claude.cmd", True),
        ("claudex", False),
        ("python", False),
    ],
)
def test_is_claude_executable(argv0, expected):
    assert claudx.is_claude_executable(argv0) is expected


def test_contract_command_is_unchanged_outside_claudx():
    command = ("claude", "-p", "go")
    assert contract_command(command, parent_env={"PATH": "x"}) == command


def test_contract_command_inserts_the_flags_after_the_claude_executable(tmp_path, two_dirs):
    parent = _session(tmp_path, two_dirs)
    got = contract_command(("claude", "-p", "go"), None, parent_env=parent)
    assert got == (
        "claude", "--plugin-dir", two_dirs[0], "--plugin-dir", two_dirs[1], "-p", "go",
    )


def test_contract_command_leaves_other_executables_alone(tmp_path, two_dirs):
    parent = _session(tmp_path, two_dirs)
    command = ("python", "check.py", "-p")
    assert contract_command(command, None, parent_env=parent) == command


@pytest.mark.parametrize(
    "argv",
    [
        ("claude", "--version"),
        ("claude", "--help"),
        ("claude", "plugin", "list"),
        ("claude", "agents", "--json"),
        ("claude", "stop", "abc"),
    ],
)
def test_contract_command_leaves_sessionless_invocations_alone(tmp_path, two_dirs, argv):
    parent = _session(tmp_path, two_dirs)
    assert contract_command(argv, None, parent_env=parent) == argv


@pytest.mark.parametrize(
    "argv", [("claude", "--bg", "--", "go"), ("claude", "respawn", "abc")]
)
def test_contract_command_refuses_supervised_invocations_under_claudx(tmp_path, two_dirs, argv):
    parent = _session(tmp_path, two_dirs)
    with pytest.raises(ClaudxPropagationError, match="supervised"):
        contract_command(argv, None, parent_env=parent)
    assert contract_command(argv, parent_env={"PATH": "x"}) == argv


def test_contract_command_refuses_a_child_environment_that_lost_the_variables(tmp_path, two_dirs):
    parent = _session(tmp_path, two_dirs)
    child = {k: v for k, v in parent.items() if k != DIRS}
    with pytest.raises(ClaudxPropagationError, match=DIRS):
        contract_command(("claude", "-p", "go"), child, parent_env=parent)
