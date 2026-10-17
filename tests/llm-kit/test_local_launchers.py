"""The local-model launch scripts of llm-kit, run under bash against fake binaries.

``plugins/llm-kit/scripts/{model-server.sh, qwen-switch.sh, frontdoor.sh}`` and the
``bin/{qwen36-server, qwen38-server, qwen38l-server, qwen-switch}`` adapters are
carried over from llm-scripting-kit. Every test runs the REAL script. The model
servers are stubs that record their argv, the llm-kit CLI is a stub sibling
``bin/llm-kit`` that records its argv, and ``lsof``, ``ps`` and ``curl`` are stubs on
a temporary PATH; nothing starts a real model server, signals a real process or
reads the real HOME.

What is pinned:

* each profile's measured GPU argv, byte for byte, and every environment override
  (``NINFER_ROOT`` and the artifact, binary, model, host, port, context,
  concurrency and draft-token names);
* the launch guard's fail-open matrix: exit 3 alone blocks the launch; exit 0, 1, 2,
  5 and 127, an uncaught traceback, and a missing or non-executable launcher all
  proceed with exactly one warning line;
* ``LLM_SCRIPTING_KIT_LAUNCH_GUARD=off`` (the legacy spelling, kept because
  environment names are public) skips the guard, and no llm-kit spelling exists;
* ``qwen-switch start`` frees the port through the plugin-relative sibling
  ``bin/llm-kit`` by path (never PATH) and aborts without launching on a non-zero
  exit;
* parity with the frozen legacy scripts run the same way. The documented CLI
  differences are: the guard and terminate calls reach ``bin/llm-kit local swapper
  ...`` where the legacy scripts reached ``swapper ...``; the guard is reached
  through the sibling shim where legacy named an interpreter plus a script
  (``LLM_SCRIPTING_KIT_PYTHON`` and ``LLM_SCRIPTING_KIT_CLI`` have no counterpart);
  ``qwen-switch`` logs under the llm-kit data directory; ``frontdoor.sh`` runs
  ``bin/llm-kit frontdoor``.

Each class names the edit that turns its checks red.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_launchers import BASH

REPO = Path(__file__).resolve().parents[2]
NEW = REPO / "plugins" / "llm-kit"
LEGACY = REPO / "plugins" / "llm-scripting-kit"

pytestmark = pytest.mark.skipif(BASH is None, reason="needs a bash (Git Bash on Windows)")

_SCRUB_PREFIXES = ("QWEN36_", "QWEN38_", "QWEN38L_", "QWEN_SWITCH_", "NINFER_", "LLAMA_", "LLM_SCRIPTING_KIT_",
                   "LLM_KIT_", "CLAUDE_PLUGIN_TEST", "CLAUDE_BOOTSTRAP_DATA_ROOT", "BOOTSTRAP_PYTHON")
_ADAPTERS = ("qwen36-server", "qwen38-server", "qwen38l-server", "qwen-switch")
_PROFILES = ("qwen36", "qwen38", "qwen38l")


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------

def _posix(path: Path) -> str:
    return path.as_posix()


def _norm(text: str) -> str:
    """One spelling for a path argv element.

    Git Bash rewrites a Windows temp path into /tmp/... when it crosses into an msys
    process, so a path under pytest's temp root is reduced to the part from
    ``pytest-of-`` onward, which every spelling shares.
    """
    text = re.sub(r"/+", "/", text.replace("\\", "/"))
    marker = text.find("pytest-of-")
    if marker >= 0:
        return text[marker:]
    return re.sub(r"^/([a-zA-Z])/", lambda m: m.group(1).upper() + ":/", text)


def _write_exec(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def _base_env(home: Path, extra: dict[str, str] | None = None, path_prefix: Path | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(_SCRUB_PREFIXES)}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    if path_prefix is not None:
        env["PATH"] = str(path_prefix) + os.pathsep + env.get("PATH", "")
    if extra:
        env.update(extra)
    return env


def _run(script: Path, args: tuple[str, ...], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([BASH, str(script), *args], text=True, capture_output=True, check=False, env=env,
                          timeout=120, encoding="utf-8", errors="replace")


class Plugin:
    """A throwaway plugin-shaped tree: real scripts and adapters, a stub sibling CLI."""

    def __init__(self, tmp: Path, source: Path, cli_name: str, name: str = "plugin") -> None:
        self.root = tmp / name
        self.source = source
        self.cli_name = cli_name
        self.log = tmp / f"{name}-{cli_name}.calls"
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(parents=True)
        for script in ("model-server.sh", "qwen-switch.sh", "frontdoor.sh"):
            if (source / "scripts" / script).exists():
                shutil.copy2(source / "scripts" / script, self.scripts / script)
        (self.root / "bin").mkdir()
        for adapter in _ADAPTERS:
            shutil.copy2(source / "bin" / adapter, self.root / "bin" / adapter)

    def stub_cli(self, guard_exit: int = 0, terminate_exit: int = 0, stderr: str = "", frontdoor_exit: int = 0) -> Path:
        """Stand-in for the sibling CLI: logs ``$*`` and exits by verb."""
        lines = ["#!/bin/sh", f"printf '%s\\n' \"$*\" >> '{_posix(self.log)}'"]
        if stderr:
            lines.append(f"printf '%s' '{stderr}' >&2")
        lines += [
            'case "$*" in',
            f"  *guard-launch*) exit {guard_exit} ;;",
            f"  *terminate-listener*) exit {terminate_exit} ;;",
            f"  *frontdoor*) exit {frontdoor_exit} ;;",
            "esac",
            "exit 0",
        ]
        return _write_exec(self.root / "bin" / self.cli_name, "\n".join(lines) + "\n")

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def script(self, name: str) -> Path:
        return self.scripts / name

    def bin(self, name: str) -> Path:
        return self.root / "bin" / name


class Fakes:
    """Fake model servers that record ``$$``, ``$LD_LIBRARY_PATH`` and argv."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.record = tmp / "server.record"
        self.ninfer = _write_exec(tmp / "fakes" / "ninfer-serve", self._body())
        self.llama = _write_exec(tmp / "fakes" / "llama" / "bin" / "llama-server", self._body())
        self.artifact = tmp / "fakes" / "model.ninfer"
        self.gguf = tmp / "fakes" / "model.gguf"
        self.artifact.touch()
        self.gguf.touch()
        self.llama_prefix = tmp / "fakes" / "llama"

    def _body(self) -> str:
        return ("#!/bin/sh\n"
                f"{{ echo \"$$\"; echo \"$LD_LIBRARY_PATH\"; for a in \"$@\"; do printf '%s\\n' \"$a\"; done; }}"
                f" > '{_posix(self.record)}'\n")

    def env(self) -> dict[str, str]:
        return {
            "NINFER_SERVE": str(self.ninfer),
            "QWEN36_ARTIFACT": str(self.artifact),
            "QWEN38_ARTIFACT": str(self.artifact),
            "LLAMA_CPP_PREFIX": str(self.llama_prefix),
            "QWEN38_GGUF": str(self.gguf),
        }

    def recorded(self) -> tuple[str, str, list[str]]:
        lines = self.record.read_text(encoding="utf-8").splitlines()
        return lines[0], lines[1], [_norm(line) for line in lines[2:]]


def _argv(profile: str, fakes: Fakes, **overrides: str) -> list[str]:
    """The exact argv a profile builds for a default environment, with overrides applied."""
    o = overrides
    if profile == "qwen36":
        return [
            _norm(str(fakes.artifact)), "--host", o.get("host", "127.0.0.1"), "--port", o.get("port", "8080"),
            "--model-id", "qwen3.6-35b-a3b", "--max-context", o.get("ctx", "262144"), "--kv-capacity", "auto",
            "--max-concurrency", o.get("conc", "1"), "--prefill-chunk", "1024", "--kv-dtype", "int8",
            "--spec", "mtp", "--draft-tokens", o.get("draft", "3"), "--lm-head-draft", "--preserve-thinking",
        ]
    if profile == "qwen38":
        ctx = o.get("ctx", "240000")
        return [
            _norm(str(fakes.artifact)), "--host", o.get("host", "127.0.0.1"), "--port", o.get("port", "8080"),
            "--model-id", "qwen3.8-27b", "--max-context", ctx, "--kv-capacity", o.get("kv", ctx),
            "--max-concurrency", o.get("conc", "4"), "--prefill-chunk", "1024", "--kv-dtype", "fp8",
            "--spec", "mtp", "--draft-tokens", o.get("draft", "3"), "--lm-head-draft", "--preserve-thinking",
        ]
    return [
        "--model", _norm(str(fakes.gguf)), "-ngl", "99", "-c", o.get("ctx", "262144"),
        "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "--flash-attn", "on",
        "--host", o.get("host", "127.0.0.1"), "--port", o.get("port", "8080"), "--alias", "qwen3.8-27b",
        "--jinja", "--temp", "1.0", "--top-p", "0.95", "--top-k", "20", "--min-p", "0.0",
    ]


@pytest.fixture
def new(tmp_path: Path) -> Plugin:
    plugin = Plugin(tmp_path, NEW, "llm-kit")
    plugin.stub_cli()
    return plugin


@pytest.fixture
def fakes(tmp_path: Path) -> Fakes:
    return Fakes(tmp_path)


def _launch(plugin: Plugin, tmp: Path, fakes: Fakes, profile: str, *args: str,
            extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = _base_env(tmp / "home", {**fakes.env(), **(extra or {})})
    (tmp / "home").mkdir(exist_ok=True)
    return _run(plugin.script("model-server.sh"), (profile, *args), env)


# --------------------------------------------------------------------------
# the measured profiles
# --------------------------------------------------------------------------

class TestProfileArgv:
    """Break one flag in model-server.sh (for example ``--kv-dtype int8``) and these go red."""

    @pytest.mark.parametrize("profile", _PROFILES)
    def test_default_argv_is_the_measured_profile(self, new, fakes, tmp_path, profile):
        result = _launch(new, tmp_path, fakes, profile)
        assert result.returncode == 0, result.stderr
        _pid, _ld, argv = fakes.recorded()
        assert argv == _argv(profile, fakes)

    def test_qwen36_overrides(self, new, fakes, tmp_path):
        extra = {"QWEN36_HOST": "0.0.0.0", "QWEN36_PORT": "9001", "QWEN36_CTX": "131072",
                 "QWEN36_MAX_CONCURRENCY": "2", "QWEN36_MTP_DRAFT_TOKENS": "5"}
        assert _launch(new, tmp_path, fakes, "qwen36", extra=extra).returncode == 0
        assert fakes.recorded()[2] == _argv("qwen36", fakes, host="0.0.0.0", port="9001", ctx="131072",
                                            conc="2", draft="5")

    def test_qwen38_overrides_and_kv_capacity_follows_context(self, new, fakes, tmp_path):
        extra = {"QWEN38_HOST": "0.0.0.0", "QWEN38_PORT": "9002", "QWEN38_CTX": "131072",
                 "QWEN38_MAX_CONCURRENCY": "3", "QWEN38_MTP_DRAFT_TOKENS": "2"}
        assert _launch(new, tmp_path, fakes, "qwen38", extra=extra).returncode == 0
        assert fakes.recorded()[2] == _argv("qwen38", fakes, host="0.0.0.0", port="9002", ctx="131072",
                                            conc="3", draft="2")

    def test_qwen38_kv_capacity_can_be_set_outright(self, new, fakes, tmp_path):
        extra = {"QWEN38_CTX": "131072", "QWEN38_KV_CAPACITY": "65536"}
        assert _launch(new, tmp_path, fakes, "qwen38", extra=extra).returncode == 0
        assert fakes.recorded()[2] == _argv("qwen38", fakes, ctx="131072", kv="65536")

    def test_qwen38l_overrides_use_its_own_context_name(self, new, fakes, tmp_path):
        extra = {"QWEN38_HOST": "0.0.0.0", "QWEN38_PORT": "9003", "QWEN38L_CTX": "131072", "QWEN38_CTX": "240000"}
        assert _launch(new, tmp_path, fakes, "qwen38l", extra=extra).returncode == 0
        assert fakes.recorded()[2] == _argv("qwen38l", fakes, host="0.0.0.0", port="9003", ctx="131072")

    def test_qwen38l_exports_the_llama_library_path(self, new, fakes, tmp_path):
        assert _launch(new, tmp_path, fakes, "qwen38l").returncode == 0
        ld = fakes.recorded()[1].replace("\\", "/")
        assert "llama" in ld and "lib" in ld

    @pytest.mark.parametrize("profile", ("qwen36", "qwen38"))
    def test_serial_sets_concurrency_to_one(self, new, fakes, tmp_path, profile):
        assert _launch(new, tmp_path, fakes, profile, "--serial").returncode == 0
        assert fakes.recorded()[2] == _argv(profile, fakes, conc="1")

    def test_serial_is_refused_for_qwen38l(self, new, fakes, tmp_path):
        result = _launch(new, tmp_path, fakes, "qwen38l", "--serial")
        assert result.returncode == 2
        assert "--serial" in result.stderr
        assert not fakes.record.exists()

    @pytest.mark.parametrize("profile", _PROFILES)
    def test_extra_arguments_are_appended_after_the_defaults(self, new, fakes, tmp_path, profile):
        assert _launch(new, tmp_path, fakes, profile, "--flag", "value").returncode == 0
        assert fakes.recorded()[2] == _argv(profile, fakes) + ["--flag", "value"]

    @pytest.mark.parametrize("profile", _PROFILES)
    def test_print_command_does_not_launch(self, new, fakes, tmp_path, profile):
        result = _launch(new, tmp_path, fakes, profile, "--print-command", "--extra")
        assert result.returncode == 0
        assert "--extra" in result.stdout
        assert not fakes.record.exists()

    def test_ninfer_root_resolves_the_binary_and_artifacts(self, new, tmp_path):
        root = tmp_path / "ninfer-root"
        record = tmp_path / "root.record"
        _write_exec(root / "build" / "apps" / "ninfer-serve",
                    f"#!/bin/sh\nfor a in \"$@\"; do printf '%s\\n' \"$a\"; done > '{_posix(record)}'\n")
        (root / "models").mkdir()
        for name in ("qwen3_6_35b_a3b.ninfer", "qwen3_8_27b_nvfp4.ninfer"):
            (root / "models" / name).touch()
        (tmp_path / "home").mkdir()
        env = _base_env(tmp_path / "home", {"NINFER_ROOT": str(root)})
        for profile, artifact in (("qwen36", "qwen3_6_35b_a3b.ninfer"), ("qwen38", "qwen3_8_27b_nvfp4.ninfer")):
            assert _run(new.script("model-server.sh"), (profile,), env).returncode == 0
            first = _norm(record.read_text(encoding="utf-8").splitlines()[0])
            assert first == _norm(str(root / "models" / artifact))

    def test_llama_server_and_model_defaults_hang_off_the_prefix_and_home(self, new, tmp_path):
        record = tmp_path / "llama.record"
        home = tmp_path / "home"
        prefix = home / ".local" / "opt" / "llama.cpp"
        _write_exec(prefix / "bin" / "llama-server",
                    f"#!/bin/sh\nfor a in \"$@\"; do printf '%s\\n' \"$a\"; done > '{_posix(record)}'\n")
        model = home / "hf" / "models" / "Qwen3.8-27B-GGUF" / "Qwen3.8-27B-UD-Q4_K_XL.gguf"
        model.parent.mkdir(parents=True)
        model.touch()
        assert _run(new.script("model-server.sh"), ("qwen38l",), _base_env(home)).returncode == 0
        lines = record.read_text(encoding="utf-8").splitlines()
        assert _norm(lines[1]) == _norm(str(model))

    @pytest.mark.parametrize(("profile", "needle"), (("qwen36", "missing executable"), ("qwen38", "missing executable"),
                                                    ("qwen38l", "missing executable")))
    def test_a_missing_server_binary_is_refused(self, new, fakes, tmp_path, profile, needle):
        extra = {"NINFER_SERVE": str(tmp_path / "nope"), "LLAMA_SERVER": str(tmp_path / "nope")}
        result = _launch(new, tmp_path, fakes, profile, extra=extra)
        assert result.returncode == 1
        assert needle in result.stderr

    def test_a_missing_artifact_is_refused(self, new, fakes, tmp_path):
        result = _launch(new, tmp_path, fakes, "qwen36", extra={"QWEN36_ARTIFACT": str(tmp_path / "nope")})
        assert result.returncode == 1
        assert "missing artifact" in result.stderr

    def test_missing_and_unknown_profiles_exit_two(self, new, fakes, tmp_path):
        assert _launch(new, tmp_path, fakes, "").returncode == 2
        unknown = _launch(new, tmp_path, fakes, "qwen99")
        assert unknown.returncode == 2
        assert "unknown profile" in unknown.stderr

    def test_help_text_advertises_serial_only_where_it_acts(self, new, fakes, tmp_path):
        for profile, advertised in (("qwen36", True), ("qwen38", True), ("qwen38l", False)):
            result = _launch(new, tmp_path, fakes, profile, "--help")
            assert result.returncode == 0
            assert (f"{profile}-server" in result.stdout)
            assert ("[--serial]" in result.stdout) is advertised


# --------------------------------------------------------------------------
# the launch guard
# --------------------------------------------------------------------------

def _guard_run(plugin: Plugin, tmp: Path, fakes: Fakes, extra: dict[str, str] | None = None):
    result = _launch(plugin, tmp, fakes, "qwen36", extra=extra)
    return result, fakes.record.exists()


def _warnings(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stderr.splitlines() if line.startswith("model-server.sh:")]


class TestLaunchGuard:
    """Make exit 1 refuse (``3)`` -> ``1|3)`` in guard_launch) and the matrix goes red."""

    def test_an_allowing_guard_is_called_with_the_launching_pid_and_the_launch_proceeds(self, new, fakes, tmp_path):
        result, launched = _guard_run(new, tmp_path, fakes)
        assert result.returncode == 0, result.stderr
        assert launched
        pid, _ld, _argv_ = fakes.recorded()
        assert new.calls() == [f"local swapper guard-launch --caller-pid {pid}"]
        assert not _warnings(result)

    def test_exit_three_alone_blocks_the_launch(self, new, fakes, tmp_path):
        new.stub_cli(guard_exit=3, stderr="llama-swap is running for this user")
        result, launched = _guard_run(new, tmp_path, fakes)
        assert result.returncode == 1
        assert not launched, "a refused launch must never reach exec"
        assert "launch refused by the swapper guard" in result.stderr
        assert "llama-swap is running for this user" in result.stderr

    @pytest.mark.parametrize(("code", "stderr"), (
        (1, "Traceback (most recent call last): boom"),   # an uncaught exception exits 1 like any failure
        (1, "llm-kit: no Python interpreter found"),      # the shim finding no interpreter
        (2, "usage error"),
        (4, "something"),
        (5, "inspection indeterminate"),                  # psutil missing
        (126, "not executable"),
        (127, "interpreter vanished"),
    ))
    def test_every_other_exit_proceeds_with_one_warning(self, new, fakes, tmp_path, code, stderr):
        new.stub_cli(guard_exit=code, stderr=stderr)
        result, launched = _guard_run(new, tmp_path, fakes)
        assert result.returncode == 0, result.stderr
        assert launched
        warnings = _warnings(result)
        assert len(warnings) == 1, result.stderr
        assert f"exit {code}" in warnings[0]
        assert "proceeding without it" in warnings[0]
        assert new.calls(), "the guard must have been asked"

    def test_a_missing_launcher_proceeds_with_a_warning(self, new, fakes, tmp_path):
        new.bin("llm-kit").unlink()
        result, launched = _guard_run(new, tmp_path, fakes)
        assert result.returncode == 0
        assert launched
        warnings = _warnings(result)
        assert len(warnings) == 1
        assert "launch guard skipped" in warnings[0] and "proceeding without it" in warnings[0]

    def test_a_non_executable_launcher_proceeds_with_a_warning(self, new, fakes, tmp_path):
        new.bin("llm-kit").chmod(0o644)
        if os.access(new.bin("llm-kit"), os.X_OK):
            pytest.skip("this filesystem reports every file executable")
        result, launched = _guard_run(new, tmp_path, fakes)
        assert result.returncode == 0
        assert launched
        assert "launch guard skipped" in result.stderr

    def test_a_real_shim_with_no_entrypoint_fails_open(self, new, fakes, tmp_path):
        """The shipped shim, copied beside the script, with nothing for it to run."""
        shutil.copy2(NEW / "bin" / "llm-kit", new.bin("llm-kit"))
        result, launched = _guard_run(new, tmp_path, fakes)
        assert result.returncode == 0, result.stderr
        assert launched
        assert len(_warnings(result)) == 1

    def test_the_guard_is_called_by_path_never_from_path(self, new, fakes, tmp_path):
        decoys = tmp_path / "decoys"
        decoy_log = tmp_path / "decoy.calls"
        _write_exec(decoys / "llm-kit", f"#!/bin/sh\necho \"$*\" >> '{_posix(decoy_log)}'\nexit 3\n")
        env = _base_env(tmp_path / "home", fakes.env(), path_prefix=decoys)
        (tmp_path / "home").mkdir()
        result = _run(new.script("model-server.sh"), ("qwen36",), env)
        assert result.returncode == 0
        assert not decoy_log.exists()
        assert new.calls()

    @pytest.mark.parametrize("flag", ("--help", "--print-command"))
    def test_help_and_print_command_never_call_the_guard(self, new, fakes, tmp_path, flag):
        assert _launch(new, tmp_path, fakes, "qwen36", flag).returncode == 0
        assert new.calls() == []

    def test_the_legacy_opt_out_skips_the_guard_with_no_call_and_no_warning(self, new, fakes, tmp_path):
        new.stub_cli(guard_exit=3, stderr="would refuse")
        result, launched = _guard_run(new, tmp_path, fakes, {"LLM_SCRIPTING_KIT_LAUNCH_GUARD": "off"})
        assert result.returncode == 0
        assert launched
        assert new.calls() == []
        assert not _warnings(result)

    @pytest.mark.parametrize("value", ("on", "ON", "OFF", "0", "false", ""))
    def test_any_other_value_leaves_the_guard_on(self, new, fakes, tmp_path, value):
        new.stub_cli(guard_exit=3, stderr="would refuse")
        result, launched = _guard_run(new, tmp_path, fakes, {"LLM_SCRIPTING_KIT_LAUNCH_GUARD": value})
        assert result.returncode == 1
        assert not launched

    def test_no_llm_kit_spelling_of_the_opt_out_exists(self, new, fakes, tmp_path):
        """Design decision 7 keeps the legacy name; an llm-kit name is not invented."""
        new.stub_cli(guard_exit=3, stderr="would refuse")
        for name in ("LLM_KIT_LAUNCH_GUARD", "LLM_KIT_NO_LAUNCH_GUARD"):
            result, launched = _guard_run(new, tmp_path, fakes, {name: "off"})
            assert result.returncode == 1 and not launched, name

    def test_removing_the_guard_call_lets_a_refusal_through(self, new, fakes, tmp_path):
        """Revert proof: without ``guard_launch "$$"`` the refusing stub no longer stops the launch."""
        script = new.script("model-server.sh")
        text = script.read_text(encoding="utf-8")
        assert 'guard_launch "$$"' in text
        script.write_text(text.replace('guard_launch "$$"\n', ""), encoding="utf-8", newline="\n")
        new.stub_cli(guard_exit=3, stderr="would refuse")
        result, launched = _guard_run(new, tmp_path, fakes)
        assert result.returncode == 0 and launched
        assert new.calls() == []


# --------------------------------------------------------------------------
# qwen-switch
# --------------------------------------------------------------------------

def _switch_tools(tmp: Path, pid_file: Path, listener: str = "ninfer-serve", model: str = "qwen3.6-35b-a3b") -> Path:
    tools = tmp / "tools"
    _write_exec(tools / "lsof", f"#!/bin/sh\nif test -f '{_posix(pid_file)}'; then cat '{_posix(pid_file)}'; fi\n")
    _write_exec(tools / "ps", "#!/bin/sh\ncase \"$*\" in\n"
                              f"  *comm=*) echo {listener} ;;\n"
                              f"  *args=*) echo '{listener} model --model-id {model}' ;;\n"
                              "esac\n")
    _write_exec(tools / "curl", f"#!/bin/sh\necho '{{\"data\":[{{\"id\":\"{model}\"}}]}}'\n")
    return tools


def _fake_loop_server(tmp: Path, pid_file: Path) -> Path:
    """A fake ninfer-serve that records its pid and idles for a bounded time."""
    return _write_exec(tmp / "loop-ninfer-serve",
                       f"#!/bin/sh\necho $$ > '{_posix(pid_file)}'\ni=0\nwhile [ $i -lt 25 ]; do sleep 1; i=$((i+1)); done\n")


def _stop(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    pid = pid_file.read_text(encoding="utf-8").strip()
    if pid.isdigit():
        subprocess.run([BASH, "-c", f"kill -0 {pid} 2>/dev/null && kill -KILL {pid}"], check=False, timeout=30)


def _switch_env(tmp: Path, server: Path, artifact: Path, tools: Path, extra: dict[str, str] | None = None):
    (tmp / "home").mkdir(exist_ok=True)
    return _base_env(tmp / "home", {"NINFER_SERVE": str(server), "QWEN36_ARTIFACT": str(artifact),
                                    "QWEN_SWITCH_TIMEOUT": "10", **(extra or {})}, path_prefix=tools)


class TestQwenSwitch:
    """Replace ``bin/llm-kit`` by ``llm-kit`` in replace_listener, or drop the ``||`` abort, and these go red."""

    def _start(self, plugin: Plugin, tmp: Path, profile: str = "qwen36", extra: dict[str, str] | None = None):
        pid_file = tmp / "server.pid"
        tools = _switch_tools(tmp, pid_file)
        decoy_log = tmp / "decoy.calls"
        _write_exec(tools / "llm-kit", f"#!/bin/sh\necho \"$*\" >> '{_posix(decoy_log)}'\nexit 0\n")
        artifact = tmp / "model.ninfer"
        artifact.touch()
        env = _switch_env(tmp, _fake_loop_server(tmp, pid_file), artifact, tools, extra)
        try:
            result = _run(plugin.script("qwen-switch.sh"), ("start", profile), env)
        finally:
            _stop(pid_file)
        return result, pid_file, decoy_log

    def test_start_frees_the_port_through_the_sibling_cli_by_path_then_launches(self, new, tmp_path):
        result, pid_file, decoy_log = self._start(new, tmp_path)
        assert result.returncode == 0, result.stderr
        assert "qwen36 is ready on port 8080" in result.stdout
        calls = new.calls()
        assert calls[0] == "local swapper terminate-listener --port 8080 --accept-replace"
        assert len(calls) == 2 and calls[1].startswith("local swapper guard-launch --caller-pid ")
        assert not decoy_log.exists(), "llm-kit must not resolve from PATH"
        assert pid_file.exists()

    def test_the_port_comes_from_the_profile_environment(self, new, tmp_path):
        result, _pid, _decoy = self._start(new, tmp_path, extra={"QWEN36_PORT": "9101"})
        assert new.calls()[0] == "local swapper terminate-listener --port 9101 --accept-replace"
        assert "port 9101" in result.stdout + result.stderr

    def test_a_non_zero_terminate_aborts_without_launching(self, new, tmp_path):
        new.stub_cli(terminate_exit=1)
        result, pid_file, _decoy = self._start(new, tmp_path)
        assert result.returncode != 0
        assert "not starting qwen36; port 8080 was not freed" in result.stderr
        assert new.calls() == ["local swapper terminate-listener --port 8080 --accept-replace"]
        assert not pid_file.exists(), "the launcher must not run after a refusal"

    def test_the_script_sends_no_signals_itself(self):
        text = (NEW / "scripts" / "qwen-switch.sh").read_text(encoding="utf-8")
        assert not re.search(r"\bkill\b|\bpkill\b|\bkillall\b|-TERM\b|-KILL\b", text)

    def test_unknown_profile_and_bad_port_never_reach_the_cli(self, new, tmp_path):
        result, _pid, _decoy = self._start(new, tmp_path, profile="qwen99")
        assert result.returncode == 2 and "unknown profile" in result.stderr
        result, _pid, _decoy = self._start(new, tmp_path, extra={"QWEN36_PORT": "80x"})
        assert result.returncode == 2 and "invalid port" in result.stderr
        assert new.calls() == []

    def test_usage_errors(self, new, tmp_path):
        env = _base_env(tmp_path)
        script = new.script("qwen-switch.sh")
        assert _run(script, (), env).returncode == 2
        assert _run(script, ("start",), env).returncode == 2
        assert _run(script, ("status", "extra"), env).returncode == 2
        assert _run(script, ("bogus",), env).returncode == 2
        helped = _run(script, ("--help",), env)
        assert helped.returncode == 0
        assert "llm-kit local swapper terminate-listener" in helped.stdout

    def test_status_is_clear_when_no_server_listens(self, new, tmp_path):
        tools = _switch_tools(tmp_path, tmp_path / "absent.pid")
        result = _run(new.bin("qwen-switch"), ("status",),
                      _base_env(tmp_path / "home", {}, path_prefix=tools))
        assert result.returncode == 0
        assert result.stdout.strip() == "no managed Qwen server is listening on the configured ports"

    @pytest.mark.parametrize(("listener", "model", "expected"), (
        ("ninfer-serve", "qwen3.6-35b-a3b", "qwen36"),
        ("ninfer-serve", "qwen3.8-27b", "qwen38"),
        ("llama-server", "qwen3.8-27b", "qwen38l"),
    ))
    def test_status_names_the_resident_profile(self, new, tmp_path, listener, model, expected):
        pid_file = tmp_path / "listener.pid"
        pid_file.write_text("4242\n", encoding="utf-8")
        tools = _switch_tools(tmp_path, pid_file, listener=listener, model=model)
        result = _run(new.script("qwen-switch.sh"), ("status",), _base_env(tmp_path / "home", {}, path_prefix=tools))
        assert result.returncode == 0
        assert result.stdout.strip() == f"{expected} running on port 8080 (pid 4242)"


# --------------------------------------------------------------------------
# front door and adapters
# --------------------------------------------------------------------------

class TestFrontdoor:
    def test_print_command_names_the_sibling_cli_and_the_frontdoor_verb(self, new, tmp_path):
        result = _run(new.script("frontdoor.sh"), ("--print-command", "--check", "--port", "9"), _base_env(tmp_path))
        assert result.returncode == 0
        tokens = result.stdout.split()
        assert _norm(tokens[0]).endswith("/plugin/bin/llm-kit")
        assert tokens[1:] == ["frontdoor", "--check", "--port", "9"]
        assert new.calls() == []

    def test_launch_execs_the_frontdoor_verb_with_every_argument(self, new, tmp_path):
        result = _run(new.script("frontdoor.sh"), ("--check", "--spill-after", "2"), _base_env(tmp_path))
        assert result.returncode == 0
        assert new.calls() == ["frontdoor --check --spill-after 2"]

    def test_the_cli_exit_status_is_propagated(self, new, tmp_path):
        new.stub_cli(frontdoor_exit=7)
        assert _run(new.script("frontdoor.sh"), ("--check",), _base_env(tmp_path)).returncode == 7

    def test_a_missing_launcher_is_reported(self, new, tmp_path):
        new.bin("llm-kit").unlink()
        result = _run(new.script("frontdoor.sh"), ("--check",), _base_env(tmp_path))
        assert result.returncode == 1
        assert "launcher not found" in result.stderr

    def test_it_names_no_legacy_or_production_interpreter(self):
        text = (NEW / "scripts" / "frontdoor.sh").read_text(encoding="utf-8")
        assert "llm_scripting_kit" not in text and "llm-scripting-kit" not in text
        assert ".venv" not in text and "PYTHONPATH" not in text


class TestAdapters:
    @pytest.mark.parametrize("profile", _PROFILES)
    def test_each_adapter_runs_its_profile(self, new, fakes, tmp_path, profile):
        (tmp_path / "home").mkdir()
        env = _base_env(tmp_path / "home", fakes.env())
        direct = _run(new.script("model-server.sh"), (profile, "--print-command"), env)
        adapter = _run(new.bin(f"{profile}-server"), ("--print-command",), env)
        assert adapter.returncode == 0
        assert adapter.stdout == direct.stdout

    def test_an_adapter_reached_through_a_symlink_resolves_back_to_the_plugin(self, new, fakes, tmp_path):
        link = tmp_path / "linked" / "qwen36-server"
        link.parent.mkdir()
        try:
            link.symlink_to(new.bin("qwen36-server"))
        except OSError:
            pytest.skip("symlinks need a privilege this account lacks")
        result = _run(link, ("--help",), _base_env(tmp_path))
        assert result.returncode == 0
        assert "qwen36-server" in result.stdout

    def test_qwen_switch_adapter_delegates_to_the_script(self, new, tmp_path):
        tools = _switch_tools(tmp_path, tmp_path / "absent.pid")
        result = _run(new.bin("qwen-switch"), ("status",), _base_env(tmp_path, {}, path_prefix=tools))
        assert result.returncode == 0
        assert "no managed Qwen server" in result.stdout

    def test_adapters_are_byte_identical_to_the_legacy_ones(self):
        for name in _ADAPTERS:
            assert (NEW / "bin" / name).read_bytes() == (LEGACY / "bin" / name).read_bytes(), name


class TestPortableShell:
    """bash 3.2 (macOS /bin/bash) and zsh-launched bash: no bash 4+ constructs."""

    _FILES = ("scripts/model-server.sh", "scripts/qwen-switch.sh", "scripts/frontdoor.sh",
              *(f"bin/{a}" for a in _ADAPTERS))
    _BASH4 = (r"declare\s+-A", r"\bmapfile\b", r"\breadarray\b", r"\$\{[^}]*(,,|\^\^)[^}]*\}", r"\bread\s+-[a-z]*p",
              r";&", r"&>>", r"\|&", r"\bcoproc\b", r"\bwait\s+-n\b", r"\bdeclare\s+-n\b", r"\blocal\s+-n\b")

    @pytest.mark.parametrize("rel", _FILES)
    def test_no_bash_four_constructs_and_an_env_bash_shebang(self, rel):
        text = (NEW / rel).read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash\n"), rel
        for pattern in self._BASH4:
            assert not re.search(pattern, text), (rel, pattern)
        assert "\r" not in text

    @pytest.mark.parametrize("rel", _FILES)
    def test_ascii_only(self, rel):
        (NEW / rel).read_bytes().decode("ascii")


# --------------------------------------------------------------------------
# parity with the frozen legacy scripts
# --------------------------------------------------------------------------

def _legacy_launch(tmp: Path, fakes: Fakes, profile: str, args: tuple[str, ...], extra: dict[str, str]):
    """The legacy script, in its own tree, with a Python stub as its guard."""
    plugin = Plugin(tmp, LEGACY, "llm-scripting-kit", name="legacy")
    guard_log = tmp / "legacy-guard.calls"
    guard = tmp / "legacy_guard.py"
    guard.write_text("import sys\n"
                     f"open({str(guard_log)!r}, 'a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n",
                     encoding="utf-8")
    (tmp / "home").mkdir(exist_ok=True)
    env = _base_env(tmp / "home", {**fakes.env(), "LLM_SCRIPTING_KIT_PYTHON": sys.executable,
                                   "LLM_SCRIPTING_KIT_CLI": str(guard), **extra})
    result = _run(plugin.script("model-server.sh"), (profile, *args), env)
    guard_calls = guard_log.read_text(encoding="utf-8").splitlines() if guard_log.exists() else []
    return result, guard_calls


class TestLegacyParity:
    """Same environment into the legacy script and the llm-kit script; compare what each execs."""

    _CASES = {
        "default": {},
        "overrides": {"QWEN36_HOST": "0.0.0.0", "QWEN36_PORT": "9001", "QWEN36_CTX": "131072",
                      "QWEN36_MAX_CONCURRENCY": "2", "QWEN36_MTP_DRAFT_TOKENS": "5",
                      "QWEN38_HOST": "0.0.0.0", "QWEN38_PORT": "9002", "QWEN38_CTX": "131072",
                      "QWEN38_KV_CAPACITY": "65536", "QWEN38_MAX_CONCURRENCY": "3",
                      "QWEN38_MTP_DRAFT_TOKENS": "2", "QWEN38L_CTX": "100000"},
    }

    @pytest.mark.parametrize("profile", _PROFILES)
    @pytest.mark.parametrize("case", sorted(_CASES))
    @pytest.mark.parametrize("args", ((), ("--serial",), ("--flag", "value")), ids=("plain", "serial", "extra"))
    def test_the_exec_argv_is_identical(self, tmp_path, profile, case, args):
        if profile == "qwen38l" and args == ("--serial",):
            # Both scripts refuse (text parity: test_refusals_and_text_are_identical).
            refused = Plugin(tmp_path, NEW, "llm-kit")
            refused.stub_cli()
            assert _launch(refused, tmp_path, Fakes(tmp_path), profile, *args,
                           extra=self._CASES[case]).returncode == 2
            return
        legacy_tmp, new_tmp = tmp_path / "a", tmp_path / "b"
        legacy_tmp.mkdir()
        new_tmp.mkdir()
        legacy_fakes, new_fakes = Fakes(legacy_tmp), Fakes(new_tmp)
        legacy_result, legacy_guard = _legacy_launch(legacy_tmp, legacy_fakes, profile, args, self._CASES[case])
        plugin = Plugin(new_tmp, NEW, "llm-kit")
        plugin.stub_cli()
        new_result = _launch(plugin, new_tmp, new_fakes, profile, *args, extra=self._CASES[case])
        assert legacy_result.returncode == new_result.returncode == 0, (legacy_result.stderr, new_result.stderr)

        def shape(fakes: Fakes) -> list[str]:
            return [a.replace(_norm(str(fakes.tmp)), "<tmp>") for a in fakes.recorded()[2]]

        assert shape(legacy_fakes) == shape(new_fakes)
        legacy_ld = _norm(legacy_fakes.recorded()[1]).replace(_norm(str(legacy_fakes.tmp)), "<tmp>")
        new_ld = _norm(new_fakes.recorded()[1]).replace(_norm(str(new_fakes.tmp)), "<tmp>")
        assert legacy_ld == new_ld
        # The documented CLI difference: the facade lives under `local`.
        legacy_pid, new_pid = legacy_fakes.recorded()[0], new_fakes.recorded()[0]
        assert legacy_guard == [f"swapper guard-launch --caller-pid {legacy_pid}"]
        assert plugin.calls() == [f"local swapper guard-launch --caller-pid {new_pid}"]

    @pytest.mark.parametrize("profile", _PROFILES)
    @pytest.mark.parametrize("args", (("--help",), ("-h",), ("--print-command",), ("--print-command", "--x"),
                                      ("--serial",), ("--serial", "--help"), ("--serial", "--print-command")))
    def test_refusals_and_text_are_identical(self, tmp_path, profile, args):
        legacy_tmp, new_tmp = tmp_path / "a", tmp_path / "b"
        legacy_tmp.mkdir()
        new_tmp.mkdir()
        legacy_fakes, new_fakes = Fakes(legacy_tmp), Fakes(new_tmp)
        legacy_result, _guard = _legacy_launch(legacy_tmp, legacy_fakes, profile, args, {})
        plugin = Plugin(new_tmp, NEW, "llm-kit")
        plugin.stub_cli()
        new_result = _launch(plugin, new_tmp, new_fakes, profile, *args)

        def clean(result: subprocess.CompletedProcess[str], tmp: Path) -> tuple[int, str, str]:
            swap = lambda s: re.sub(r"\S*pytest-of-\S*?/(a|b)/", "<tmp>/", re.sub(r"/+", "/", s.replace("\\", "/")))  # noqa: E731
            return result.returncode, swap(result.stdout), swap(result.stderr)

        assert clean(legacy_result, legacy_tmp) == clean(new_result, new_tmp)

    @pytest.mark.parametrize("profile", ("", "qwen99"))
    def test_profile_errors_are_identical(self, tmp_path, profile):
        legacy_tmp, new_tmp = tmp_path / "a", tmp_path / "b"
        legacy_tmp.mkdir()
        new_tmp.mkdir()
        legacy_result, _guard = _legacy_launch(legacy_tmp, Fakes(legacy_tmp), profile, (), {})
        plugin = Plugin(new_tmp, NEW, "llm-kit")
        plugin.stub_cli()
        new_result = _launch(plugin, new_tmp, Fakes(new_tmp), profile)
        assert (legacy_result.returncode, legacy_result.stdout, legacy_result.stderr) == \
            (new_result.returncode, new_result.stdout, new_result.stderr)

    @pytest.mark.parametrize("profile", _PROFILES)
    def test_missing_binary_messages_are_identical(self, tmp_path, profile):
        legacy_tmp, new_tmp = tmp_path / "a", tmp_path / "b"
        legacy_tmp.mkdir()
        new_tmp.mkdir()
        missing = {"NINFER_SERVE": "/no/such/server", "LLAMA_SERVER": "/no/such/server"}
        legacy_result, _guard = _legacy_launch(legacy_tmp, Fakes(legacy_tmp), profile, (), missing)
        plugin = Plugin(new_tmp, NEW, "llm-kit")
        plugin.stub_cli()
        new_result = _launch(plugin, new_tmp, Fakes(new_tmp), profile, extra=missing)
        assert (legacy_result.returncode, legacy_result.stderr) == (new_result.returncode, new_result.stderr)

    @pytest.mark.parametrize(("code", "refused"), ((0, False), (1, False), (3, True), (5, False)))
    def test_the_guard_decision_matches_the_legacy_one(self, tmp_path, code, refused):
        legacy_tmp, new_tmp = tmp_path / "a", tmp_path / "b"
        legacy_tmp.mkdir()
        new_tmp.mkdir()
        legacy_fakes, new_fakes = Fakes(legacy_tmp), Fakes(new_tmp)
        legacy = Plugin(legacy_tmp, LEGACY, "llm-scripting-kit", name="legacy")
        guard = legacy_tmp / "guard.py"
        guard.write_text(f"import sys\nsys.stderr.write('guard says no')\nsys.exit({code})\n", encoding="utf-8")
        (legacy_tmp / "home").mkdir()
        legacy_env = _base_env(legacy_tmp / "home", {**legacy_fakes.env(), "LLM_SCRIPTING_KIT_PYTHON": sys.executable,
                                                    "LLM_SCRIPTING_KIT_CLI": str(guard)})
        legacy_result = _run(legacy.script("model-server.sh"), ("qwen36",), legacy_env)
        plugin = Plugin(new_tmp, NEW, "llm-kit")
        plugin.stub_cli(guard_exit=code, stderr="guard says no")
        new_result = _launch(plugin, new_tmp, new_fakes, "qwen36")
        assert legacy_result.returncode == new_result.returncode
        assert legacy_fakes.record.exists() is new_fakes.record.exists() is (not refused)
        assert (legacy_result.stderr.count("launch refused") == new_result.stderr.count("launch refused")
                == (1 if refused else 0))

    def test_qwen_switch_start_and_status_match(self, tmp_path):
        """Same fakes into both switch scripts: the calls differ only by the documented ``local`` group."""
        results = {}
        for label, source, cli in (("legacy", LEGACY, "llm-scripting-kit"), ("new", NEW, "llm-kit")):
            tmp = tmp_path / label
            tmp.mkdir()
            plugin = Plugin(tmp, source, cli, name=label)
            plugin.stub_cli()
            pid_file = tmp / "server.pid"
            tools = _switch_tools(tmp, pid_file)
            artifact = tmp / "model.ninfer"
            artifact.touch()
            env = _switch_env(tmp, _fake_loop_server(tmp, pid_file), artifact, tools)
            if label == "legacy":
                env["LLM_SCRIPTING_KIT_PYTHON"] = sys.executable
                guard = tmp / "guard.py"
                guard.write_text("", encoding="utf-8")
                env["LLM_SCRIPTING_KIT_CLI"] = str(guard)
            try:
                start = _run(plugin.script("qwen-switch.sh"), ("start", "qwen36"), env)
            finally:
                _stop(pid_file)
            status = _run(plugin.script("qwen-switch.sh"), ("status",), _base_env(tmp / "home", {}, path_prefix=tools))
            results[label] = (start.returncode, re.sub(r"pid \d+", "pid N", start.stdout), re.sub(r"pid \d+", "pid N", status.stdout),
                              plugin.calls()[0])
        legacy, new = results["legacy"], results["new"]
        assert legacy[:3] == new[:3]
        assert legacy[3] == "swapper terminate-listener --port 8080 --accept-replace"
        assert new[3] == "local swapper terminate-listener --port 8080 --accept-replace"
