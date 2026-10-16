"""The llm-scripting-kit CLI under a redirected bootstrap data root.

A session that redirects bootstrap's data tree (``CLAUDE_BOOTSTRAP_DATA_ROOT``,
exported by ``scripts/claude_plugin_test.py``) provisions this plugin's dev venv
under that root. The CLI must run against THAT venv: re-exec into it when
started under another interpreter, and exit 2 when it is missing, instead of
running the production venv's installed release. Agent-facing messages must
name the redirected console script for the same reason.

Each test names the revert that turns it red.

The re-exec tests run in-process with ``os.execv`` replaced by a recorder, so
they need no real venv and run the same on every platform. The production venv
is absent in all of them (HOME is isolated by the package conftest), which is
the "works before publication / without a production venv" case.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from llm_scripting_kit import bootstrap_guard, cli, constants, declaration

_SKIP = "_BOOTSTRAP_GUARD_SKIP_REEXEC"
_FLAG = "_BOOTSTRAP_GUARD_VENV_REEXEC"
_ROOT = "CLAUDE_BOOTSTRAP_DATA_ROOT"


class _Execed(Exception):
    """Raised by the recorder in place of replacing the process."""


def _venv_dir(data_root: Path) -> Path:
    return data_root / "plugins-kit" / "llm-scripting-kit" / ".venv"


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
        ``[redirected_py, -m, llm_scripting_kit.cli, <args>]``.

        Shown to fail: delete the ``reexec_under_plugin_venv`` call in
        ``cli.main`` and ``execs`` stays empty (``pytest.raises`` fails)."""
        target = _fake_redirected_interpreter(redirected)
        entry = ["/somewhere/.venv/bin/llm-scripting-kit", "status", "--endpoint", "x"]
        monkeypatch.setattr(sys, "argv", list(entry))

        with pytest.raises(_Execed):
            cli.main()

        assert execs == [
            (
                str(target),
                [str(target), "-m", "llm_scripting_kit.cli", "status", "--endpoint", "x"],
            )
        ]
        # The rewrite is scoped to the guard call; the caller's argv comes back.
        assert sys.argv == entry

    def test_the_argv_rewrite_is_not_the_console_wrapper_path(
        self, redirected, execs, monkeypatch
    ):
        """The replacement interpreter is never handed the console-script
        wrapper as a script to run (an .exe on Windows is not Python source).

        Shown to fail: drop the ``sys.argv = ["-m", ...]`` rewrite in
        ``cli.main`` and the wrapper path appears in the exec'd argv."""
        _fake_redirected_interpreter(redirected)
        wrapper = "/somewhere/.venv/Scripts/llm-scripting-kit.exe"
        monkeypatch.setattr(sys, "argv", [wrapper, "which"])

        with pytest.raises(_Execed):
            cli.main()

        assert wrapper not in execs[0][1]

    def test_an_explicit_argv_is_a_library_call_and_never_reexecs(
        self, redirected, execs, capsys
    ):
        """``main([...])`` stays in the caller's interpreter.

        Shown to fail: call the guard unconditionally in ``cli.main`` (drop the
        ``if argv is None`` condition) and this exec's instead of printing."""
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
        """No redirected interpreter: exit 2, and nothing is exec'd or run.

        Shown to fail: delete the guard call in ``cli.main`` and the command
        runs (``status`` returns 1 or 0) instead of raising SystemExit(2)."""
        monkeypatch.setattr(sys, "argv", ["llm-scripting-kit", "status"])

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

        Pins guard behavior this CLI relies on; the guard copy is vendored
        byte-for-byte, so its own revert evidence lives in
        tests/bootstrap/test_bootstrap_guard.py."""
        monkeypatch.setenv(_SKIP, "1")
        monkeypatch.setattr(sys, "argv", ["llm-scripting-kit", "status"])

        with pytest.raises(SystemExit) as stop:
            cli.main()

        assert stop.value.code == 2


def _run(args: list[str], root: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run a Python child with a redirected, EMPTY data root and isolated HOME.

    The test opt-out is inherited from the package conftest and left in place on
    purpose: a missing redirected venv must still refuse."""
    env = dict(os.environ)
    env[_ROOT] = str(root)
    env.pop(_FLAG, None)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, env=env, check=False
    )


class TestEntryPointsRefuseInASubprocess:
    def test_console_script_shape_exits_2(self, tmp_path):
        """``from llm_scripting_kit.cli import main; sys.exit(main())`` is what
        the setuptools console wrapper runs.

        Shown to fail: delete the guard call in ``cli.main`` and the child
        exits 0 or 1 instead of 2."""
        lib = Path(constants.__file__).resolve().parent.parent
        code = (
            "import sys; sys.path.insert(0, sys.argv.pop(1)); "
            "from llm_scripting_kit.cli import main; sys.exit(main())"
        )
        result = _run(["-c", code, str(lib), "status"], tmp_path / "empty", tmp_path)

        assert result.returncode == 2, result.stderr
        assert "redirected plugin interpreter is missing" in result.stderr

    def test_launcher_script_exits_2_before_importing_the_cli(self, plugin_root, tmp_path):
        """The launcher runs the guard BEFORE ``llm_scripting_kit.cli`` is
        imported: the child poisons that module, so reaching the import is
        exit 1 (ImportError) and the guard is the only way to exit 2.

        Shown to fail: remove the guard block from
        ``scripts/llm_scripting_kit_cli.py`` and the child exits 1."""
        script = Path(plugin_root) / "scripts" / "llm_scripting_kit_cli.py"
        code = (
            "import runpy, sys; sys.modules['llm_scripting_kit.cli'] = None; "
            "script = sys.argv.pop(1); "
            "runpy.run_path(script, run_name='__main__')"
        )
        result = _run(["-c", code, str(script), "status"], tmp_path / "empty", tmp_path)

        assert result.returncode == 2, result.stderr
        assert "redirected plugin interpreter is missing" in result.stderr

    def test_module_entry_exits_2(self, plugin_root, tmp_path):
        """``python -m llm_scripting_kit.cli`` (the form the re-exec itself
        uses) reaches the same refusal.

        Shown to fail: delete the guard call in ``cli.main``."""
        lib = Path(plugin_root) / "lib"
        env_code = "import sys; sys.path.insert(0, sys.argv.pop(1)); import runpy; " \
                   "runpy.run_module('llm_scripting_kit.cli', run_name='__main__')"
        result = _run(["-c", env_code, str(lib), "status"], tmp_path / "empty", tmp_path)

        assert result.returncode == 2, result.stderr


class TestCliCommandIsRedirectAware:
    def test_unredirected_returns_the_human_contract(self, monkeypatch):
        """Shown to fail: make ``cli_command()`` return the redirected form
        unconditionally."""
        monkeypatch.delenv(_ROOT, raising=False)
        assert constants.cli_command() == constants.CLI_COMMAND

    def test_redirected_returns_the_redirect_aware_form(self, monkeypatch, tmp_path):
        """Shown to fail: make ``cli_command()`` ignore the environment."""
        monkeypatch.setenv(_ROOT, str(tmp_path))
        command = constants.cli_command()
        assert command == constants.REDIRECTED_CLI_COMMAND
        assert command.startswith('"${CLAUDE_BOOTSTRAP_DATA_ROOT:-')
        assert "/plugins-kit/llm-scripting-kit/.venv/" in command
        assert "~" not in command
        # Same console-script leaf as the contract, only the base differs.
        leaf = constants.CLI_COMMAND.rsplit(".venv/", 1)[1]
        assert command.endswith(".venv/" + leaf)

    def test_the_record_halt_rule_follows_the_redirect(self, monkeypatch, tmp_path):
        """``declaration`` builds the session rule per call, not at import.

        Shown to fail: render ``_rule`` from the import-time constant and the
        redirected assertion goes red."""
        monkeypatch.delenv(_ROOT, raising=False)
        assert f"{constants.CLI_COMMAND} record-halt <entry>" in declaration.rule_trigger_session()
        monkeypatch.setenv(_ROOT, str(tmp_path))
        assert (
            f"{constants.REDIRECTED_CLI_COMMAND} record-halt <entry>"
            in declaration._rule("session", False)
        )

    def test_the_missing_key_error_follows_the_redirect(self, monkeypatch, tmp_path):
        """``client`` names the redirected console script in its error.

        Shown to fail: switch ``client.py`` back to ``CLI_COMMAND``."""
        from llm_scripting_kit.client import make_openai_client

        monkeypatch.setenv(_ROOT, str(tmp_path))
        monkeypatch.delenv(constants.API_KEY_ENV, raising=False)
        # USER_ENV_FILE is resolved from the real home at import time.
        monkeypatch.setattr("llm_scripting_kit.api_key.USER_ENV_FILE", tmp_path / "none" / ".env")
        with pytest.raises(RuntimeError) as err:
            make_openai_client(project_root=tmp_path)
        assert constants.REDIRECTED_CLI_COMMAND in str(err.value)
