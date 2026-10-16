"""claudx containment escapes, reproduced at pytest level without launching claude.

Each reproduction asserts the CONTAINED behavior and is marked
``xfail(strict=True)``. Today the escape reproduces, so the test is XFAIL and the
suite stays green; when a fix lands the test XPASSes, which strict turns into a
failure that tells the fixer to delete the marker. The open-escape ledger lives in
dev/tasks/claudx-shared-lib-escape; the containment mechanics are in
docs/reference/testing.md ("claudx containment mechanics").

Isolation: every subprocess gets HOME and USERPROFILE pointed into tmp_path, so
nothing here reads or writes the real ``~/.claude``. The "cached bootstrap" is a
fake whose only effect is a marker file; no real bootstrap pass ever runs (the
real ``session-bootstrap.sh`` performs persistent PATH writes and installs, which
a test must never do to its host -- see test_plugin_test_session.py).

Escape 1 -- harvest launches the CACHED engine from the PRODUCTION registry.
    ``harvest.py`` knows nothing of CLAUDE_PLUGIN_TEST or
    CLAUDE_BOOTSTRAP_DATA_ROOT: with no ``engine_ran_version`` stamp in the
    redirected data dir it resolves bootstrap's installPath from
    ``$HOME/.claude/plugins/installed_plugins.json`` and detaches
    ``<installPath>/hooks/sessionstart/session-bootstrap.sh``.
Escape 2 -- the cached script's stand-down is spelling-fragile.
    The only thing that stops that launched engine is a glob on its own
    PLUGIN_ROOT (``*/.claude/plugins/cache/*``). An installPath spelled through
    the target of a ``~/.claude`` link does not match it, so the engine runs.
Escape 3 -- an inherited re-exec loop flag keeps a child on the wrong interpreter.
    ``reexec_under_plugin_venv`` returns on ``_BOOTSTRAP_GUARD_VENV_REEXEC``
    before it looks at ``sys.prefix``, so a child that inherits the flag from
    another plugin's process never moves into the redirected plugin venv.
Escape 4 -- the registry-change relaunch launches the cached engine too.
    ``run_registry_relaunch`` is harvest.py's third trigger. A stored plugin-set
    snapshot that differs from the current one makes it detach the same cached
    ``session-bootstrap.sh``, with no redirect awareness.
Escape 5 -- the harvest default registry is the production registry.
    The hook passes no ``--registry``, so ``harvest.py`` reads
    ``$HOME/.claude/plugins/installed_plugins.json`` however
    CLAUDE_BOOTSTRAP_DATA_ROOT is set.
Escape 6 -- a ``<PLUGIN>_ROOT`` under plugins/cache is accepted in a redirected session.
    Neither ``export_env_var`` nor the pre-gate ``plugin_roots`` record
    (``engine._maintain_env_records``, re-emitted by the hook prelude into later
    gate-skipped sessions) refuses a cache-rooted install path, so a command
    anchored on ``"${<PLUGIN>_ROOT}"`` runs the installed plugin.

Escapes 5 and 6 run in this process with HOME,
USERPROFILE and CLAUDE_BOOTSTRAP_DATA_ROOT monkeypatched into tmp_path, and
subprocess.Popen stubbed, so no process is spawned.
"""
import contextlib
import json
import os
import subprocess
import sys
import time
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO_ROOT / "plugins" / "bootstrap"
HARVEST_PY = BOOTSTRAP / "bootstrap_lib" / "harvest.py"
SESSION_HOOK = BOOTSTRAP / "hooks" / "sessionstart" / "session-bootstrap.sh"
GUARD_PY = BOOTSTRAP / "bootstrap_lib" / "bootstrap_guard.py"

LEDGER = "dev/tasks/claudx-shared-lib-escape"


def _escape(n: int) -> "pytest.MarkDecorator":
    return pytest.mark.xfail(
        strict=True, reason=f"claudx escape {n}: open; see {LEDGER}"
    )


# --------------------------------------------------------------------------
# Escapes 1 and 2: harvest -> cached session-bootstrap.sh
# --------------------------------------------------------------------------

def _stand_down_prelude() -> str:
    """The REAL session-bootstrap.sh text from ``SCRIPT_DIR=`` up to (not
    including) the trap that precedes any side effect, which holds its
    claude-plugin-test stand-down. Reusing the real text means the glob under
    test is the shipped one. Fails loudly if the script is reshaped."""
    text = SESSION_HOOK.read_text(encoding="utf-8")
    start = text.index("SCRIPT_DIR=")
    end = text.index("# Set trap after BOOTSTRAP_LABEL")
    prelude = text[start:end]
    assert '*/.claude/plugins/cache/*) true ;; *) false ;; esac; then' in prelude, (
        "session-bootstrap.sh no longer carries the CLAUDE_PLUGIN_TEST stand-down "
        "before its first side effect; update this fixture"
    )
    return prelude


def _fake_cached_script(with_stand_down: bool) -> str:
    """A stand-in for the cached bootstrap's session-bootstrap.sh. It records that
    it ran (RAN), that it finished (DONE, via an EXIT trap so an early
    ``exit 0`` in the stand-down still reports), and that it got past the
    stand-down and would have run a pass (ESCAPED)."""
    body = [
        "#!/usr/bin/env bash",
        'trap \': > "$CLAUDX_ESCAPE_DONE"\' EXIT',
        ': > "$CLAUDX_ESCAPE_RAN"',
    ]
    if with_stand_down:
        body.append(_stand_down_prelude())
    body.append(': > "$CLAUDX_ESCAPE_ESCAPED"')
    return "\n".join(body) + "\n"


class _Harvest:
    """One harvest run under a claudx-shaped environment, with a fake HOME."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.data_root = tmp_path / "data-dev"
        self.data_dir = self.data_root / "plugins-kit" / "bootstrap"
        self.project = tmp_path / "project"
        self.project.mkdir()
        self.ran = tmp_path / "marker-ran"
        self.done = tmp_path / "marker-done"
        self.escaped = tmp_path / "marker-escaped"

    def install_fake_cached_bootstrap(
        self, install_path: Path, registry: Path, *, with_stand_down: bool
    ) -> None:
        sb = install_path / "hooks" / "sessionstart" / "session-bootstrap.sh"
        sb.parent.mkdir(parents=True)
        # newline="\n": bash must not see CRLF on a Windows host.
        with open(sb, "w", encoding="utf-8", newline="\n") as f:
            f.write(_fake_cached_script(with_stand_down))
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            json.dumps({"version": 2, "plugins": {"bootstrap@plugins-kit": [
                {"version": "9.9.9", "installPath": str(install_path)}
            ]}}),
            encoding="utf-8",
        )

    def run(self) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update({
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "CLAUDE_PLUGIN_TEST": "1",
            "CLAUDE_BOOTSTRAP_DATA_ROOT": str(self.data_root),
            "CLAUDX_ESCAPE_RAN": self.ran.as_posix(),
            "CLAUDX_ESCAPE_DONE": self.done.as_posix(),
            "CLAUDX_ESCAPE_ESCAPED": self.escaped.as_posix(),
        })
        # The argument list the UserPromptSubmit hook passes: no --registry, no
        # --settings, and no engine_ran_version stamp in the redirected data dir.
        return subprocess.run(
            [sys.executable, str(HARVEST_PY),
             "--data-dir", str(self.data_dir),
             "--project-dir", str(self.project),
             "--marketplace", "plugins-kit"],
            capture_output=True, text=True, timeout=60, env=env,
            stdin=subprocess.DEVNULL,
        )

    @property
    def launched(self) -> bool:
        """harvest.py recorded a launch (it writes the stamp before spawning)."""
        return (self.data_dir / "harvest_launched_version").exists()

    def wait_for_launched_child(self, timeout: float = 30.0) -> None:
        """Poll for the detached child's completion marker. Only called when a
        launch happened, so the contained case never waits."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.done.exists():
                return
            time.sleep(0.1)
        stderr = self.data_dir / "harvest.stderr"
        raise AssertionError(
            "harvest launched a cached session-bootstrap.sh but it never "
            f"finished within {timeout}s; harvest.stderr="
            f"{stderr.read_text(errors='replace') if stderr.exists() else '<absent>'}"
        )

    def assert_contained(self) -> None:
        proc = self.run()
        assert proc.returncode == 0, proc.stderr
        if not self.launched:
            return  # contained: nothing was launched, nothing to wait for
        self.wait_for_launched_child()
        assert not self.escaped.exists(), (
            "claudx escape: harvest.py launched the CACHED session-bootstrap.sh "
            "from the production registry inside a CLAUDE_PLUGIN_TEST / "
            "CLAUDE_BOOTSTRAP_DATA_ROOT session, and that engine got past its "
            f"stand-down (ran={self.ran.exists()}, escaped=True, "
            f"harvest_launched_version="
            f"{(self.data_dir / 'harvest_launched_version').read_text().strip()!r})"
        )


@_escape(1)
def test_harvest_does_not_launch_the_cached_engine_in_a_claudx_session(tmp_path):
    """Escape 1. A cached engine that does not stand down (one older than the
    stand-down, or one the stand-down does not recognise) runs a pass against the
    redirected data root, because harvest.py resolves it from the production
    registry. The install path matches the cache glob here on purpose: this is
    the harvest's launch decision, not the stand-down's spelling."""
    h = _Harvest(tmp_path)
    install = h.home / ".claude" / "plugins" / "cache" / "plugins-kit" / "bootstrap" / "9.9.9"
    h.install_fake_cached_bootstrap(
        install, h.home / ".claude" / "plugins" / "installed_plugins.json",
        with_stand_down=False,
    )
    h.assert_contained()


def test_cache_spelled_install_path_is_masked_by_the_stand_down(tmp_path):
    """Control for escape 2, NOT an xfail: with the install path spelled
    ``.../.claude/plugins/cache/...`` the shipped stand-down does stop the launched
    engine. Passing here is what makes the escape-2 failure mean something -- the
    fixture reaches the real stand-down and it works for this spelling."""
    h = _Harvest(tmp_path)
    install = h.home / ".claude" / "plugins" / "cache" / "plugins-kit" / "bootstrap" / "9.9.9"
    h.install_fake_cached_bootstrap(
        install, h.home / ".claude" / "plugins" / "installed_plugins.json",
        with_stand_down=True,
    )
    proc = h.run()
    assert proc.returncode == 0, proc.stderr
    assert h.launched, "control needs harvest to have launched the cached script"
    h.wait_for_launched_child()
    assert h.ran.exists(), "the fake cached script never ran"
    assert not h.escaped.exists(), "the stand-down did not mask a cache-spelled path"


def _make_dir_link(link: Path, target: Path) -> bool:
    """Directory link usable without elevation: a junction on Windows, a symlink
    elsewhere. False when the host refuses."""
    try:
        if os.name == "nt":
            res = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True, text=True, timeout=30,
            )
            return res.returncode == 0 and link.exists()
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


@_escape(2)
def test_stand_down_does_not_depend_on_how_the_cache_path_is_spelled(tmp_path):
    """Escape 2. ``~/.claude`` is a link to a differently named directory (the
    recorded case: ``~/.claude`` -> a settings checkout), and the registry
    records installPath spelled through the TARGET. PLUGIN_ROOT then lacks
    ``/.claude/plugins/cache/``, the stand-down glob misses, and the cached
    engine runs a pass in a claudx session."""
    h = _Harvest(tmp_path)
    target = tmp_path / "claude-settings"
    target.mkdir()
    link = h.home / ".claude"
    if not _make_dir_link(link, target):
        pytest.skip("cannot create a directory junction/symlink on this host")
    try:
        install = target / "plugins" / "cache" / "plugins-kit" / "bootstrap" / "9.9.9"
        h.install_fake_cached_bootstrap(
            install, link / "plugins" / "installed_plugins.json", with_stand_down=True,
        )
        h.assert_contained()
    finally:
        # rmdir removes the junction/symlink itself, never the target's contents.
        if link.is_symlink() or link.exists():
            try:
                os.rmdir(link)
            except OSError:
                link.unlink()


# --------------------------------------------------------------------------
# Escape 3: inherited re-exec loop flag
# --------------------------------------------------------------------------

_LOOP_FLAG = "_BOOTSTRAP_GUARD_VENV_REEXEC"


def _run_guarded_consumer(tmp_path: Path, *, inherit_flag: bool):
    """Run a consumer under an interpreter that is NOT the redirected plugin venv
    and report the sys.prefix it ends up on after reexec_under_plugin_venv."""
    redirected = tmp_path / "data-dev"
    plugin_venv = redirected / "plugins-kit" / "git-kit" / ".venv"
    # A real, empty venv: the re-exec target must be an executable that starts.
    venv.create(plugin_venv, with_pip=False)
    script = tmp_path / "consumer.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(GUARD_PY.parent)!r})\n"
        "from bootstrap_guard import reexec_under_plugin_venv\n"
        "reexec_under_plugin_venv('git-kit')\n"
        "print('PREFIX=' + sys.prefix)\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["CLAUDE_BOOTSTRAP_DATA_ROOT"] = str(redirected)
    env.pop(_LOOP_FLAG, None)
    if inherit_flag:
        env[_LOOP_FLAG] = "1"
    res = subprocess.run(
        [sys.executable, str(script)], env=env,
        capture_output=True, text=True, timeout=60,
    )
    prefix = ""
    for line in res.stdout.splitlines():
        if line.startswith("PREFIX="):
            prefix = line[len("PREFIX="):]
    return res, prefix, plugin_venv


def _on_plugin_venv(prefix: str, plugin_venv: Path) -> bool:
    return bool(prefix) and Path(prefix).resolve() == plugin_venv.resolve()


def test_guard_reexecs_into_the_redirected_venv_without_an_inherited_flag(tmp_path):
    """Control for escape 3, NOT an xfail: with no inherited loop flag the guard
    moves the process into the existing redirected venv. Proves the fixture's
    venv is a valid re-exec target, so the xfail below fails on the flag alone."""
    res, prefix, plugin_venv = _run_guarded_consumer(tmp_path, inherit_flag=False)
    assert res.returncode == 0, res.stderr
    assert _on_plugin_venv(prefix, plugin_venv), (
        f"expected re-exec into {plugin_venv}, ended on prefix {prefix!r}; "
        f"stderr={res.stderr!r}"
    )


@_escape(3)
def test_inherited_loop_flag_does_not_leave_a_child_on_the_wrong_interpreter(tmp_path):
    """Escape 3. The flag is process-tree scoped, so a child of another plugin's
    already re-exec'd process inherits it. Under redirection with the plugin venv
    PRESENT, the guard returns at the flag check before comparing sys.prefix, and
    the child imports shared libs from whatever interpreter launched it. Contained
    means: it re-execs into the redirected venv, or it refuses."""
    res, prefix, plugin_venv = _run_guarded_consumer(tmp_path, inherit_flag=True)
    refused = res.returncode != 0 and not prefix
    assert _on_plugin_venv(prefix, plugin_venv) or refused, (
        f"{_LOOP_FLAG} was inherited, the redirected venv {plugin_venv} exists, and "
        f"the process stayed on sys.prefix={prefix!r} (exit {res.returncode}); "
        "reexec_under_plugin_venv returned on the flag before checking sys.prefix"
    )


# --------------------------------------------------------------------------
# Escape 4: registry-change relaunch (harvest's third trigger)
# --------------------------------------------------------------------------

@_escape(4)
def test_registry_change_relaunch_does_not_launch_the_cached_engine(tmp_path):
    """Escape 4. engine_ran_version equals the installed version, so the version
    trigger stays quiet; a stored plugin-set snapshot that differs from the
    current one arms ``run_registry_relaunch``, which detaches the cached
    ``session-bootstrap.sh`` from the production registry's installPath."""
    from bootstrap_lib.plugins_snapshot import LAUNCHED_STAMP, STATE_STAMP
    from bootstrap_lib.stamps import global_stamp

    h = _Harvest(tmp_path)
    install = h.home / ".claude" / "plugins" / "cache" / "plugins-kit" / "bootstrap" / "9.9.9"
    h.install_fake_cached_bootstrap(
        install, h.home / ".claude" / "plugins" / "installed_plugins.json",
        with_stand_down=False,
    )
    global_stamp(str(h.data_dir), "engine_ran_version").write("9.9.9")
    global_stamp(str(h.data_dir), STATE_STAMP).write("stale-snapshot-hash")
    proc = h.run()
    assert proc.returncode == 0, proc.stderr
    relaunched = global_stamp(str(h.data_dir), LAUNCHED_STAMP).read()
    if relaunched:
        h.wait_for_launched_child()
    assert not relaunched and not h.ran.exists(), (
        "claudx escape: harvest.py's registry-change relaunch launched the CACHED "
        "session-bootstrap.sh from the production registry inside a "
        f"CLAUDE_PLUGIN_TEST / CLAUDE_BOOTSTRAP_DATA_ROOT session (ran={h.ran.exists()})"
    )


# --------------------------------------------------------------------------
# Escapes 5 and 6: in-process, nothing spawned
# --------------------------------------------------------------------------

@pytest.fixture
def redirected(tmp_path, monkeypatch) -> _Harvest:
    """A claudx-shaped environment for THIS process, all under tmp_path."""
    h = _Harvest(tmp_path)
    monkeypatch.setenv("HOME", str(h.home))
    monkeypatch.setenv("USERPROFILE", str(h.home))
    monkeypatch.setenv("CLAUDE_BOOTSTRAP_DATA_ROOT", str(h.data_root))
    monkeypatch.setenv("CLAUDE_PLUGIN_TEST", "1")
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)
    # Prove the sandbox before any code under test runs.
    assert Path(os.path.expanduser("~")) == h.home
    assert Path(os.environ["CLAUDE_BOOTSTRAP_DATA_ROOT"]) == h.data_root
    assert tmp_path in h.home.parents and tmp_path in h.data_root.parents
    return h


@_escape(5)
def test_default_registry_is_not_the_production_registry(redirected):
    """Escape 5. In a redirected session the harvest default must not be the
    registry under HOME/.claude/plugins."""
    from bootstrap_lib import harvest

    production = redirected.home / ".claude" / "plugins" / "installed_plugins.json"
    resolved = Path(harvest._default_registry())
    assert resolved != production, (
        f"claudx escape: a redirected session resolves the production registry {resolved}"
    )


@_escape(5)
def test_main_without_registry_flag_does_not_launch_the_cached_engine(
    redirected, monkeypatch
):
    """Escape 5, end to end through ``main`` with the hook's argument list (no
    ``--registry``). Popen is stubbed, so the launch is observed and not made."""
    from bootstrap_lib import harvest, tool_check

    install = redirected.home / ".claude" / "plugins" / "cache" / "plugins-kit" / "bootstrap" / "9.9.9"
    redirected.install_fake_cached_bootstrap(
        install, redirected.home / ".claude" / "plugins" / "installed_plugins.json",
        with_stand_down=False,
    )
    launched: list = []

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            launched.append([str(a) for a in argv])

    monkeypatch.setattr(harvest.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(tool_check, "resolve_bash", lambda: "bash-stub")
    redirected.data_dir.mkdir(parents=True)
    assert harvest.main([
        "--data-dir", str(redirected.data_dir),
        "--project-dir", str(redirected.project),
        "--marketplace", "plugins-kit",
    ]) == 0
    assert not launched, (
        f"claudx escape: main() read the production registry and launched {launched}"
    )


@_escape(6)
def test_export_refuses_a_plugin_root_under_the_cache(redirected, monkeypatch):
    """Escape 6, the export. A fix may refuse by raising or by returning; either
    leaves the cache path out of the environment."""
    from bootstrap_lib.env_var_check import export_env_var

    cache_root = redirected.home / ".claude" / "plugins" / "cache" / "plugins-kit" / "skills-kit" / "0.83.0"
    cache_root.mkdir(parents=True)
    # Seeded so monkeypatch restores the variable (it undoes nothing for an absent name).
    monkeypatch.setenv("SKILLS_KIT_ROOT", "sentinel-not-a-path")
    with contextlib.suppress(Exception):
        export_env_var("SKILLS_KIT_ROOT", str(cache_root))
    assert os.environ["SKILLS_KIT_ROOT"] != str(cache_root), (
        "claudx escape: a redirected session exported a plugin root under plugins/cache"
    )


@_escape(6)
def test_pre_gate_record_excludes_a_plugin_root_under_the_cache(redirected):
    """Escape 6, the record the hook prelude re-emits into later gate-skipped
    sessions."""
    from bootstrap_lib.engine import _maintain_env_records
    from bootstrap_lib.env_var_check import plugin_roots_record_path, read_env_record
    from bootstrap_lib.plugin_resolve import PluginInfo

    install = redirected.home / ".claude" / "plugins" / "cache" / "plugins-kit" / "skills-kit" / "0.83.0"
    install.mkdir(parents=True)
    (install / "bootstrap.json").write_text("{}", encoding="utf-8")
    plugins = [PluginInfo(name="skills-kit", install_path=str(install),
                          version="0.83.0", marketplace="plugins-kit")]
    redirected.data_dir.mkdir(parents=True)
    with contextlib.suppress(Exception):
        _maintain_env_records(str(redirected.data_dir), plugins, [], [])
    record = read_env_record(plugin_roots_record_path(str(redirected.data_dir)))
    assert record.get("SKILLS_KIT_ROOT") != str(install), (
        "claudx escape: the redirected data root records a plugin root under "
        "plugins/cache, which the hook prelude re-emits into later sessions"
    )
