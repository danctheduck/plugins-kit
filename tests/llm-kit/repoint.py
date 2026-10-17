"""Helpers for the old-versus-final differential.

Imported by ``test_copy_inventory.py`` and ``test_repointed_suites.py``; also a
command line for iterating on one suite:

    uv run --extra dev python tests/llm-kit/repoint.py compare job-kit
    uv run --extra dev python tests/llm-kit/repoint.py mirror-only job-kit

The legacy suite runs from ``tests/<suite>`` and the re-pointed suite from the
ignored mirror ``tmp/<suite>``, each in its own pytest process. The mirror
process starts with the mirror directory on PYTHONPATH so that the generated
``sitecustomize.py`` runs in it and in every child interpreter.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "llm_kit_repoint.py"
SUITES = ("llm-scripting-kit", "content-pipeline-kit", "job-kit")
TOTAL_TESTS = 5276
SUITE_TOTALS = {"llm-scripting-kit": 1926, "content-pipeline-kit": 2732, "job-kit": 618}


def load_generator():
    """The generator module, loaded by path (it lives in the repo scripts/)."""
    name = "llm_kit_repoint_tests"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_ledger(suite: str) -> dict:
    path = REPO / "tests" / "llm-kit" / "repoint-dispositions" / f"{suite}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# running a suite
# --------------------------------------------------------------------------

_SCRUB_PREFIXES = ("PYTEST_", "COVERAGE", "_BOOTSTRAP_GUARD_VENV_REEXEC")


def _clean_env(extra: Optional[Mapping[str, str]] = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(_SCRUB_PREFIXES)}
    if extra:
        env.update(extra)
    return env


def run_pytest(target: str, junit: Path, *, mirror: bool, extra_args: Iterable[str] = (),
               timeout: int = 3600) -> subprocess.CompletedProcess:
    env_extra = {}
    if mirror:
        existing = os.environ.get("PYTHONPATH", "")
        env_extra["PYTHONPATH"] = os.pathsep.join(
            p for p in (str(REPO / "tmp"), existing) if p)
    else:
        env_extra["PYTHONPATH"] = ""
    cmd = [
        sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider",
        "--tb=short", f"--junitxml={junit}", *extra_args,
    ]
    return subprocess.run(
        cmd, cwd=REPO, env=_clean_env(env_extra), capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )


@dataclass(frozen=True)
class Outcome:
    status: str          # passed | failed | error | skipped
    kind: str = ""       # exception type for failed/error
    message: str = ""    # normalized first line of the failure message


def parse_junit(path: Path, suite: str) -> dict[str, Outcome]:
    """nodeid (suite-relative, stable across legacy and mirror) -> Outcome."""
    tree = ET.parse(path)
    out: dict[str, Outcome] = {}
    for case in tree.iter("testcase"):
        classname = case.get("classname", "")
        parts = classname.split(".")
        # drop the leading root (tests|tmp) and suite directory segments
        if len(parts) >= 2 and parts[0] in ("tests", "tmp") and parts[1] == suite:
            parts = parts[2:]
        elif parts and parts[0] == suite:
            parts = parts[1:]
        module_index = next((i for i, p in enumerate(parts) if p.startswith("test_") or p == "conftest"), 0)
        module = parts[module_index] if parts else "?"
        nested = "::".join(parts[module_index + 1:])
        nodeid = normalize_nodeid(
            f"{suite}/{module}.py::" + (nested + "::" if nested else "") + case.get("name", ""))
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None or error is not None:
            node = failure if failure is not None else error
            out[nodeid] = Outcome(
                "failed" if failure is not None else "error",
                (node.get("type") or "").rsplit(".", 1)[-1],
                normalize_message(node.get("message") or ""),
            )
        elif skipped is not None:
            out[nodeid] = Outcome("skipped")
        else:
            out[nodeid] = Outcome("passed")
    return out


_REVERSE: list = []


def _reverse_names() -> list[tuple[str, str]]:
    """(final dotted name, legacy dotted name) pairs, longest final name first.

    A mirror run names final modules where the legacy run names legacy ones, so a
    node id or a failure message is spelled back in legacy names before the two
    runs are compared. The generated alias tree (``legacy_names.<legacy>``) is
    spelled back the same way.
    """
    if not _REVERSE:
        gen = load_generator()
        mapping = json.loads((REPO / "tests" / "llm-kit" / "repoint-map.json").read_text(encoding="utf-8"))
        for path, row in mapping["modules"].items():
            if row["kind"] in ("module", "facade-package") and path.endswith(".py"):
                _REVERSE.append((row["final"], gen.legacy_dotted(path)))
        _REVERSE.sort(key=lambda p: len(p[0]), reverse=True)
    return _REVERSE


def _reverse_path_overrides() -> list[tuple[str, str]]:
    """(final path, legacy path) for the map's path overrides (made-up paths a test uses as data)."""
    mapping = json.loads((REPO / "tests" / "llm-kit" / "repoint-map.json").read_text(encoding="utf-8"))
    return [(row["to"], legacy) for legacy, row in mapping.get("path_overrides", {}).items()]


def to_legacy_names(text: str) -> str:
    """Spell final module names in legacy names (idempotent on legacy text)."""
    text = text.replace("legacy_names.", "")
    for final, legacy in _reverse_path_overrides():
        text = text.replace(final, legacy)
    for final, legacy in _reverse_names():
        text = re.sub(rf"(?<![\w.]){re.escape(final)}(?![\w])", legacy, text)
    return text


def normalize_nodeid(nodeid: str) -> str:
    """Spell a mirror node id the way the legacy run spells it.

    Parameter ids derive from the strings a test parametrizes over, which the
    re-pointer rewrites; the legacy spelling is the stable one.
    """
    return to_legacy_names(nodeid)


_NORMALIZERS = [
    (re.compile(r"plugins[\\/]llm-kit[\\/]lib"), "<LIB>"),
    (re.compile(r"plugins[\\/](?:llm-scripting-kit|content-pipeline-kit|job-kit)[\\/]lib"), "<LIB>"),
    (re.compile(r"[A-Za-z]:[\\/][^\s'\"]*?(?:pytest-of-[^\\/]+|Temp)[\\/][^\s'\"]*"), "<TMP>"),
    (re.compile(r"(?:/tmp|/private/var)[^\s'\"]*"), "<TMP>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "0x?"),
    (re.compile(r"\b(?:tests|tmp)[\\/](?:llm-scripting-kit|content-pipeline-kit|job-kit)[\\/]"), "<SUITE>/"),
    (re.compile(r"\d+\.\d+s"), "<T>s"),
]


def normalize_message(message: str) -> str:
    line = message.strip().splitlines()[0] if message.strip() else ""
    line = to_legacy_names(line)
    for pattern, repl in _NORMALIZERS:
        line = pattern.sub(repl, line)
    return line[:300]


@dataclass
class SuiteRun:
    suite: str
    outcomes: dict[str, Outcome]
    returncode: int
    summary: str
    stdout_tail: str


def run_suite(suite: str, workdir: Path, *, mirror: bool) -> SuiteRun:
    workdir.mkdir(parents=True, exist_ok=True)
    junit = workdir / f"{'mirror' if mirror else 'legacy'}-{suite}.xml"
    target = f"tmp/{suite}" if mirror else f"tests/{suite}"
    proc = run_pytest(target, junit, mirror=mirror)
    if not junit.is_file():
        raise RuntimeError(
            f"{target}: pytest produced no junit file (exit {proc.returncode})\n"
            f"{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    return SuiteRun(suite, parse_junit(junit, suite), proc.returncode,
                    lines[-1] if lines else "", "\n".join(lines[-40:]))


# --------------------------------------------------------------------------
# comparing
# --------------------------------------------------------------------------

def failing(outcomes: Mapping[str, Outcome]) -> dict[str, Outcome]:
    return {k: v for k, v in outcomes.items() if v.status in ("failed", "error")}


def rewrite_files(ledger: Mapping) -> set[str]:
    return {Path(r["path"]).name for r in ledger["rows"] if r["disposition"] == "rewrite"}


def declared_differences(ledger: Mapping) -> dict[str, dict]:
    out = {}
    for row in ledger["rows"]:
        for node, entry in row.get("declared_differences", {}).items():
            out[node] = entry
    return out


def compare(suite: str, legacy: Mapping[str, Outcome], mirror: Mapping[str, Outcome],
            ledger: Mapping) -> list[str]:
    """Problems found comparing the legacy run with the mirror run (empty when equal)."""
    problems: list[str] = []
    mirrored_files = rewrite_files(ledger)

    def in_scope(nodeid: str) -> bool:
        return nodeid.split("::", 1)[0].split("/", 1)[1] in mirrored_files

    old = {k: v for k, v in legacy.items() if in_scope(k)}
    declared_base = declared_differences(ledger)

    class _Declared(dict):
        """Declared differences are keyed by node id without parameters, or by the
        exact parametrized node id when only one parameter differs."""
        def __contains__(self, node):
            return str(node) in declared_base or declared_base.__contains__(str(node).split("[", 1)[0])

        def __getitem__(self, node):
            if str(node) in declared_base:
                return declared_base[str(node)]
            return declared_base[str(node).split("[", 1)[0]]

    declared = _Declared()

    # 1. the collected node ids must be the same set
    missing = sorted(set(old) - set(mirror))
    extra = sorted(set(mirror) - set(old))
    for n in missing:
        if n not in declared:
            problems.append(f"collected by legacy, absent from the mirror: {n}")
    for n in extra:
        if n not in declared:
            problems.append(f"collected only by the mirror: {n}")

    # 2. outcomes must agree, after declared differences
    for node in sorted(set(old) & set(mirror)):
        a, b = old[node], mirror[node]
        if node in declared:
            want = declared[node]
            if (b.status, b.kind) != (want["mirror_status"], want.get("mirror_kind", "")):
                problems.append(
                    f"declared difference no longer holds: {node}: mirror is {b.status}/{b.kind}, "
                    f"ledger says {want['mirror_status']}/{want.get('mirror_kind', '')}")
            continue
        if a.status in ("failed", "error") or b.status in ("failed", "error"):
            if (a.status, a.kind, a.message) != (b.status, b.kind, b.message):
                problems.append(f"failure differs: {node}\n   legacy: {a}\n   mirror: {b}")
        elif (a.status == "skipped") != (b.status == "skipped"):
            problems.append(f"skip differs: {node}: legacy {a.status}, mirror {b.status}")

    # 3. every legacy failure, in or out of scope, must be a declared baseline failure
    baseline = {n for row in ledger["rows"] for n in row.get("baseline_failures", [])}
    for node, a in sorted(failing(legacy).items()):
        if node not in baseline:
            problems.append(f"undeclared legacy failure: {node}: {a}")
    for node in sorted(baseline):
        if node in legacy and legacy[node].status not in ("failed", "error"):
            problems.append(f"declared baseline failure now passes: {node}")
    return problems


def flaky_nodes(ledger: Mapping) -> dict[str, str]:
    """Function-level node id -> reason, for tests whose outcome depends on timing."""
    return {node: reason for row in ledger["rows"] for node, reason in row.get("flaky_nodes", {}).items()}


def rerun_flaky(suite: str, run: SuiteRun, flaky: Mapping[str, str], workdir: Path, *, mirror: bool,
                attempts: int = 2) -> list[str]:
    """Re-run the failing flaky nodes of one run, up to ``attempts`` times; return the nodes that recovered.

    A node counts as recovered only when its own re-run passes, so a defect that
    fails the test every time stays a failure. Only nodes the ledger lists as
    flaky are ever re-run, and the recovery is reported by the caller.
    """
    root = "tmp" if mirror else "tests"
    recovered: list[str] = []
    for attempt in range(attempts):
        pending = {n for n, o in failing(run.outcomes).items() if n.split("[", 1)[0] in flaky}
        if not pending:
            break
        targets = sorted({f"{root}/{n.split('[', 1)[0]}" for n in pending})
        junit = workdir / f"rerun-{'mirror' if mirror else 'legacy'}-{suite}-{attempt}.xml"
        run_pytest(targets[0], junit, mirror=mirror, extra_args=targets[1:])
        if not junit.is_file():
            break
        again = parse_junit(junit, suite)
        for node in sorted(pending):
            if again.get(node) is not None and again[node].status == "passed":
                run.outcomes[node] = again[node]
                recovered.append(node)
    return recovered


def compare_suite(suite: str, workdir: Path) -> tuple[list[str], SuiteRun, SuiteRun]:
    gen = load_generator()
    gen.cmd_mirror(None)
    legacy = run_suite(suite, workdir, mirror=False)
    mirror = run_suite(suite, workdir, mirror=True)
    ledger = load_ledger(suite)
    flaky = flaky_nodes(ledger)
    if flaky:
        for run, is_mirror in ((legacy, False), (mirror, True)):
            for node in rerun_flaky(suite, run, flaky, workdir, mirror=is_mirror):
                print(f"flaky node recovered on re-run ({'mirror' if is_mirror else 'legacy'}): {node}", file=sys.stderr)
    return compare(suite, legacy.outcomes, mirror.outcomes, ledger), legacy, mirror


def _main(argv: list[str]) -> int:
    import tempfile
    cmd, suite = argv[0], argv[1]
    workdir = Path(os.environ.get("REPOINT_WORKDIR") or tempfile.mkdtemp(prefix="repoint-"))
    if cmd == "compare":
        problems, legacy, mirror = compare_suite(suite, workdir)
        print(f"legacy: {legacy.summary}\nmirror: {mirror.summary}\nworkdir: {workdir}")
        for p in problems:
            print(p)
        print(f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if cmd == "mirror-only":
        load_generator().cmd_mirror(None)
        mirror = run_suite(suite, workdir, mirror=True)
        print(f"mirror: {mirror.summary}\nworkdir: {workdir}")
        for node, o in sorted(failing(mirror.outcomes).items()):
            print(f"{node}\n    {o.kind}: {o.message}")
        return 0
    raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
