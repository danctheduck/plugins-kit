"""CLAUDE_BOOTSTRAP_DATA_ROOT redirect in the venv-first launcher shims.

job-kit and llm-scripting-kit launch their CLI under the plugin venv at the
production path ``~/.claude/plugins/data/plugins-kit/<plugin>/.venv``. A
claude-plugin-test session sets ``CLAUDE_BOOTSTRAP_DATA_ROOT`` to a separate
tree that holds its own venvs, so a shim that kept naming the production venv
ran the published release's interpreter inside a session meant to test the
working copy. The rule under test (root CLAUDE.md, "Scoped exception: Python
CLI launcher shims"): the redirected venv is the FIRST candidate only when the
variable is set AND that venv exists; every other case resolves exactly as
before.

The tests run each real shim, copied into a throwaway plugin tree whose
entrypoint prints ``sys.prefix``, against real venvs, so the printed prefix
names which interpreter the shim chose. The POSIX shim needs a bash; its
``.cmd`` twin needs Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IS_WINDOWS = os.name == "nt"


def _find_bash() -> str | None:
    """Git Bash on Windows (never the WSL launcher), else bash on PATH."""
    candidates = []
    if _IS_WINDOWS:
        candidates += [
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
        ]
    found = shutil.which("bash")
    if found:
        candidates.append(found)
    for candidate in candidates:
        if Path(candidate).exists() and "WindowsApps" not in candidate and "System32" not in candidate:
            return candidate
    return None


_BASH = _find_bash()

# (plugin, shim file stem, entrypoint relative to the plugin root)
_SHIMS = [
    ("job-kit", "job-kit", "lib/job_kit_entrypoint.py"),
    ("llm-scripting-kit", "llm-scripting-kit", "scripts/llm_scripting_kit_cli.py"),
]
_KINDS = [
    pytest.param(
        "posix",
        marks=pytest.mark.skipif(_BASH is None, reason="bash not available"),
    ),
    pytest.param(
        "cmd",
        marks=pytest.mark.skipif(not _IS_WINDOWS, reason=".cmd shims run only on Windows"),
    ),
]


@pytest.fixture(scope="session")
def venv_template(tmp_path_factory) -> Path:
    """One real venv, copied per test (a venv is located by its pyvenv.cfg, not
    its path, so a copy runs as its own environment)."""
    root = tmp_path_factory.mktemp("venv-template") / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(root)],
        check=True, capture_output=True, timeout=120,
    )
    return root


def _make_venv(template: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, dest, symlinks=True)
    return dest


class _Launch:
    """A shim copied into a throwaway plugin tree, plus the two data trees."""

    def __init__(self, tmp_path: Path, template: Path, plugin: str, stem: str,
                 entrypoint: str, kind: str) -> None:
        self.template = template
        self.plugin = plugin
        self.kind = kind
        plugin_root = tmp_path / "plugin"
        suffix = ".cmd" if kind == "cmd" else ""
        shim_src = _REPO_ROOT / "plugins" / plugin / "bin" / (stem + suffix)
        self.shim = plugin_root / "bin" / shim_src.name
        self.shim.parent.mkdir(parents=True)
        shutil.copy2(shim_src, self.shim)
        entry = plugin_root / entrypoint
        entry.parent.mkdir(parents=True)
        entry.write_text("import sys\nprint(sys.prefix)\n", encoding="utf-8")
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.redirect_root = tmp_path / "redirected-data"

    def production_venv(self) -> Path:
        return _make_venv(
            self.template,
            self.home / ".claude" / "plugins" / "data" / "plugins-kit" / self.plugin / ".venv",
        )

    def redirected_venv(self) -> Path:
        return _make_venv(
            self.template, self.redirect_root / "plugins-kit" / self.plugin / ".venv"
        )

    def chosen_prefix(self, *, redirect: bool) -> Path:
        env = dict(os.environ)
        for name in ("BOOTSTRAP_PYTHON", "BOOTSTRAP_PROJECT_PYTHON", "CLAUDE_BOOTSTRAP_DATA_ROOT"):
            env.pop(name, None)
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        if redirect:
            env["CLAUDE_BOOTSTRAP_DATA_ROOT"] = str(self.redirect_root)
        command = [_BASH, str(self.shim)] if self.kind == "posix" else ["cmd.exe", "/c", str(self.shim)]
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return Path(result.stdout.strip().splitlines()[-1]).resolve()


@pytest.fixture(params=_SHIMS, ids=[s[0] for s in _SHIMS])
def shim_spec(request):
    return request.param


@pytest.fixture(params=_KINDS)
def kind(request):
    return request.param


@pytest.fixture
def launch(tmp_path, venv_template, shim_spec, kind) -> _Launch:
    plugin, stem, entrypoint = shim_spec
    return _Launch(tmp_path, venv_template, plugin, stem, entrypoint, kind)


def test_redirected_venv_outranks_production_when_root_is_set(launch):
    """The point of the change: set + redirected venv present -> redirected venv.

    Shown to fail: restore the shim from git (``git show HEAD:<shim>``); it
    names only the production venv and this test sees the production prefix.
    """
    production = launch.production_venv()
    redirected = launch.redirected_venv()
    assert launch.chosen_prefix(redirect=True) == redirected.resolve()
    assert launch.chosen_prefix(redirect=True) != production.resolve()


def test_production_venv_is_chosen_when_root_is_unset(launch):
    """Normal behaviour is identical: with the variable unset, even a populated
    redirect tree on disk is ignored.

    Shown to fail: break the shim's production DATA_DIR (any other path) and
    the chosen prefix is no longer the production venv.
    """
    production = launch.production_venv()
    launch.redirected_venv()
    assert launch.chosen_prefix(redirect=False) == production.resolve()


def test_production_venv_is_chosen_when_redirected_venv_is_absent(launch):
    """Set but empty redirect tree: the existing chain runs unchanged.

    Shown to fail: drop the existence test from the shim (``[ -x ... ]`` /
    ``if exist ...``) and the shim selects a path that is not there.
    """
    production = launch.production_venv()
    launch.redirect_root.mkdir()
    assert launch.chosen_prefix(redirect=True) == production.resolve()
