"""Nothing but bootstrap_guard writes the re-exec loop flag.

``bootstrap_guard`` keeps two environment variables with two meanings:

* ``_BOOTSTRAP_GUARD_VENV_REEXEC`` is provenance only. Its value is the
  interpreter path a re-exec moved into, and the guard is its only writer.
* ``_BOOTSTRAP_GUARD_SKIP_REEXEC=1`` is the only opt-out, set by test
  conftests and test subprocess environments.

A writer of the loop flag outside the guard reopens the ambiguity the split
removed: a "1" (or any non-path value) there is read by an old guard as an
opt-out and by a new guard as an untrusted foreign value. This file scans every
tracked or untracked-but-not-ignored text file for such a writer, and scans the
shipped surfaces (plugins/, scripts/) for a writer of the skip variable, which
only a test may set.

Python files are read by AST, so an alias (``_LOOP_FLAG = "..."``), the guard's
own constant (``mod._REEXEC_GUARD_ENV``), ``monkeypatch.setenv``,
``os.environ[...] = ``, ``setdefault``, ``putenv``, a dict display and a
``dict(os.environ, NAME=...)`` keyword are all writes. Reading, popping and
deleting the flag are not. Other text files are read by regex for an assignment
form.

Allowlisted loop-flag writers, each with the reason it must write the flag:

* every ``bootstrap_guard.py`` (the guard writes its own token);
* the guard's own tests, ``tests/bootstrap/test_bootstrap_guard.py`` and
  ``tests/bootstrap/test_claudx_escapes.py``, and the launcher's environment
  test ``tests/repo-scripts/test_claude_plugin_test_env.py``, which place an
  inherited value in a child environment to prove how it is handled.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SELF = "tests/repo-scripts/test_guard_flag_writers.py"

LOOP_FLAG = "_BOOTSTRAP_GUARD_VENV_REEXEC"
SKIP_VAR = "_BOOTSTRAP_GUARD_SKIP_REEXEC"
_CONSTANT = {LOOP_FLAG: "_REEXEC_GUARD_ENV", SKIP_VAR: "_REEXEC_SKIP_ENV"}

_LOOP_WRITER_ALLOWLIST = {
    "tests/bootstrap/test_bootstrap_guard.py":
        "the guard's own tests simulate an inherited token and the legacy value",
    "tests/bootstrap/test_claudx_escapes.py":
        "drives a real child through an inherited token and the legacy value",
    "tests/repo-scripts/test_claude_plugin_test_env.py":
        "places an inherited loop flag in the launcher's parent environment",
}

_SETTER_METHODS = {"setdefault", "setenv", "putenv", "setitem"}
_MAX_BYTES = 2_000_000


def _tracked_text_files() -> dict[str, str]:
    """Relative POSIX path -> text, for tracked and untracked-unignored files."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=_REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    files: dict[str, str] = {}
    for rel in filter(None, out.split("\0")):
        path = _REPO_ROOT / rel
        if not path.is_file() or path.stat().st_size > _MAX_BYTES:
            continue
        try:
            files[rel] = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: cannot carry a text assignment
    return files


def python_writes(source: str, name: str) -> list[int]:
    """Line numbers where Python ``source`` WRITES the environment variable ``name``."""
    tree = ast.parse(source)
    constant = _CONSTANT[name]
    aliases = {constant}

    def refers(node: ast.AST) -> bool:
        if isinstance(node, ast.Constant):
            return node.value == name
        if isinstance(node, ast.Name):
            return node.id in aliases
        if isinstance(node, ast.Attribute):
            return node.attr == constant
        return False

    # An alias is a name bound to the variable's name or to the guard's constant.
    # Iterate to a fixed point so a chain of two aliases is followed.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and refers(node.value)
                and node.targets[0].id not in aliases
            ):
                aliases.add(node.targets[0].id)
                changed = True

    lines: set[int] = set()
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Subscript) and refers(target.slice):
                lines.add(node.lineno)
        if isinstance(node, ast.Dict):
            if any(key is not None and refers(key) for key in node.keys):
                lines.add(node.lineno)
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in _SETTER_METHODS
                and any(refers(arg) for arg in node.args)
            ):
                lines.add(node.lineno)
            if any(kw.arg == name for kw in node.keywords):
                lines.add(node.lineno)
    return sorted(lines)


def text_writes(text: str, name: str) -> list[int]:
    """Line numbers where non-Python ``text`` assigns the variable ``name``."""
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])" + re.escape(name) + r"""(?:\s*=|["']\s*:)"""
    )
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if pattern.search(line)
    ]


def loop_flag_offenders(files: dict[str, str]) -> list[str]:
    offenders = []
    for rel, text in sorted(files.items()):
        if rel == _SELF or rel.endswith("/bootstrap_guard.py"):
            continue
        if rel in _LOOP_WRITER_ALLOWLIST:
            continue
        if LOOP_FLAG not in text and _CONSTANT[LOOP_FLAG] not in text:
            continue
        hits = python_writes(text, LOOP_FLAG) if rel.endswith(".py") else text_writes(text, LOOP_FLAG)
        offenders.extend(f"{rel}:{line}" for line in hits)
    return offenders


def skip_variable_offenders(files: dict[str, str]) -> list[str]:
    """The skip variable is a test opt-out: no shipped surface may set it."""
    offenders = []
    for rel, text in sorted(files.items()):
        if rel == _SELF or rel.endswith("/bootstrap_guard.py"):
            continue
        if not rel.startswith(("plugins/", "scripts/")):
            continue
        if rel.endswith(".md"):
            continue  # documentation shows the opt-out in a test conftest example
        if SKIP_VAR not in text and _CONSTANT[SKIP_VAR] not in text:
            continue
        hits = python_writes(text, SKIP_VAR) if rel.endswith(".py") else text_writes(text, SKIP_VAR)
        offenders.extend(f"{rel}:{line}" for line in hits)
    return offenders


@pytest.fixture(scope="module")
def files() -> dict[str, str]:
    found = _tracked_text_files()
    assert found, "the file scan collected nothing, so every check below would be vacuous"
    return found


def test_nothing_but_the_guard_writes_the_loop_flag(files):
    offenders = loop_flag_offenders(files)
    assert not offenders, (
        f"{LOOP_FLAG} carries only the interpreter path bootstrap_guard re-exec'd into. "
        f"Set {SKIP_VAR}=1 for a test opt-out instead. Writers: {offenders}"
    )


def test_no_shipped_surface_sets_the_skip_variable(files):
    offenders = skip_variable_offenders(files)
    assert not offenders, (
        f"{SKIP_VAR} is the test opt-out and would disable the re-exec for a consumer: "
        f"{offenders}"
    )


def test_the_scan_sees_the_real_writers_of_the_skip_variable(files):
    """Non-vacuity: the conftests that opt out are found by the same detector."""
    conftests = [
        rel for rel, text in files.items()
        if rel.startswith("tests/") and rel.endswith("conftest.py")
        and python_writes(text, SKIP_VAR)
    ]
    assert len(conftests) >= 1, "no conftest writes the skip variable; the detector is blind"


def _conftest_sources(files: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(
        (rel, text) for rel, text in files.items()
        if rel.startswith("tests/") and rel.endswith("conftest.py")
        and python_writes(text, SKIP_VAR)
    )


_INJECTIONS = {
    "setdefault-literal": 'os.environ.setdefault("_BOOTSTRAP_GUARD_VENV_REEXEC", "1")\n',
    "subscript-literal": 'os.environ["_BOOTSTRAP_GUARD_VENV_REEXEC"] = "1"\n',
    "alias-constant": 'FLAG = "_BOOTSTRAP_GUARD_VENV_REEXEC"\nos.environ[FLAG] = "1"\n',
    "guard-constant": (
        "from bootstrap_guard import _REEXEC_GUARD_ENV\n"
        'os.environ[_REEXEC_GUARD_ENV] = "1"\n'
    ),
    "dict-display": 'ENV = {"_BOOTSTRAP_GUARD_VENV_REEXEC": "1"}\n',
    "dict-keyword": 'ENV = dict(os.environ, _BOOTSTRAP_GUARD_VENV_REEXEC="1")\n',
    "monkeypatch": 'def test_x(monkeypatch):\n    monkeypatch.setenv("_BOOTSTRAP_GUARD_VENV_REEXEC", "1")\n',
}


@pytest.mark.parametrize("kind", sorted(_INJECTIONS))
def test_mutation_an_injected_loop_flag_write_in_a_conftest_copy_is_flagged(files, kind):
    """A check must be shown to fail: copy a real conftest, inject a loop-flag
    write of each shape, and require the verdict to flag exactly that copy."""
    conftests = _conftest_sources(files)
    assert conftests, "no conftest to mutate"
    rel, text = conftests[0]
    assert loop_flag_offenders({rel: text}) == [], "the unmutated conftest must be clean"
    mutated = text + "\nimport os\n" + _INJECTIONS[kind]
    flagged = loop_flag_offenders({rel: mutated})
    assert flagged and all(item.startswith(rel + ":") for item in flagged), (kind, flagged)


def test_mutation_every_real_conftest_copy_is_flagged_when_it_writes_the_loop_flag(files):
    conftests = _conftest_sources(files)
    assert conftests
    for rel, text in conftests:
        mutated = text.replace(SKIP_VAR, LOOP_FLAG)
        assert mutated != text
        assert loop_flag_offenders({rel: mutated}), rel


def test_mutation_the_legacy_value_in_a_shell_or_doc_example_is_flagged():
    assert loop_flag_offenders(
        {"CONTRIBUTING.md": f"{LOOP_FLAG}=1 uv run pytest tests/p4-kit -q\n"}
    ) == ["CONTRIBUTING.md:1"]
    assert loop_flag_offenders(
        {"scripts/run.sh": f"export {LOOP_FLAG}=1\n"}
    ) == ["scripts/run.sh:1"]


def test_reading_popping_or_naming_the_loop_flag_is_not_a_write():
    source = (
        "import os\n"
        f'env = dict(os.environ)\nenv.pop("{LOOP_FLAG}", None)\n'
        f'seen = os.environ.get("{LOOP_FLAG}")\n'
        f'has = "{LOOP_FLAG}" in os.environ\n'
    )
    assert loop_flag_offenders({"tests/x/test_y.py": source}) == []


def test_mutation_a_shipped_script_that_sets_the_skip_variable_is_flagged():
    cases = (
        ("plugins/p4-kit/scripts/run.py", f'import os\nos.environ["{SKIP_VAR}"] = "1"\n', 2),
        ("plugins/p4-kit/bin/p4-kit", f"export {SKIP_VAR}=1\n", 1),
        (
            "scripts/claude_plugin_test.py",
            f'import os\nos.environ.setdefault("{SKIP_VAR}", "1")\n',
            2,
        ),
    )
    for rel, text, line in cases:
        assert skip_variable_offenders({rel: text}) == [f"{rel}:{line}"], rel
    # A launcher that scrubs it for a child is a read, not a write.
    scrub = f'import os\nenv = dict(os.environ)\nenv.pop("{SKIP_VAR}", None)\n'
    assert skip_variable_offenders({"scripts/claude_plugin_test.py": scrub}) == []
