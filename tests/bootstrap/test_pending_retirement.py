"""A clean background pass retires pending display verdicts that predate it.

Without this, a failure verdict left unconsumed on disk was relayed on the next
prompt after a later pass had already confirmed the fix, so users were prompted
about problems that no longer existed.
"""

import json
import os
import time

import pytest

import bootstrap_lib.engine as engine
from bootstrap_lib import profiles

PENDING = "bootstrap_display.pending"
SIDECAR = "bootstrap_display.wrapper_import.pending"
OLD_VERDICT = json.dumps({"systemMessage": "bootstrap: Setup issues found"})


class _Args:
    background = True
    project_dir = "/proj"


def _quiet_state():
    return profiles.ProfileState(
        status="no_profiles", selected=None, source=None, chain=(),
        available=(), warnings=(), errors=(),
        write_target="/home/u/.claude/bootstrap.local.json",
    )


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_clear_project_cooldown", lambda *a, **k: None)
    monkeypatch.setattr(engine, "_restamp_project_cooldown", lambda *a, **k: None)
    d = tmp_path / "data"
    d.mkdir()
    return d


def _write(path, mtime):
    path.write_text(OLD_VERDICT)
    os.utime(path, (mtime, mtime))


def _emit(data_dir, failures, started_at):
    engine._emit_pass_results(
        all_failures=failures, current_os="windows", display_content="",
        bootstrap_label="bootstrap", data_dir=str(data_dir), args=_Args(),
        recorder=None, profile_state=_quiet_state(),
        plugin_root=str(data_dir / "plugin"), pass_started_at=started_at,
    )


def test_clean_pass_retires_both_channels_written_before_it(data_dir):
    started = time.time()
    _write(data_dir / PENDING, started - 3600)
    _write(data_dir / SIDECAR, started - 3600)

    _emit(data_dir, [], started)

    assert not (data_dir / PENDING).exists()
    assert not (data_dir / SIDECAR).exists()
    log = (data_dir / "bootstrap.log").read_text()
    assert "retired superseded bootstrap_display.pending" in log


def test_clean_pass_keeps_a_verdict_written_while_it_ran(data_dir):
    started = time.time()
    _write(data_dir / PENDING, started + 5)

    _emit(data_dir, [], started)

    assert (data_dir / PENDING).read_text() == OLD_VERDICT
    assert not list(data_dir.glob(".*retire*"))


def test_failing_pass_replaces_rather_than_retires(data_dir):
    started = time.time()
    _write(data_dir / PENDING, started - 3600)
    failure = {"type": "tool_missing", "message": "jq missing",
               "user_msg": "jq missing", "agent_msg": "install jq",
               "plugin": "bootstrap"}

    _emit(data_dir, [failure], started)

    assert "jq missing" in (data_dir / PENDING).read_text()
