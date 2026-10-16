"""ClaudeCli under a claudx session: supervised sessions are refused.

``claude --bg`` and ``claude respawn`` run under a background supervisor whose
environment and plugin flags are not established, so under claudx
(CLAUDE_PLUGIN_TEST set) both raise ``ClaudxPropagationError`` before the runner
is called. Outside claudx the argv is unchanged, and the calls that start no
session (``--version``, ``agents``, ``stop``, ``rm``) are never refused.

Revert-to-red: removing the ``_refuse_supervised_under_claudx`` call from
``ClaudeCli.launch_bg`` turns ``test_launch_bg_is_refused_under_claudx`` red; from
``ClaudeCli.respawn``, ``test_respawn_is_refused_under_claudx``.
"""

from __future__ import annotations

import builtins
import sys
import types

import pytest

from bootstrap_lib.claudx import ClaudxPropagationError
from content_pipeline.execution.drivers.claude_bg import ClaudeCli, ClaudxSupportError

FLAG = "CLAUDE_PLUGIN_TEST"


class _Runner:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return "", "", 0


@pytest.fixture
def runner():
    return _Runner()


@pytest.fixture
def cli(runner):
    return ClaudeCli(executable="claude", runner=runner)


@pytest.fixture
def production(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


@pytest.fixture
def claudx_session(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


def test_launch_bg_is_unchanged_outside_claudx(production, cli, runner):
    cli.launch_bg("do it", extra_args=["--model", "opus"])
    assert runner.calls[0][0] == ["claude", "--bg", "--model", "opus", "--", "do it"]


def test_respawn_is_unchanged_outside_claudx(production, cli, runner):
    cli.respawn("abc123")
    assert runner.calls[0][0] == ["claude", "respawn", "abc123"]


def test_launch_bg_is_refused_under_claudx(claudx_session, cli, runner):
    with pytest.raises(ClaudxPropagationError, match="claude --bg"):
        cli.launch_bg("do it")
    assert runner.calls == []


def test_respawn_is_refused_under_claudx(claudx_session, cli, runner):
    with pytest.raises(ClaudxPropagationError, match="claude respawn"):
        cli.respawn("abc123")
    assert runner.calls == []


def test_a_caller_environment_naming_claudx_is_refused_too(production, cli, runner):
    with pytest.raises(ClaudxPropagationError):
        cli.launch_bg("do it", env={FLAG: "1"})
    with pytest.raises(ClaudxPropagationError):
        cli.respawn("abc123", env={FLAG: "1"})
    assert runner.calls == []


def test_calls_that_start_no_session_are_not_refused(claudx_session, cli, runner):
    cli.version()
    cli.agents_json()
    cli.stop("abc123")
    cli.rm("abc123")
    assert [call[0][1] for call in runner.calls] == ["--version", "agents", "stop", "rm"]


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


def test_absent_bootstrap_lib_refuses_with_the_install_message(claudx_session, monkeypatch, cli, runner):
    _hide_bootstrap_lib(monkeypatch)
    with pytest.raises(ClaudxSupportError) as caught:
        cli.launch_bg("do it")
    message = str(caught.value)
    assert "claude plugin install bootstrap@plugins-kit" in message
    assert "0.154.1" in message and "Nothing was" in message
    assert "claude plugin update" not in message
    assert runner.calls == []


def test_a_bootstrap_lib_without_the_claudx_module_refuses_with_the_update_message(
    claudx_session, monkeypatch, cli, runner
):
    monkeypatch.setitem(sys.modules, "bootstrap_lib.claudx", None)
    with pytest.raises(ClaudxSupportError) as caught:
        cli.launch_bg("do it")
    message = str(caught.value)
    assert "claude plugin update bootstrap@plugins-kit" in message
    assert "0.154.1" in message and "no claudx module" in message
    assert "claude plugin install" not in message
    assert runner.calls == []


def test_a_claudx_module_without_the_symbol_refuses_with_the_update_message(
    claudx_session, monkeypatch, cli, runner
):
    monkeypatch.setitem(
        sys.modules, "bootstrap_lib.claudx", types.ModuleType("bootstrap_lib.claudx")
    )
    with pytest.raises(ClaudxSupportError) as caught:
        cli.launch_bg("do it")
    message = str(caught.value)
    assert "claude plugin update bootstrap@plugins-kit" in message
    assert "has no refuse_supervised" in message and "0.154.1" in message
    assert "claude plugin install" not in message
    assert runner.calls == []

