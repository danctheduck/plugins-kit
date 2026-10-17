"""workflow-kit launch paths are redirect-aware under claudx.

Two surfaces, one property: a session that sets CLAUDE_BOOTSTRAP_DATA_ROOT
(the claude-plugin-test launcher) must never end up running workflow-kit's
runners against the PRODUCTION venv.

1. The runners. ``openrouter_run.py``, ``check_artifact.py`` and
   ``compile_workflow.py`` receive their interpreter from the caller (the
   compiled workflow's ``${inputs.workflowKitVenvPython}``, or the skill's
   ``<plugin-venv-python>``), and the Workflow tool expands nothing in
   ``args``, so the entry guard is the only runtime check. With a redirected
   root and no redirected venv each must exit 2 before any work, even when the
   test opt-out is set.
2. The placeholder definitions. ``<workflow-kit-venv-python>``,
   ``workflowKitVenvPython`` and ``venvPy`` are defined in prose and comments
   that an agent copies from; a definition spelled with a production data
   path produces a production interpreter under claudx. Every venv or
   bootstrap-log path in the shipped workflow-kit text must use the
   redirect-aware base.
"""

import ast
import os
import re
import subprocess
import sys

import pytest

from wk_testlib import PLUGIN_ROOT

SCRIPTS = PLUGIN_ROOT / "scripts"
GUARDED = ["openrouter_run.py", "check_artifact.py", "compile_workflow.py"]

# The placeholder definitions the plan names, plus the other shipped text that
# names the venv, so a new definition site cannot reintroduce a literal.
DEFINITION_SITES = [
    "skills/workflow-kit/references/preamble.js",
    "skills/workflow-kit/references/node-strategies.md",
    "examples/node-strategies.example.js",
]
SCANNED_SUFFIXES = {".md", ".js", ".yaml", ".yml", ".py", ".json"}
SKIPPED_DIRS = {"__pycache__", ".venv", "workflow_kit.egg-info", "node_modules"}
# The vendored guard documents the production path it replaces; it is the
# mechanism, not a launch site.
SKIPPED_FILES = {"bootstrap_guard.py"}

R_BASE = "CLAUDE_BOOTSTRAP_DATA_ROOT:-"
DATA_ROOT_TOKEN = ".claude/plugins/data"
LAUNCH_TARGETS = (".venv", "bootstrap.log")


def production_literal_lines(text):
    """Lines that reach a venv or bootstrap data file through a production base.

    A line is an offender when it names the plugins data directory and a launch
    target (``.venv``, ``bootstrap.log``) without the redirect-aware
    ``${CLAUDE_BOOTSTRAP_DATA_ROOT:-...}`` base in front of that data path.
    User state under the data directory (a config.yaml) names no launch target
    and is not flagged.
    """
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if DATA_ROOT_TOKEN not in line:
            continue
        if not any(target in line for target in LAUNCH_TARGETS):
            continue
        head = line.split(DATA_ROOT_TOKEN, 1)[0]
        if R_BASE not in head:
            found.append((number, line.strip()))
    return found


def redirect_aware_lines(text):
    return [
        line for line in text.splitlines()
        if DATA_ROOT_TOKEN in line
        and any(t in line for t in LAUNCH_TARGETS)
        and R_BASE in line.split(DATA_ROOT_TOKEN, 1)[0]
    ]


def _shipped_text_files():
    for path in sorted(PLUGIN_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if SKIPPED_DIRS & set(path.relative_to(PLUGIN_ROOT).parts):
            continue
        if path.name in SKIPPED_FILES:
            continue
        yield path


# --------------------------------------------------------------------------- #
# The runners refuse a missing redirected interpreter
# --------------------------------------------------------------------------- #
def _redirected_env(tmp_path):
    env = dict(os.environ)
    home = tmp_path / "home"
    home.mkdir()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CLAUDE_BOOTSTRAP_DATA_ROOT"] = str(tmp_path / "data")
    # The conftest opt-out is deliberately kept: a missing redirected
    # interpreter is refused even with it set. The loop flag is dropped so no
    # inherited token can matter.
    env["_BOOTSTRAP_GUARD_SKIP_REEXEC"] = "1"
    env.pop("_BOOTSTRAP_GUARD_VENV_REEXEC", None)
    return env


@pytest.mark.parametrize("script", GUARDED)
def test_runner_refuses_when_redirected_venv_is_missing(tmp_path, script):
    """Shown to fail: delete the ``reexec_under_plugin_venv`` call from the script
    (for compile_workflow.py, the block added ahead of the ``workflow_kit_lib``
    import) and the child prints its usage and exits 0 instead of 2."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--help"],
        cwd=tmp_path,
        env=_redirected_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 2, (proc.returncode, proc.stdout[:300], proc.stderr[:300])
    assert "redirected plugin interpreter is missing" in proc.stderr
    # The message names the redirected location, not the production one.
    assert str(tmp_path / "data").replace("\\", "/") in proc.stderr.replace("\\", "/")
    assert proc.stdout == ""


@pytest.mark.parametrize("script", GUARDED)
def test_runner_without_redirect_is_not_refused(tmp_path, script):
    """The refusal belongs to the redirect: `--help` still works without it."""
    env = _redirected_env(tmp_path)
    del env["CLAUDE_BOOTSTRAP_DATA_ROOT"]
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr[:300])
    assert "usage:" in proc.stdout


@pytest.mark.parametrize("script", GUARDED)
def test_guard_call_precedes_every_shared_lib_import(script):
    tree = ast.parse((SCRIPTS / script).read_text(encoding="utf-8"))
    guard_line = None
    for node in tree.body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) == "reexec_under_plugin_venv"
        ):
            assert [a.value for a in node.value.args] == ["workflow-kit"]
            guard_line = node.lineno
    assert guard_line is not None, f"{script} has no module-level reexec_under_plugin_venv call"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
            )
            for name in names:
                if name.split(".")[0] in {"llm_kit", "bootstrap_lib"}:
                    assert node.lineno > guard_line, (script, name, node.lineno)


# --------------------------------------------------------------------------- #
# The placeholder definitions are redirect-aware
# --------------------------------------------------------------------------- #
def test_no_shipped_workflow_kit_text_reaches_the_venv_through_a_production_base():
    offenders = {}
    for path in _shipped_text_files():
        hits = production_literal_lines(path.read_text(encoding="utf-8"))
        if hits:
            offenders[str(path.relative_to(PLUGIN_ROOT)).replace("\\", "/")] = hits
    assert not offenders, offenders


@pytest.mark.parametrize("relative", DEFINITION_SITES)
def test_each_definition_site_defines_the_interpreter_and_root_redirect_aware(relative):
    text = (PLUGIN_ROOT / relative).read_text(encoding="utf-8")
    assert redirect_aware_lines(text), f"{relative} defines no redirect-aware venv path"
    assert "WORKFLOW_KIT_ROOT:?" in text, f"{relative} does not define pluginRoot via WORKFLOW_KIT_ROOT"
    assert "${CLAUDE_PLUGIN_ROOT}" not in text, (
        f"{relative} names ${{CLAUDE_PLUGIN_ROOT}}, which is unset in the Bash tool"
    )


@pytest.mark.parametrize("relative", DEFINITION_SITES)
def test_detector_flags_a_production_literal_injected_at_each_definition_site(relative):
    """Mutation: restore the production spelling at every redirect-aware site."""
    text = (PLUGIN_ROOT / relative).read_text(encoding="utf-8")
    assert not production_literal_lines(text)
    mutated = text.replace('"${CLAUDE_BOOTSTRAP_DATA_ROOT:-$HOME/.claude/plugins/data}"', "~/.claude/plugins/data")
    assert mutated != text
    assert production_literal_lines(mutated), f"{relative}: a restored production literal went unflagged"


def test_detector_flags_the_other_production_spellings():
    for literal in (
        "$HOME/.claude/plugins/data/plugins-kit/workflow-kit/.venv/bin/python",
        "%USERPROFILE%/.claude/plugins/data/plugins-kit/workflow-kit/.venv/Scripts/python.exe",
        "~/.claude/plugins/data/plugins-kit/workflow-kit/bootstrap.log",
    ):
        assert production_literal_lines(literal), literal
    # A redirect-aware base and user state are not flagged.
    assert not production_literal_lines(
        '"${CLAUDE_BOOTSTRAP_DATA_ROOT:-$HOME/.claude/plugins/data}"/plugins-kit/workflow-kit/.venv/bin/python'
    )
    assert not production_literal_lines("~/.claude/plugins/data/plugins-kit/llm-scripting-kit/config.yaml")
