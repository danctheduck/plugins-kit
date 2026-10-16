"""The job-kit CLI under a redirected bootstrap data root.

A session that redirects bootstrap's data tree (``CLAUDE_BOOTSTRAP_DATA_ROOT``,
exported by ``scripts/claude_plugin_test.py``) provisions this plugin's dev venv
under that root. The venv's ``job-kit`` console script (``job_kit.cli:main``)
must run against THAT venv: re-exec into it when started under another
interpreter, and exit 2 when it is missing, instead of running whatever code the
wrapper's own venv holds. An explicit ``argv`` is a library call and never
re-execs.

The file name is unique across test directories (no ``__init__.py`` files, so
pytest keys modules by basename): ``tests/llm-scripting-kit/test_cli_redirect.py``
is the sibling for that plugin.

Each test names the revert that turns it red. The re-exec tests run in-process
with ``os.execv`` replaced by a recorder, so they need no real venv and behave
the same on every platform.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import bootstrap_guard
from job_kit import cli

_SKIP = "_BOOTSTRAP_GUARD_SKIP_REEXEC"
_FLAG = "_BOOTSTRAP_GUARD_VENV_REEXEC"
_ROOT = "CLAUDE_BOOTSTRAP_DATA_ROOT"
_REPO = Path(__file__).resolve().parents[2]
_LIBS = [
    _REPO / "plugins" / "job-kit" / "lib",
    _REPO / "plugins" / "llm-scripting-kit" / "lib",
    _REPO / "plugins" / "bootstrap",
]


class _Execed(Exception):
    """Raised by the recorder in place of replacing the process."""


def _venv_dir(data_root: Path) -> Path:
    return data_root / "plugins-kit" / "job-kit" / ".venv"


def _fake_redirected_interpreter(data_root: Path) -> Path:
    """An interpreter file where the guard looks for one (never executed)."""
    py = _venv_dir(data_root) / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    return py


@pytest.fixture
def redirected(tmp_path, monkeypatch):
    """A redirected data root, with the test opt-out and loop flag cleared so
    the guard runs for real."""
    root = tmp_path / "data-dev"
    root.mkdir()
    monkeypatch.setenv(_ROOT, str(root))
    monkeypatch.delenv(_SKIP, raising=False)
    monkeypatch.delenv(_FLAG, raising=False)
    return root


@pytest.fixture
def execs(monkeypatch):
    """Record os.execv instead of replacing the test process.

    ``_is_windows`` is pinned False so the Windows spawn-and-wait branch (which
    would run the fake interpreter) is not taken on a Windows runner."""
    calls: list[tuple[str, list[str]]] = []

    def fake_execv(path, argv):
        calls.append((path, list(argv)))
        raise _Execed

    monkeypatch.setattr(bootstrap_guard, "_is_windows", lambda: False)
    monkeypatch.setattr(os, "execv", fake_execv)
    return calls


class TestMainReexecs:
    def test_console_script_entry_runs_the_module_under_the_redirected_venv(
        self, redirected, execs, monkeypatch
    ):
        """argv=None is the console-script path: it execs
        ``[redirected_py, -m, job_kit.cli, <args>]``.

        Shown to fail: delete the ``reexec_under_plugin_venv`` call in
        ``cli.main`` and ``execs`` stays empty (``pytest.raises`` fails)."""
        target = _fake_redirected_interpreter(redirected)
        entry = ["/somewhere/.venv/bin/job-kit", "status", "--store", "x"]
        monkeypatch.setattr(sys, "argv", list(entry))

        with pytest.raises(_Execed):
            cli.main()

        assert execs == [
            (str(target), [str(target), "-m", "job_kit.cli", "status", "--store", "x"])
        ]
        # The rewrite is scoped to the guard call; the caller's argv comes back.
        assert sys.argv == entry

    def test_the_argv_rewrite_is_not_the_console_wrapper_path(
        self, redirected, execs, monkeypatch
    ):
        """The replacement interpreter is never handed the console-script
        wrapper as a script to run (an .exe on Windows is not Python source).

        Shown to fail: drop the ``sys.argv = ["-m", ...]`` rewrite in
        ``cli.main`` and the wrapper path appears in the exec argv."""
        _fake_redirected_interpreter(redirected)
        wrapper = "/somewhere/.venv/Scripts/job-kit.exe"
        monkeypatch.setattr(sys, "argv", [wrapper, "status"])

        with pytest.raises(_Execed):
            cli.main()

        assert wrapper not in execs[0][1]

    def test_an_explicit_argv_is_a_library_call_and_never_reexecs(
        self, redirected, execs, capsys
    ):
        """``main([...])`` stays in the caller's interpreter.

        Shown to fail: call the guard unconditionally in ``cli.main`` (drop the
        ``if argv is None`` condition) and this execs instead of printing."""
        _fake_redirected_interpreter(redirected)

        with pytest.raises(SystemExit) as stop:
            cli.main(["--help"])

        assert stop.value.code == 0
        assert execs == []
        assert "usage" in capsys.readouterr().out.lower()


class TestMainRefusesWithoutTheRedirectedVenv:
    def test_exits_2_naming_the_missing_interpreter(
        self, redirected, execs, monkeypatch, capsys
    ):
        """No redirected interpreter: exit 2, and nothing is run.

        Shown to fail: delete the guard call in ``cli.main`` and ``--help``
        exits 0 with the usage text instead of refusing."""
        monkeypatch.setattr(sys, "argv", ["job-kit", "--help"])

        with pytest.raises(SystemExit) as stop:
            cli.main()

        assert stop.value.code == 2
        err = capsys.readouterr().err
        assert "redirected plugin interpreter is missing" in err
        assert str(_venv_dir(redirected)) in err
        assert execs == []

    def test_the_test_opt_out_does_not_bypass_the_refusal(
        self, redirected, execs, monkeypatch
    ):
        """The skip variable (set by the package conftest) must not turn a
        missing redirected venv into a quiet run of the wrong code.

        Shown to fail: delete the guard call in ``cli.main`` and ``--help``
        exits 0 instead of 2."""
        monkeypatch.setenv(_SKIP, "1")
        monkeypatch.setattr(sys, "argv", ["job-kit", "--help"])

        with pytest.raises(SystemExit) as stop:
            cli.main()

        assert stop.value.code == 2


class TestConsoleScriptShapeInASubprocess:
    def test_exits_2_before_running_the_verb(self, tmp_path):
        """``from job_kit.cli import main; sys.exit(main())`` is what the
        setuptools console wrapper runs. The opt-out stays set, as the package
        conftest leaves it: a missing redirected venv must still refuse.

        Shown to fail: delete the guard call in ``cli.main`` and ``--help``
        prints the usage and the child exits 0."""
        home = tmp_path / "home"
        home.mkdir()
        env = dict(os.environ)
        env[_ROOT] = str(tmp_path / "empty")
        env[_SKIP] = "1"
        env.pop(_FLAG, None)
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env["PYTHONPATH"] = os.pathsep.join(str(p) for p in _LIBS)
        code = "import sys; from job_kit.cli import main; sys.exit(main())"
        result = subprocess.run(
            [sys.executable, "-c", code, "--help"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=120,
        )

        assert result.returncode == 2, (result.returncode, result.stdout[:200], result.stderr[:300])
        assert "redirected plugin interpreter is missing" in result.stderr
