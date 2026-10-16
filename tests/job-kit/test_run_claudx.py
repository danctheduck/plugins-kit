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

import builtins
import os
import subprocess
import sys
import types

import pytest

from bootstrap_lib.claudx import ClaudxPropagationError
from job_kit import run as run_module
from job_kit.model import Contract
from job_kit.run import ClaudxSupportError

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


def test_absent_bootstrap_lib_refuses_with_the_install_message(claudx_session, monkeypatch, tmp_path, _popen):
    _hide_bootstrap_lib(monkeypatch)
    with pytest.raises(ClaudxSupportError) as caught:
        _run(["claude", "-p", "check it"], tmp_path)
    message = str(caught.value)
    assert "claude plugin install bootstrap@plugins-kit" in message
    assert "0.154.1" in message and "Nothing was" in message
    assert "claude plugin update" not in message
    assert _popen.started == []


def test_a_bootstrap_lib_without_the_claudx_module_refuses_with_the_update_message(
    claudx_session, monkeypatch, tmp_path, _popen
):
    monkeypatch.setitem(sys.modules, "bootstrap_lib.claudx", None)
    with pytest.raises(ClaudxSupportError) as caught:
        _run(["claude", "-p", "check it"], tmp_path)
    message = str(caught.value)
    assert "claude plugin update bootstrap@plugins-kit" in message
    assert "0.154.1" in message and "no claudx module" in message
    assert "claude plugin install" not in message
    assert _popen.started == []


def test_a_claudx_module_without_the_symbol_refuses_with_the_update_message(
    claudx_session, monkeypatch, tmp_path, _popen
):
    monkeypatch.setitem(
        sys.modules, "bootstrap_lib.claudx", types.ModuleType("bootstrap_lib.claudx")
    )
    with pytest.raises(ClaudxSupportError) as caught:
        _run(["claude", "-p", "check it"], tmp_path)
    message = str(caught.value)
    assert "claude plugin update bootstrap@plugins-kit" in message
    assert "has no contract_command" in message and "0.154.1" in message
    assert "claude plugin install" not in message
    assert _popen.started == []

