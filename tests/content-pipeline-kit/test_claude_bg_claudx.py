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

import pytest

from bootstrap_lib.claudx import ClaudxPropagationError
from content_pipeline.execution.drivers.claude_bg import ClaudeCli

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
