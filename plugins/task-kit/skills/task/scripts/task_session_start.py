"""task_session_start.py -- the SessionStart hook entry (matchers ``resume`` and ``clear``).

``hooks/sessionstart/session-start.sh`` pipes the hook input (JSON) to this script after its fast path
confirmed this machine holds a registration the event can affect. The input's ``source`` selects the work:

* ``resume`` -- the session id is kept and the process is new: ``sessions.refresh`` gives every record of this
  machine carrying that id the new process stamp and the transcript path.
* ``clear`` -- the session id changes and the process stays: ``sessions.rekey_after_clear`` moves every record of
  the calling process (and its index entry) to the new id.
* anything else (``fork``, ``startup``, ``compact``) does nothing: a fork has a fresh id and registers through
  ``/task work``.

Changed session files are then published, one publication per repository, through ``session_publish``.

The hook never fails the session: :func:`main` returns 0 on every path and records an error in
``<data dir>/sessions/session-start-hook.log`` (stderr when the data directory cannot be resolved). The library
is imported inside :func:`run`, after the venv re-exec in :func:`main`, as ``task.py`` orders it.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

LOG_NAME = "session-start-hook.log"
SOURCE_RESUME = "resume"
SOURCE_CLEAR = "clear"


class HookInputError(ValueError):
    """The hook input is not the JSON object this hook needs."""


def parse_input(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HookInputError(f"the hook input is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HookInputError("the hook input is not a JSON object")
    return data


def log_line(data_dir: Path | None, text: str) -> None:
    """Append one timestamped line to the hook log; to stderr when there is no data directory."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{stamp} session-start: {text}"
    if data_dir is not None:
        try:
            path = Path(data_dir) / "sessions" / LOG_NAME
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            return
        except OSError as exc:
            line += f" (the log {data_dir} is unwritable: {exc})"
    print(line, file=sys.stderr)


def publish_changed(changed, machine, data_dir: Path | None, log: Callable[[str], None]) -> None:
    """Publish the repositories whose session files changed: once per repository, durable roots only."""
    from task_system import session_publish

    seen: set[Path] = set()
    for file in changed:
        root = Path(file).parent.parent  # <task root>/.sessions/<host>.yaml
        flight = session_publish.preflight(root, machine=machine)
        if not flight.ok:
            log(f"not published for {root}: {flight.reason}")
            continue
        if flight.kind != session_publish.KIND_DURABLE or flight.repo_root is None:
            continue  # a tmp root is machine-local: nothing to publish
        if flight.repo_root in seen:
            continue
        seen.add(flight.repo_root)
        result = session_publish.publish(flight.repo_root, machine, data_dir=data_dir)
        log(f"published {flight.repo_root}: {result.status}: {result.message}")


def run(raw: str, env: Mapping[str, str] | None = None, *, data_dir: Path | None = None, machine=None,
        identity=None, publish: Callable[..., None] | None = None, log: Callable[[str], None] | None = None) -> str:
    """Do the work for one hook input and return a one-line outcome. Raises on any failure (see :func:`main`).

    ``data_dir``, ``machine``, ``identity``, ``publish`` and ``log`` default to the real ones; tests inject them.
    """
    from task_system import datadir, harness, machine as machine_module, sessions

    env = os.environ if env is None else env
    data = parse_input(raw)
    source = data.get("source")
    if source not in (SOURCE_RESUME, SOURCE_CLEAR):
        return f"ignored source {source!r}"
    if harness.in_dashboard_run(env):
        return "ignored: this is a dashboard run"
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise HookInputError("the hook input carries no session_id")
    if data_dir is None:
        data_dir = datadir.resolve_data_dir()
    if log is None:
        def log(text: str) -> None:
            log_line(data_dir, text)
    if machine is None:
        machine = machine_module.current()
    if identity is None:
        identity = harness.resolve_identity({**env, harness.SESSION_ID_ENV: session_id})
    transcript = data.get("transcript_path")
    recorded = sessions.to_home_relative(transcript) if isinstance(transcript, str) and transcript else None
    if source == SOURCE_RESUME:
        result = sessions.refresh(identity, machine, recorded, data_dir=data_dir)
        outcome = f"resume {session_id[:8]}: refreshed {len(result.refreshed)}, dropped {len(result.dropped)}"
    else:
        result = sessions.rekey_after_clear(identity, machine, recorded, data_dir=data_dir)
        outcome = (f"clear {session_id[:8]}: re-keyed {len(result.rekeyed)} from "
                   f"{', '.join(i[:8] for i in result.previous_ids) or 'no previous session'}, "
                   f"dropped {len(result.dropped)}")
    for note in result.notes:
        log(f"note: {note}")
    if result.changed_files:
        (publish or publish_changed)(result.changed_files, machine, data_dir, log)
    return outcome


def main() -> int:
    """Re-exec under the task-kit venv, run, and exit 0 whatever happens (the hook never fails the session)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    data_dir = None
    try:
        from bootstrap_guard import reexec_under_plugin_venv

        reexec_under_plugin_venv("task-kit")
        from task_system import datadir

        data_dir = datadir.resolve_data_dir()
        log_line(data_dir, run(sys.stdin.read(), data_dir=data_dir))
    except SystemExit as exc:
        if exc.code not in (0, None):
            log_line(data_dir, f"stopped with exit code {exc.code}")
    except BaseException:  # noqa: BLE001 -- the hook must not fail the session; the traceback is the log
        log_line(data_dir, "failed:\n" + traceback.format_exc().rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
