# task-kit working sessions: implementation plan

Status: plan only (unit `plan-working-sessions`, 2026-10-21). Target release: task-kit 0.13.0
(dev and master both carry task-kit 0.12.0 on 2026-10-21). Publishing task-kit is
pre-approved for this work: `uv run python scripts/publish.py --only task-kit`.

## Goal

Anyone looking at a task -- through the task CLI or the task-kit dashboard, on any of the user's
machines -- can see that a Claude Code harness session is working it, and a session that died
without saying so is recognised as dead on the machine that ran it.

## Binding rulings (user, 2026-10-21, verbatim)

> a claude code session is currently working on 'beta narrative pipeline' and that is not
> reflected in the task-kit interface. This may be an unimplemented feature, not sure. I think I
> should know if a claude code harness is currently working on a task.

> For example, the harness could register its host and process id and state it is working on the
> task within the task file itself. task-kit could validate that process is still running and the
> hostname matches.

> I don't like any dependency on the dashboard running

> if the data isn't in the task file, wherever it goes still needs to be commited, because we run
> this dashboard on multiple machines

Offered "keep task.yaml untouched; each host commits its own dev/tasks/.sessions/<hostname>.yaml
listing which tasks its live Claude sessions work (no merge conflicts: one writer per file, and
that writer is the only host able to verify its own PIDs)", the user answered:

> oh ok sure

On verification across machines:

> i mentioned including the process so we can verify local machines. For an external machine i
> agree for now that can be unverified. Eventually we will make it so the task-kit service is
> running on all the machines all the time, and then you can ask the other machine if it's valid
> or not, but that's for the future

So: a record carries host, session id, pid and process creation time; the host that wrote it
verifies it; every other host shows it unverified. Nothing is built for cross-machine queries, but
the format and the display states leave room for one (see "Future direction").

## Premise outcomes

| Hypothesis | Outcome | Evidence |
|---|---|---|
| Claude Code offers a SessionEnd hook usable from a plugin | Confirmed by documentation; plugin firing and detached-child survival unmeasured (unit U0 measures them) | https://code.claude.com/docs/en/hooks, "SessionEnd": fires when a session ends; `reason` is `clear`, `resume`, `logout`, `prompt_input_exit` or `other`; no decision control; command hooks supported; input carries `session_id` and `cwd`. Budget: "SessionEnd hooks have a default timeout of 1.5 seconds ... Timeouts set on plugin-provided hooks don't raise the budget" (only `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS`, a user setting, does). Nothing documents firing on a crash, `kill -9` or a closed terminal. Plugins register hooks in `hooks/hooks.json` with no plugin.json field (`plugins/presence-kit/hooks/hooks.json`). |
| `task_hold.py` already resolves the harness's Claude pid and create time reusably | Refuted | `handshake.find_session_process` (`task_system/dashboard/handshake.py:40-58`) returns the first ancestor whose name or first three argv words contain "claude". Measured on Claude Code 2.1.306, macOS, from a Bash tool command: it returned the transient `zsh -c "source ~/.claude/shell-snapshots/..."` shell, not the Claude process (process name `2.1.306`, argv `['claude']`, equal to `CLAUDE_PID`). A hold keyed on that shell dies when the command returns and `RuntimeDB.live_holds` deletes it (`runtime.py:542-556`), which matches the empty holds table while the Afterplay session worked beta-narrative-pipeline. Every hold test passes `session_pid` explicitly (`tests/task-kit/test_dashboard_harness_hold.py:142`), so the walk was never exercised. The session-id fallback reads `CLAUDE_SESSION_ID`, which is unset in a Bash tool environment (only the skill-body substitution supplies it). `proctree.ProcIdent` / `live` (PID plus creation time, 1.0 s tolerance) ARE reusable, but live in the dashboard package, which `task.py` and the rest of `task_system` may not import (`tests/task-kit/test_dashboard_non_interference.py`, check 1). The documented replacement: `CLAUDE_PID` -- "Claude Code sets this to its own process ID in the subprocesses it spawns: Bash and PowerShell tool commands and hook commands ... Requires Claude Code v2.1.214 or later" -- and `CLAUDE_CODE_SESSION_ID`, which "matches the `session_id` field in the hook JSON input and is updated on `/clear`" (https://code.claude.com/docs/en/env-vars). |
| `task.py` has git commit/push helpers a registration can reuse; push failure, offline and concurrent pushes can be handled | Partly confirmed | A commit helper exists: `location_ops._git_commit_folder` (pathspec-limited `add` + `commit -- <folder>`, `location_ops.py:333-380`), with `_git_toplevel` (`:307-330`) and `validate.git_ignores_path`. They are private and archive-worded. task-kit has no fetch, pull or push code anywhere (`dashboard/vcs.py` is read-only; `floor.py` denies push to runs). Push, fetch and integration are added work; the failure handling is designed below ("Git automation"). |
| Hostname is a stable identifier across the user's machines | Confirmed for this host; indirect for the fleet; two hazards designed around | `socket.gethostname()` is `m5pro.local` and `scutil --get HostName` is set explicitly, so it does not follow the network. task_system already uses `resolve.short_hostname()` (`resolve.py:87-89`) as the local host for tmp refs. bootstrap's env.json `machines` registry is keyed by `gethostname()` and hard-errors on an unknown name (`bootstrap_lib/env_manifest.py:141-160`), so drift on any fleet machine would already surface as a bootstrap failure. The registry's short names are distinct ignoring case (christina-mac, m5pro, 5090rtx, 5090w, 5090wsl, 2060s, 2060w, polycade, ricoprime). Hazards: a Mac with no `HostName` set takes its name from the network; a WSL instance defaults to its Windows host's name while having a separate process table. Windows not measured. |
| A `.sessions` directory outside any task folder does not trip validate | Confirmed by code and by measurement | validate's uncommitted check is `git status --porcelain -- <folder>`, pathspec-limited to the task folder (`validate.py:123-146`). Measured in a scratch repo: an untracked `dev/tasks/.sessions/m5pro.yaml` left `validate` clean (exit 0) and `list` unchanged; an untracked file inside the task folder made validate warn (exit 1). Discovery only globs `task.yaml` and `*.md` (`discovery.py:274,313`); the inventory only takes directories holding `task.yaml` (`inventory.py:189-197`); a stub cannot begin with `.` (`init.py:65`). |

## Decisions

1. **Storage: `<task root>/.sessions/<host>.yaml`, one file per host per physical task root.**
   task.yaml is untouched. With `dev/tasks` linked into the tasks repository this lands at
   `<tasks repo>/<project>/.sessions/<host>.yaml`, so the record travels with the tasks' own
   version control, which is the only repository every machine running the dashboard shares.
   `.plugin-data/` in the project root is the wrong home: the project repository can differ from
   the task root's (plugins-kit is public and ignores its `dev/tasks` link), so a record there
   would neither reach the tasks repository nor stay private.
2. **Identity comes from documented variables, never from process names.** Session id:
   `CLAUDE_CODE_SESSION_ID`. Process: `CLAUDE_PID`, accepted only when it names a live ancestor of
   the calling process; its creation time comes from psutil. Host id: `short_hostname()` lowercased,
   with `-wsl` appended under WSL unless the name already ends in `wsl` (so a WSL instance on its
   Windows host's default name can never share, and prune, the Windows file). The file also records
   `os_instance` (`macos`, `linux`, `linux-wsl`, `windows`).
3. **`task.py work` registers, after its validation gate passes.** A skill step depends on the agent
   remembering it, and the handshake's broken PID went unnoticed precisely because nothing
   mechanical exercised it. Registering after the gate means a task that failed validation is never
   shown as worked.
4. **One task per session.** A second `work` in the same session moves the registration (removes
   the session's record from the old root's file, adds it to the target root's file). `/task work` loads one
   task's context; showing a session on every task it ever opened would overstate what it works.
5. **Git publication runs detached, for registration and for session end alike.** SessionEnd gets
   1.5 s and a plugin cannot extend it; an offline `fetch` must not stall `/task work`. The
   foreground step writes the file and the local index (milliseconds) and starts one background
   publisher; it never claims the record was published. Publication state is DERIVED from git when
   shown (uncommitted, committed but not pushed, pushed as of the last fetch), plus the last
   publisher outcome recorded in the data directory.
6. **Git automation never publishes work that is not its own and never rewrites anything.**
   Fast-forward only; pathspec-limited commits; a merge only when every upstream-only commit touches
   nothing but other hosts' session files; a push only when the net diff from upstream to HEAD names
   nothing but this host's session files. No force, rebase, reset, stash, branch switch or retry.
7. **Pruning is done by writers, not readers** (argued against the orchestrator default that any
   local CLI prunes). Register, release, session end and `task sessions prune` drop this host's
   dead records in the same write; the dashboard, a long-lived process on its host, starts a prune
   for its own host's dead records. `task list`, `show`, `status` and `task sessions` (list) stay
   read-only and offline: agents run `list` constantly, and a read that commits and pushes into the
   shared tasks checkout would surprise, slow, and race the writers. A dead record is still SHOWN as
   dead on its own host the moment the process is gone.
8. **Records from other hosts are shown "unverified" with their age; they never hold the dashboard
   and are never pruned by another host.** One writer per file is what makes the scheme
   conflict-free, and only the owning host can tell a crashed session from a live one.
9. **No heartbeat commits.** Each record carries `registered_at`; every display shows its age.
10. **Live local records become dashboard holds.** The scheduler and the authoring controls yield to
    a live record on the same host even when the dashboard started after the session, which the
    HTTP-only hold cannot do. The `/task work` handshake stays (it is gated, so it closes the race
    with a starting run, and it prints the live-run notice) but takes its PID from decision 2.
11. **`sessions.publish` in `~/.claude/task.local.yaml`: `push` (default), `commit`, or `local`.**
    See "Razor" for the scenarios that earn the key.
12. **tmp-root records are local only.** Durability is location: `tmp/` is machine-local by
    definition, so `tmp/.sessions/<host>.yaml` is written and never committed.
13. **Item-level "in flight" is unchanged.** The `inflight-evidence` item (deferred by the user in
    dev/tasks/task-kit-extraction) needs the user's UX review; this feature supplies the evidence it
    asks for (`sessions` on each task row) and leaves that label alone.
14. **Codex and other harnesses are out of scope.** A process without `CLAUDE_CODE_SESSION_ID`
    registers nothing. The record's `harness: claude-code` field leaves room for them.

## File format

`<task root>/.sessions/<host>.yaml`, written atomically (temporary file in the same directory, then
`os.replace`), keys in the order shown, records sorted by `(task, session_id)`, so equal state is
equal bytes and an unchanged set is never rewritten:

```yaml
_schema_version: 1
host: m5pro                 # must equal the file name; a mismatch makes the file invalid
os_instance: macos          # macos | linux | linux-wsl | windows
sessions:
  - session_id: e4a0712e-91f0-4c7f-bdd5-61c7ea094a4a
    harness: claude-code
    pid: 46063
    process_created: 1792613951.174   # psutil create_time, epoch seconds
    task: beta-narrative-pipeline     # stub under this task root
    checkout: Afterplay2              # basename of the project root the session worked from
    registered_at: "2026-10-21T18:04:11Z"
```

- No absolute paths: the file is committed, possibly to a repository more widely readable than the
  machine it describes. `checkout` is a display hint only; records match tasks by physical task
  root plus stub, so plugins-kit, plugins-kit2 and plugins-kit3 (one physical `dev/tasks`) agree.
- An empty set is `sessions: []`; the file is never deleted.
- An unparseable or mis-shaped file is reported by every reader as a `note:` naming the file and
  the reason, and its records are ignored. The owning host refuses to overwrite its own invalid
  file (registration reports it; nothing is clobbered).

Local, uncommitted state lives in the user-scoped data directory
(`${CLAUDE_BOOTSTRAP_DATA_ROOT:-~/.claude/plugins/data}/plugins-kit/task-kit/sessions/`):
`index/<session id>.json` (the physical task roots and stubs the session registered in, which is
how session end finds them without searching), `locks/` (per physical task root for file writes, per
repository for git operations), `publish.log` (append-only publisher log, the detached process's
stderr), and `status/<digest of root>.json` (last publisher outcome per root).

## Verification states

| State | Condition | Shown as |
|---|---|---|
| `live` | record's file host and `os_instance` are this machine's, the PID is running, its creation time is within 1.0 s of the record | `m5pro live (this host, Afterplay2, 2h)` |
| `ended` | this machine's file, but the process is gone or the PID was reused | `m5pro ENDED (process gone, 2h)`; removed at this host's next write |
| `unverified` | another host's file | `5090w unverified (registered 3h ago)` |
| reserved: `confirmed`, `ended-remote` | answered by the owning host's task-kit service | not built (see "Future direction") |

The host check is the user's "the hostname matches": a record is this machine's only when the
file name, the file's `host`, and `os_instance` all match. Ages on another host's records use that
host's clock; skew shows as a slightly wrong age, never as a wrong state.

## Lifecycle

**Register** (`task.py work <ref>`, after the gate). Skipped silently when
`CLAUDE_CODE_SESSION_ID` is unset (not a Claude Code subprocess). Skipped with a
`session: not registered` line inside a dashboard run (`TASK_KIT_AGENT_DEPTH` set): the dashboard
already shows its runs, and a run must not commit. Otherwise: resolve identity (decision 2; a
missing `CLAUDE_PID` reports that Claude Code 2.1.214 or later sets it); take the root lock; read
this host's file; drop this host's `ended` records; drop this session's record anywhere the index
says it registered (decision 4); add the record; write; update the index; start the detached
publisher for each root that changed.

**Release** (`task.py sessions release`): the calling session drops its registration without
ending, then publishes. For a session that finishes with a task but keeps going.

**Session end** (SessionEnd hook, every reason). The hook script exits at once, before starting
Python, when the index directory does not exist. Otherwise a small stdlib-only entry
(`scripts/task_session_end.py`) reads the hook JSON, exits if the index has no entry for its
`session_id`, and only then re-execs into the plugin venv to remove the records and start the
publisher. `/clear` and interactive `/resume` end the old session id while the process lives on;
removing its record is correct, because the session id that follows has worked no task. Stderr from this
hook reaches the user (documented), so a failure is visible at exit.

**Crash** (no SessionEnd). Its own host shows the record `ended` immediately; the next write on
that host for that root (any register, release, end or prune), or the dashboard on that host,
removes it and publishes. Other hosts show `unverified` with a growing age until then.

**Resume.** `claude --resume` starts with no registration (the previous exit cleared it); the
hand-off baton's `/task work` re-registers. Whether to re-register automatically is question Q1.

## Git automation and failure modes

The detached publisher (`task.py sessions publish --task-root <physical root>`, hidden from help)
holds the per-repository lock, runs every git command with `GIT_TERMINAL_PROMPT=0`, stdin closed,
60 s bounds on network commands and 30 s on local ones, and appends one outcome line to
`publish.log`. Sequence:

1. Decide the mode: tmp root, no git work tree, the file ignored by git (`check-ignore --no-index`),
   or `sessions.publish: local` -> local only, stop. No upstream branch -> commit only.
2. `git fetch` the upstream. If HEAD is a strict ancestor of upstream, `git merge --ff-only`.
3. If the file differs from HEAD: `git add -- <file>` (only when untracked), then
   `git commit -q -m "task-kit sessions: <host> <root relative to repo>" -- <file>`. Pathspec
   commits leave any other staged content alone.
4. If HEAD and upstream have diverged and every upstream-only commit touches only other hosts'
   `.sessions/*.yaml` files, `git merge --no-edit -q <upstream>` (cannot conflict: one writer per
   file). Any other divergence: no merge.
5. If HEAD descends from upstream and `git diff --name-only <upstream> HEAD` names only this host's
   session files (any root in the repository), `git push -q <remote> HEAD:<upstream branch>`.
   `commit` mode stops before step 2's fetch and never pushes.

| Situation | What happens | Outcome recorded and shown |
|---|---|---|
| tmp root, not a git repository, file ignored, `local` mode | nothing in git | `local only: <reason>` |
| no upstream | commit | `committed, not pushed: no upstream branch` |
| offline, auth failure, fetch timeout | commit | `committed, not pushed: fetch failed: <git's line>` |
| behind upstream, nothing local | fast-forward, commit, push | `published` |
| fast-forward refused (local edits on incoming paths) | commit | `committed, not pushed: fast-forward refused: <line>` |
| diverged, upstream-only commits are other hosts' session files | merge, push | `published` |
| diverged otherwise | commit | `committed, not pushed: branch diverged; the next integration carries it` |
| unpushed commits outside this host's session files | commit | `committed, not pushed: <n> unpushed paths are not this host's session records` |
| commit fails (`index.lock` held, a commit hook) | stop | `not committed: <line>`; the file on disk is current and the next publish commits it |
| push rejected (another host pushed first) | stop | `committed, not pushed: push rejected: <line>` |
| merge conflict in `.sessions` | `git merge --abort` | `not pushed: conflict in <file> -- two machines share host id <host>` |

Every file is a whole-state snapshot, so any later publish from the same host carries everything
earlier ones missed; that is why no step retries (fail loudly, then converge at the next event).
In the tasks repository the common cases (in step, or behind with nothing local) publish at once.
Other sessions' unpushed task-record commits delay publication until their authors push, which the
user's standing `task_records` authorization has them do in the same turn.

## Contract changes

The prior ruling that the DASHBOARD changes no verb contract still holds: every verb change below
rests on the user's 2026-10-21 rulings, and the dashboard's own prune runs the `sessions prune`
verb rather than writing records itself.

**`work`** (precisely): exit codes, the validation gate and stdout (the initialization block) are
byte-identical. Added, after a passing gate and only inside a Claude Code subprocess: the
registration side effect (a write under `<task root>/.sessions/`, the local index, and one detached
publisher), and stderr lines with the fixed prefix `session:`:

- `session: registered <host> on <task id> (session <first 8>); publishing in the background (log: <data dir>/sessions/publish.log)`
- `session: also working this task: <host> <state> <age> (session <first 8>)`, one per other record
- `session: last publish of <root> failed at <time>: <reason>`, when the last outcome was a failure
- `session: not registered: <reason>`; exit stays 0, because the gate passed and the work may proceed

**`list`**: a task line with records gains a trailing ` [working: <host> <state>[ <age>]; ...]`
after the title, so the first four two-space fields are unchanged. `--format json|yaml` gain a
`sessions` array per task.
**`show`**: one `working: <host> <state> (<checkout>, session <first 8>, since <time>)` line per
record, or `working: -`.
**`status`**: a `sessions:` block in the substrate.
**`sessions`** (the fifteenth verb): `task.py sessions [--scope project|all] [--format text|json]`
lists records with states, plus one publication line per own-host file; `prune` removes this
host's `ended` records and publishes; `release`; `end` (the hook's entry); `publish` (hidden).
**Skill**: the work capability tells the agent to relay any `session:` line in one sentence; a
`sessions` capability routes "who is working on X" and "which sessions are live" to the verb.
**Handshake**: `task_hold.py` takes the PID and session id from decision 2; its contract is
otherwise unchanged. `find_session_process` stays as a shim emitting `DeprecationWarning` for two
minor versions (docs/reference/deprecation-policy.md).

**Dashboard**: each task row carries `sessions` (host, state, age, checkout, short session id) and
draws a badge (live, ended, unverified with age); the task details list them; `held` becomes
"runtime hold OR a live local record", so authoring and the scheduler yield; Queue on a task with
an unverified record shows that record beside the control and does not refuse; the snapshot
revision covers records and their states, so a dying process repaints the page. On refresh, a
root whose own-host file holds `ended` records gets one detached `sessions prune`, not repeated
until that file changes. references/dashboard.md, "What it writes", gains that prune.

## Cross-cutting cases

- **One folder, several checkouts.** Records key on the physical task root (realpath of
  `<project>/dev/tasks`) plus stub; `checkout` is display only. The inventory reads each physical
  root's `.sessions` once, exactly as it assigns each physical task folder once.
- **Several sessions on one host.** One file, many records; the per-root lock serialises
  read-modify-write between processes; the per-repository lock serialises git work, and the two are
  never held together.
- **Git-ignored or non-git roots.** Records are written and verified on this host and shown with
  `local only: <reason>`; nothing is committed. This extends the register entry "task-kit:task
  privileges git as the automated VCS" (plugins/CLAUDE.md), whose posture it follows.
- **Windows.** `CLAUDE_PID` is documented for Bash and PowerShell tool commands. Locks use
  `msvcrt`; host ids are lowercased for case-insensitive filesystems; the hook runs through `bash`
  as the shipped hooks do. Detached spawning uses the procspawn flags the dashboard launcher already
  relies on from a Bash tool command; survival when spawned from a SessionEnd hook at exit is a U0
  measurement. WSL gets its own host id (decision 2).
- **Tests run inside Claude sessions.** pytest inherits `CLAUDE_PID` and `CLAUDE_CODE_SESSION_ID`,
  so any test running `task.py work` would register real sessions and spawn real publishers.
  `tests/task-kit/conftest.py` removes both at import and redirects the data directory; a guard test
  asserts they are absent. Registration tests set them explicitly through a fake-Claude parent.
- **Dashboard runs.** Never register (decision: inside a run, `session: not registered`).

## Razor, write paths, directives (submit gates)

Opinions added:

| Opinion | Verdict |
|---|---|
| Automatic commit, fetch, fast-forward and push of session records | Passes the test, so configurable: `sessions.publish: push` (default) / `commit` / `local`. Scenarios: tasks tracked inside a project repository whose pushes start CI or whose branch is protected (a push per `/task work` is unwanted); a repository readable by people who should not see host and checkout names. |
| One task per session | Fails: `/task work` loads one task's working context. |
| Other hosts' records never hold the dashboard | Fails: the record is shown at the Queue control, so the choice is made per action with the evidence in view; refusing would let a crashed host block a task that only that host can clear. |
| No heartbeat | Fails: the age is always shown. |
| Host identity from the hostname | Not an opinion: an observed fact, with WSL detected. |

Write paths: `<task root>/.sessions/<host>.yaml` is project-durable (task-kit's own durable task
root, reason in decision 1); everything under the plugin data directory's `sessions/` is
user-scoped. Neither derives from a script's location.
Directives: the added skill line (relay `session:` lines) is true, cites no authority, and keeps
the user informed. No worktree text. No cross-plugin import.

## Implementation units

File paths are relative to `plugins/task-kit/skills/task/scripts/` unless they start with
`plugins/`, `tests/` or `docs/`. Each unit runs its own targeted tests
(`uv run --extra dev pytest tests/task-kit/<file> -v`) and shows each listed check failing first.

| Unit | Scope | Owns | Depends on |
|---|---|---|---|
| U0 probe | Measure, with a scratch plugin carrying only a SessionEnd hook (nested `claude -p` with `CLAUDECODE` cleared, plus one interactive run for `/clear`): the hook fires from a plugin `hooks/hooks.json`; reasons for exit, `/clear`, Ctrl-C, terminal close, `kill -TERM`; `CLAUDE_PID` and `CLAUDE_CODE_SESSION_ID` in the hook environment and the JSON `session_id` at `/clear`; a detached child (`start_new_session`) started by the hook outlives Claude Code. macOS first; Windows when a Windows host is reachable (else recorded as unmeasured). | `docs/reference/claude-code-plugin-platform.md` (a "SessionEnd, measured" section) | none |
| U1 identity and neutral helpers | `task_system/harness.py` (identity from the two variables, ancestor check, dashboard-run detection, host id, `os_instance`); move `ProcIdent`/`ident_of`/`live` to `task_system/procident.py`, `procspawn` to `task_system/procspawn.py`, the OS file lock to `task_system/oslock.py`, the data-dir resolver to `task_system/datadir.py`, each re-exported from its dashboard module; handshake on the identity; `find_session_process` shim | those five modules; `task_system/dashboard/{proctree,procspawn,mutation,state,handshake}.py`; `task_hold.py`; `tests/task-kit/{test_task_harness_identity.py,fake_claude.py,conftest.py,test_dashboard_harness_hold.py}` | none |
| U2 store | format, validation, atomic write, root lock, index, verification states, register / move / release / end / prune, reading every host file of a root | `task_system/sessions.py`; `tests/task-kit/test_task_sessions_store.py` | U1 |
| U3 publisher | mode detection, the git sequence, outcome log and status, detached spawn, derived publication state, the `sessions:` config key | `task_system/session_publish.py`; `tests/task-kit/{test_task_sessions_publish.py,git_remote_support.py}` | U1 (U2 only by the file path) |
| U4 CLI | `work` registration and `session:` lines (in `_cmd_work`, after `state_ops.work` returns; `state_ops` untouched); `sessions` verb; `list`/`show`/`status` display; docstring; skill text | `task.py`; `task_system/listing.py`; `plugins/task-kit/skills/task/SKILL.md`; `tests/task-kit/test_task_sessions_cli.py` and any task-kit test asserting list/show/status/work text | U2, U3 |
| U5 SessionEnd hook | `hooks.json`, the bash 3.2/zsh-safe script (forced interpreter chain as in `plugins/presence-kit/hooks/stop/presence-stop.sh`; `task.py` re-execs into the venv), the stdlib-only fast entry | `plugins/task-kit/hooks/hooks.json`; `plugins/task-kit/hooks/sessionend/session-end.sh`; `task_session_end.py`; `tests/task-kit/test_task_session_end_hook.py`; the allowlist entry in `tests/repo-scripts/test_python_invocation_standard.py` | U2, U3; U0's result |
| U6 dashboard | inventory read of `.sessions` per physical root, task-row `sessions`, revision, `held` union, Queue note, prune trigger, page badge and details | `task_system/dashboard/{inventory,snapshot,scheduler,server}.py`; `task_system/dashboard/static/{app.js,app.css}`; `plugins/task-kit/skills/task/references/dashboard.md`; `tests/task-kit/{test_dashboard_sessions.py,test_dashboard_inventory.py,test_dashboard_ui_contract.py,ui_harness.js}` | U2, U3 |
| U7 docs and release | register entry extended (plugins/CLAUDE.md, task-kit git privilege); README; design doc section; version 0.13.0 in plugin.json and pyproject.toml; review; claudx smoke; publish | `plugins/CLAUDE.md`; `plugins/task-kit/{README.md,.claude-plugin/plugin.json,pyproject.toml}`; `plugins/task-kit/skills/task/design/task-system-design.md` | all |

Order: U0 and U1 in parallel; then U2 and U3 in parallel; then U4, U5 and U6 in parallel; U7 last.
U2 and U3 meet at one fixed interface: the file path `<task root>/.sessions/<host id>.yaml`, the
data directory layout above, and `session_publish.spawn_publish(task_root, data_dir)`.

## Tests (each shown to fail by the stated revert)

1. Identity: a fake-Claude parent sets `CLAUDE_PID` to itself and runs a child through
   `bash -c` with `.claude/shell-snapshots` in its argv. The resolver returns the fake Claude;
   reverting the handshake to `find_session_process` returns the shell (red).
2. Identity refusals: `CLAUDE_PID` naming a non-ancestor, and `CLAUDE_PID` unset with
   `CLAUDE_CODE_SESSION_ID` set, each refuse with their message.
3. Store: byte-identical rewrite of an unchanged set; move between tasks and roots; release; end
   by session id; an invalid own file is not overwritten (revert: write unconditionally -> red);
   a host mismatch inside a file is reported.
4. States: live (sleeper), ended (killed sleeper), PID reused (creation time differs), another
   host -> unverified; the WSL host-id rule with a faked kernel release. Revert the creation-time
   comparison -> the reused-PID case reads live (red).
5. Publisher, against a bare remote and two clones: in-step publish; behind then fast-forward;
   an unpushed foreign commit is not pushed (revert the net-diff guard -> the foreign commit
   reaches the remote, red); upstream-only session commits are merged and pushed; other upstream
   commits are not merged and the tree is untouched; ignored, non-git and tmp roots create no
   commit (reflog unchanged); pre-staged unrelated content survives the commit; an unreachable
   remote yields `committed, not pushed`.
6. `work`: stdout byte-identical with and without registration; `session:` lines; no registration
   without `CLAUDE_CODE_SESSION_ID` or under `TASK_KIT_AGENT_DEPTH`; a registration failure keeps
   exit 0; the "also working" line.
7. Read verbs never write: `list`, `show`, `status`, `sessions` leave the tree and the data
   directory byte-identical with an `ended` record present (revert: prune on read -> red).
8. Hook: the no-index path exits without importing yaml or psutil (asserted on `sys.modules`
   in-process, never by timing); `end` clears exactly the ending session; the publisher is
   detached with stderr to the log; `hooks.json` shape; the script under bash 3.2 rules.
9. validate, list and the inventory ignore a dirty `.sessions` sibling (control: the same file
   inside the task folder trips validate).
10. Dashboard: one read per physical root across three checkouts; `held` from a live local record
    with no HTTP hold (revert the union -> the scheduler starts a run, red); revision changes when
    the process dies; prune started once per file state; other hosts' files never written.
11. Non-interference: the import-graph check covers the added modules; the conftest guard asserts
    `CLAUDE_PID` and `CLAUDE_CODE_SESSION_ID` are absent (revert the removal -> red).

## Release (U7)

Run the targeted files above, then the task-kit directory serially; `git-kit:git-code-review` over
the range; `claudx --all` smoke in a scratch project whose `dev/tasks` is a clone of a scratch bare
remote (`/task work`, confirm the record and its push, exit, confirm removal and push); then
`uv run python scripts/publish.py --only task-kit`, and confirm on this machine that a real
`/task work` in Afterplay produces a pushed record in the tasks repository. `requires_bootstrap`
stays 0.138.0 (no bootstrap call shape changes).

## Future direction (not built)

When a task-kit service runs on every machine, a reader can ask the owning host to verify a record
by `(session_id, pid, process_created)` and show `confirmed` or `ended-remote` instead of
`unverified`; the owning service could also prune on request. The record already carries every
field such a query needs, the host id is the natural address key (env.json's `machines` registry
holds each machine's tailscale name), and the two state names are reserved above.

## Questions for the user

- **Q1.** On `claude --resume` of a session that had registered, should task-kit re-register it
  automatically at session start (one commit and push when the session starts), or rely on the
  hand-off baton's `/task work`? Default if unanswered: rely on `/task work`, so session start
  stays write-free.
