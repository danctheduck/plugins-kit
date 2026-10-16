"""claudx containment in the launcher shims (CLAUDE_BOOTSTRAP_DATA_ROOT, CLAUDE_PLUGIN_TEST).

job-kit and llm-scripting-kit launch their CLI under the plugin venv at the
production path ``~/.claude/plugins/data/plugins-kit/<plugin>/.venv``. A
claude-plugin-test session sets ``CLAUDE_BOOTSTRAP_DATA_ROOT`` to a separate
tree that holds its own venvs, so a shim that named the production venv ran the
published release's interpreter inside a session meant to test the working
copy. The rules under test (root CLAUDE.md, "Scoped exception: Python CLI
launcher shims"):

* With the variable set, the redirected venv is the ONLY candidate. A missing
  one exits 2 with a message, never a fallback to the production venv. With the
  variable unset the existing chain is unchanged.
* All four shims (job-kit, llm-scripting-kit, hue-kit, secrets-kit) refuse to
  run as the CACHED copy, a path under ``plugins/cache/<marketplace>/``, when
  ``CLAUDE_PLUGIN_TEST`` is set. The marketplace is
  ``CLAUDE_PLUGIN_TEST_MARKETPLACE``; with it unset every cache path is refused,
  and a cache path under another marketplace is kept. Outside claudx nothing is
  refused.

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
_VENV_SHIMS = [
    ("job-kit", "job-kit", "lib/job_kit_entrypoint.py"),
    ("llm-scripting-kit", "llm-scripting-kit", "scripts/llm_scripting_kit_cli.py"),
]
# hue-kit and secrets-kit choose no plugin venv (the CLI re-execs itself), so only
# the cached-copy refusal applies to them.
_SHIMS = _VENV_SHIMS + [
    ("hue-kit", "hue-kit", "scripts/hue_kit_cli.py"),
    ("secrets-kit", "secrets-kit", "scripts/secrets_kit_cli.py"),
]
# Variables a surrounding claudx session would leak into the shim under test.
_SCRUBBED_ENV = (
    "CLAUDE_PLUGIN_TEST",
    "CLAUDE_PLUGIN_TEST_MARKETPLACE",
    "CLAUDE_PLUGIN_TEST_DIRS",
    "CLAUDE_BOOTSTRAP_DATA_ROOT",
    "BOOTSTRAP_PYTHON",
    "BOOTSTRAP_PROJECT_PYTHON",
)
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
    """A shim copied into a throwaway plugin tree, plus the two data trees.

    ``cache_marketplace`` places the plugin tree at
    ``<home>/.claude/plugins/cache/<marketplace>/<plugin>/1.0.0`` instead of an
    ordinary directory, so the shim runs as the cached copy.
    """

    def __init__(self, tmp_path: Path, template: Path, plugin: str, stem: str,
                 entrypoint: str, kind: str, cache_marketplace: str | None = None) -> None:
        self.template = template
        self.plugin = plugin
        self.kind = kind
        self.home = tmp_path / "home"
        self.home.mkdir()
        if cache_marketplace is None:
            plugin_root = tmp_path / "plugin"
        else:
            plugin_root = (self.home / ".claude" / "plugins" / "cache" / cache_marketplace
                           / plugin / "1.0.0")
        suffix = ".cmd" if kind == "cmd" else ""
        shim_src = _REPO_ROOT / "plugins" / plugin / "bin" / (stem + suffix)
        self.shim = plugin_root / "bin" / shim_src.name
        self.shim.parent.mkdir(parents=True)
        shutil.copy2(shim_src, self.shim)
        entry = plugin_root / entrypoint
        entry.parent.mkdir(parents=True)
        entry.write_text("import sys\nprint(sys.prefix)\n", encoding="utf-8")
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

    def run(self, *, redirect: bool, claudx: bool = False,
            marketplace: str | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        for name in _SCRUBBED_ENV:
            env.pop(name, None)
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        if redirect:
            env["CLAUDE_BOOTSTRAP_DATA_ROOT"] = str(self.redirect_root)
        if claudx:
            env["CLAUDE_PLUGIN_TEST"] = "1"
        if marketplace is not None:
            env["CLAUDE_PLUGIN_TEST_MARKETPLACE"] = marketplace
        command = [_BASH, str(self.shim)] if self.kind == "posix" else ["cmd.exe", "/c", str(self.shim)]
        return subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=60,
        )

    def chosen_prefix(self, *, redirect: bool, claudx: bool = False) -> Path:
        result = self.run(redirect=redirect, claudx=claudx)
        assert result.returncode == 0, result.stderr
        return Path(result.stdout.strip().splitlines()[-1]).resolve()


@pytest.fixture(params=_VENV_SHIMS, ids=[s[0] for s in _VENV_SHIMS])
def shim_spec(request):
    return request.param


@pytest.fixture(params=_SHIMS, ids=[s[0] for s in _SHIMS])
def any_shim_spec(request):
    return request.param


@pytest.fixture(params=_KINDS)
def kind(request):
    return request.param


@pytest.fixture
def launch(tmp_path, venv_template, shim_spec, kind) -> _Launch:
    plugin, stem, entrypoint = shim_spec
    return _Launch(tmp_path, venv_template, plugin, stem, entrypoint, kind)


def _cached_launch(tmp_path, template, spec, kind, marketplace="plugins-kit") -> _Launch:
    plugin, stem, entrypoint = spec
    return _Launch(tmp_path, template, plugin, stem, entrypoint, kind,
                   cache_marketplace=marketplace)


def test_redirected_venv_outranks_production_when_root_is_set(launch):
    """Set + redirected venv present -> redirected venv.

    Shown to fail: restore the shim from git history before the redirect was
    added; it names only the production venv and this test sees the production
    prefix.
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


def test_missing_redirected_venv_is_refused_not_replaced_by_production(launch):
    """Set but empty redirect tree: exit 2 with a message, even though a
    working production venv exists. The silent fallback is the defect.

    Shown to fail: restore the previous branch (use the redirected venv only
    when it exists, else keep the production one); the shim then exits 0 with
    the production prefix and this test sees returncode 0.
    """
    production = launch.production_venv()
    launch.redirect_root.mkdir()
    result = launch.run(redirect=True)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "CLAUDE_BOOTSTRAP_DATA_ROOT" in result.stderr
    assert "refusing to fall back to the production venv" in result.stderr
    assert str(production.resolve()) not in result.stdout


def test_missing_redirected_venv_is_refused_under_claudx_too(launch):
    """The same refusal when the session is a claudx session."""
    launch.production_venv()
    launch.redirect_root.mkdir()
    result = launch.run(redirect=True, claudx=True, marketplace="plugins-kit")
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "refusing to fall back to the production venv" in result.stderr


@pytest.mark.parametrize("marketplace_env", ["plugins-kit", "Plugins-Kit", None],
                         ids=["owned", "owned-other-case", "marketplace-unset"])
def test_cached_copy_is_refused_under_claudx(tmp_path, venv_template, any_shim_spec, kind,
                                             marketplace_env):
    """A shim whose own path is under plugins/cache/<owned marketplace>/ exits 2.

    With the marketplace unset every cache path is refused, as in
    bootstrap_lib.env_var_check.cache_root_refusal.

    Shown to fail: delete the CLAUDE_PLUGIN_TEST block from the shim (between
    PLUGIN_ROOT and the interpreter chain); the shim then runs instead.
    """
    launch = _cached_launch(tmp_path, venv_template, any_shim_spec, kind)
    result = launch.run(redirect=False, claudx=True, marketplace=marketplace_env)
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "refusing to run the cached copy" in result.stderr
    assert "CLAUDE_PLUGIN_TEST" in result.stderr


def test_cached_copy_is_kept_outside_claudx(tmp_path, venv_template, any_shim_spec, kind):
    """Without CLAUDE_PLUGIN_TEST the cache IS the plugin in use: no refusal."""
    launch = _cached_launch(tmp_path, venv_template, any_shim_spec, kind)
    result = launch.run(redirect=False, claudx=False, marketplace="plugins-kit")
    assert "refusing to run the cached copy" not in result.stderr


def test_cached_copy_of_another_marketplace_is_kept(tmp_path, venv_template, any_shim_spec, kind):
    """A cache path under a marketplace claudx does not own is not refused.

    Shown to fail: make the shim refuse any plugins/cache path regardless of
    CLAUDE_PLUGIN_TEST_MARKETPLACE.
    """
    launch = _cached_launch(tmp_path, venv_template, any_shim_spec, kind,
                            marketplace="some-other-marketplace")
    result = launch.run(redirect=False, claudx=True, marketplace="plugins-kit")
    assert "refusing to run the cached copy" not in result.stderr


def test_working_copy_is_not_refused_under_claudx(launch):
    """A shim outside the plugin cache runs under claudx on its redirected venv."""
    launch.production_venv()
    redirected = launch.redirected_venv()
    assert launch.chosen_prefix(redirect=True, claudx=True) == redirected.resolve()
