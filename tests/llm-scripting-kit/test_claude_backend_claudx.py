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

import builtins
import json
import os
import sys
import types

import pytest

from bootstrap_lib.claudx import ClaudxPropagationError
from llm_scripting_kit.completion.backends import ClaudeCliBackend, ClaudxSupportError

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


# --- cross-plugin edge: bootstrap_lib.claudx is REFUSE-class -----------------
# Revert-to-red: removing the ``except ImportError`` around the lazy
# ``from bootstrap_lib.claudx import ...`` turns the three tests below red (the
# absent and no-module cases surface a bare ModuleNotFoundError, the
# missing-symbol case a bare ImportError, none of them ClaudxSupportError).


def _hide_bootstrap_lib(monkeypatch):
    # What importing a submodule of a package that is not installed raises:
    # a ModuleNotFoundError whose name is the top-level package.
    monkeypatch.delitem(sys.modules, "bootstrap_lib.claudx", raising=False)
    real = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "bootstrap_lib.claudx":
            raise ModuleNotFoundError("No module named 'bootstrap_lib'", name="bootstrap_lib")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_absent_bootstrap_lib_refuses_with_the_install_message(claudx_session, monkeypatch):
    _hide_bootstrap_lib(monkeypatch)
    runner = _Runner()
    with pytest.raises(ClaudxSupportError) as caught:
        _backend(runner).complete("SYS", "USER", model="opus")
    message = str(caught.value)
    assert "claude plugin install bootstrap@plugins-kit" in message
    assert "0.154.1" in message and "Nothing was" in message
    assert "claude plugin update" not in message
    assert runner.calls == []


def test_a_bootstrap_lib_without_the_claudx_module_refuses_with_the_update_message(
    claudx_session, monkeypatch
):
    monkeypatch.setitem(sys.modules, "bootstrap_lib.claudx", None)
    runner = _Runner()
    with pytest.raises(ClaudxSupportError) as caught:
        _backend(runner).complete("SYS", "USER", model="opus")
    message = str(caught.value)
    assert "claude plugin update bootstrap@plugins-kit" in message
    assert "0.154.1" in message and "no claudx module" in message
    assert "claude plugin install" not in message
    assert runner.calls == []


def test_a_claudx_module_without_the_symbol_refuses_with_the_update_message(
    claudx_session, monkeypatch
):
    monkeypatch.setitem(
        sys.modules, "bootstrap_lib.claudx", types.ModuleType("bootstrap_lib.claudx")
    )
    runner = _Runner()
    with pytest.raises(ClaudxSupportError) as caught:
        _backend(runner).complete("SYS", "USER", model="opus")
    message = str(caught.value)
    assert "claude plugin update bootstrap@plugins-kit" in message
    assert "has no nested_claude_args" in message and "0.154.1" in message
    assert "claude plugin install" not in message
    assert runner.calls == []

