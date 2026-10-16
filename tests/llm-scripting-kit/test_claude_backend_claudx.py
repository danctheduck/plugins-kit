"""ClaudeCliBackend under a claudx session: the ``claude -p`` child is a claudx child.

The backend hands its runner no environment, so the child inherits this
process's. Under claudx (CLAUDE_PLUGIN_TEST set) the argv therefore carries the
session's ``--plugin-dir`` pairs, right after the executable; when the claudx
variables are unusable the call raises before the runner is invoked. Outside
claudx the argv is unchanged.

Revert-to-red: removing ``*_claudx_plugin_args()`` from the argv in
``ClaudeCliBackend.complete`` turns
``test_the_argv_carries_the_session_plugin_dirs_under_claudx`` red.
"""

from __future__ import annotations

import json
import os

import pytest

from bootstrap_lib.claudx import ClaudxPropagationError
from llm_scripting_kit.completion.backends import ClaudeCliBackend

FLAG = "CLAUDE_PLUGIN_TEST"
DATA_ROOT = "CLAUDE_BOOTSTRAP_DATA_ROOT"
DIRS = "CLAUDE_PLUGIN_TEST_DIRS"


class _Runner:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, request, cwd, *, log_prefix, timeout_s):
        self.calls.append(list(cmd))
        return json.dumps({"result": "ok", "is_error": False}), "", 0


def _plugin_dir(base, name):
    directory = base / name
    (directory / ".claude-plugin").mkdir(parents=True)
    (directory / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    return str(directory)


def _backend(runner):
    return ClaudeCliBackend(runner=runner, executable="claude")


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


def test_the_argv_is_unchanged_outside_claudx(production):
    runner = _Runner()
    _backend(runner).complete("SYS", "USER", model="opus")
    cmd = runner.calls[0]
    assert cmd[0] == "claude" and cmd[1] == "-p"
    assert "--plugin-dir" not in cmd


def test_the_argv_carries_the_session_plugin_dirs_under_claudx(claudx_session, plugin_dirs):
    runner = _Runner()
    _backend(runner).complete("SYS", "USER", model="opus")
    cmd = runner.calls[0]
    assert cmd[:6] == [
        "claude",
        "--plugin-dir", plugin_dirs[0],
        "--plugin-dir", plugin_dirs[1],
        "-p",
    ]
    # The rest of the argv is the ordinary one.
    assert cmd[cmd.index("--model") + 1] == "opus"


@pytest.mark.parametrize("lost", [DIRS, DATA_ROOT])
def test_lost_claudx_variables_raise_before_the_runner_is_called(
    claudx_session, monkeypatch, lost
):
    monkeypatch.delenv(lost)
    runner = _Runner()
    with pytest.raises(ClaudxPropagationError, match=lost):
        _backend(runner).complete("SYS", "USER", model="opus")
    assert runner.calls == []


def test_an_invalid_directory_list_raises_before_the_runner_is_called(
    claudx_session, monkeypatch, tmp_path
):
    monkeypatch.setenv(DIRS, str(tmp_path / "no-such-plugin"))
    runner = _Runner()
    with pytest.raises(ClaudxPropagationError, match="plugin.json"):
        _backend(runner).complete("SYS", "USER", model="opus")
    assert runner.calls == []
