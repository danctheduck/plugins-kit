"""job-kit contract commands under a claudx session.

A contract command whose executable is ``claude`` is a nested claude child: under
claudx (CLAUDE_PLUGIN_TEST set) ``run_contract`` inserts the session's
``--plugin-dir`` flags after the executable, refuses ``--bg`` and ``respawn``, and
raises (nothing started) when the claudx variables are unusable. Other commands,
and every command outside claudx, start exactly as written.

Revert-to-red: passing ``contract.command`` to Popen instead of the
``_claudx_contract_command`` result turns
``test_a_claude_contract_command_carries_the_session_plugin_dirs`` red.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from bootstrap_lib.claudx import ClaudxPropagationError
from job_kit import run as run_module
from job_kit.model import Contract

FLAG = "CLAUDE_PLUGIN_TEST"
DATA_ROOT = "CLAUDE_BOOTSTRAP_DATA_ROOT"
DIRS = "CLAUDE_PLUGIN_TEST_DIRS"


class _Popen:
    started: list = []

    def __init__(self, argv, **kwargs):
        type(self).started.append(list(argv))
        self.returncode = 0

    def communicate(self, input=None, timeout=None):
        return "", ""


@pytest.fixture(autouse=True)
def _popen(monkeypatch):
    _Popen.started = []
    monkeypatch.setattr(subprocess, "Popen", _Popen)
    return _Popen


def _plugin_dir(base, name):
    directory = base / name
    (directory / ".claude-plugin").mkdir(parents=True)
    (directory / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    return str(directory)


@pytest.fixture
def plugin_dirs(tmp_path):
    return [_plugin_dir(tmp_path, "alpha"), _plugin_dir(tmp_path, "beta")]


@pytest.fixture
def claudx_session(monkeypatch, tmp_path, plugin_dirs):
    monkeypatch.setenv(FLAG, "1")
    monkeypatch.setenv(DATA_ROOT, str(tmp_path / "data"))
    monkeypatch.setenv(DIRS, os.pathsep.join(plugin_dirs))


@pytest.fixture
def production(monkeypatch):
    for name in (FLAG, DATA_ROOT, DIRS):
        monkeypatch.delenv(name, raising=False)


def _run(command, tmp_path):
    return run_module.run_contract(Contract(command=tuple(command)), directory=tmp_path)


def test_a_claude_command_is_unchanged_outside_claudx(production, tmp_path, _popen):
    _run(["claude", "-p", "check it"], tmp_path)
    assert _popen.started == [["claude", "-p", "check it"]]


def test_a_claude_contract_command_carries_the_session_plugin_dirs(
    claudx_session, plugin_dirs, tmp_path, _popen
):
    acceptance = _run(["claude", "-p", "check it"], tmp_path)
    assert _popen.started == [[
        "claude",
        "--plugin-dir", plugin_dirs[0],
        "--plugin-dir", plugin_dirs[1],
        "-p", "check it",
    ]]
    # The ledger record keeps the contract as the user wrote it.
    assert acceptance.command == ("claude", "-p", "check it")


def test_a_non_claude_command_is_unchanged_under_claudx(claudx_session, tmp_path, _popen):
    _run(["python", "check.py", "-p"], tmp_path)
    assert _popen.started == [["python", "check.py", "-p"]]


def test_a_sessionless_claude_command_is_unchanged_under_claudx(
    claudx_session, tmp_path, _popen
):
    _run(["claude", "--version"], tmp_path)
    assert _popen.started == [["claude", "--version"]]


@pytest.mark.parametrize(
    "command", [["claude", "--bg", "--", "go"], ["claude", "respawn", "abc"]]
)
def test_a_supervised_claude_command_is_refused_under_claudx(
    claudx_session, tmp_path, _popen, command
):
    with pytest.raises(ClaudxPropagationError, match="supervised"):
        _run(command, tmp_path)
    assert _popen.started == []


def test_unusable_claudx_variables_start_nothing(claudx_session, monkeypatch, tmp_path, _popen):
    monkeypatch.delenv(DIRS)
    with pytest.raises(ClaudxPropagationError, match=DIRS):
        _run(["claude", "-p", "check it"], tmp_path)
    assert _popen.started == []


def test_a_contract_environment_with_another_directory_list_is_refused(
    claudx_session, tmp_path, plugin_dirs
):
    other = _plugin_dir(tmp_path, "gamma")
    environment = dict(os.environ, **{DIRS: other})
    with pytest.raises(ClaudxPropagationError, match=DIRS):
        run_module._claudx_contract_command(("claude", "-p", "go"), environment)
    # The same environment without the substitution is accepted.
    assert run_module._claudx_contract_command(("claude", "-p", "go"), dict(os.environ)) == [
        "claude", "--plugin-dir", plugin_dirs[0], "--plugin-dir", plugin_dirs[1], "-p", "go",
    ]
