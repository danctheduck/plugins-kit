#!/usr/bin/env python3
"""Generate llm-kit's quarantined copy and the re-pointed legacy test mirror.

Maintainer tool for the llm-kit consolidation; it reads three legacy plugin
trees and writes (a) ``plugins/llm-kit/lib/llm_kit/_copy/**`` and (b) the
ignored in-repo mirror under ``tmp/`` that the old-versus-copy differential
runs. The legacy trees are never written.

Commands (run from the repository root, ``uv run --extra dev python <this file>
<command>``; ``sync`` collects the legacy suites, so pytest must be importable):

``sync``      Refresh the copy, the hash table in ``tests/llm-kit/repoint-map.json``
              and the collection counts in the disposition ledgers. A module that
              has moved (``state`` other than ``unmoved``) is never overwritten and a
              legacy edit after its move is refused unless the porting ledger
              records it.
``mirror``    Regenerate only the mirror under ``tmp/``.
``clean``     Remove the mirror under tmp/ (the files this tool wrote, nothing else).
``check``     Exit 1 when the copy, the map or the ledgers disagree with the legacy
              trees (what ``tests/llm-kit/test_copy_inventory.py`` asserts).
``propose``   Print map entries for runtime-string sites not yet classified.

The rewrite is mechanical and parsed, never a blind text replace: absolute
imports are rewritten from the syntax tree, runtime-string sites only where the
map classifies them, and test strings and paths only in the shapes listed in
``rewrite_test_source``.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "tests" / "llm-kit" / "repoint-map.json"
DISPOSITIONS_DIR = REPO / "tests" / "llm-kit" / "repoint-dispositions"
PORTING_LEDGER = REPO / "tests" / "llm-kit" / "porting-ledger.json"
COPY_ROOT = REPO / "plugins" / "llm-kit" / "lib" / "llm_kit" / "_copy"
LLM_KIT_LIB = REPO / "plugins" / "llm-kit" / "lib"
MIRROR_ROOT = REPO / "tmp"
GUARD_MODULE = "llm_kit.bootstrap_guard"
SUITES = ("llm-scripting-kit", "content-pipeline-kit", "job-kit")
DISPOSITIONS = ("rewrite", "legacy-only", "deferred-to-I9")
SITE_ACTIONS = ("rewrite", "keep-human")

_ROOT_ALT = "llm_scripting_kit|content_pipeline|job_kit"


def _read(path: Path) -> bytes:
    """File bytes with CRLF folded to LF.

    The repository pins LF in the index (.gitattributes), but a working tree
    checked out under another setting can hold CRLF. Every hash and rewrite is
    taken over the LF form so the copy, its hashes and the mirror do not depend
    on the checkout that produced them.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    text = json.dumps(data, indent=2, sort_keys=False, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("ascii"))


def git_files(*paths: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", *paths],
        cwd=REPO, capture_output=True, check=True,
    ).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p)


# --------------------------------------------------------------------------
# map access
# --------------------------------------------------------------------------

def roots(mapping: Mapping) -> dict[str, str]:
    """legacy package name -> copy dotted name."""
    return {name: spec["copy"] for name, spec in mapping["packages"].items()}


def token_re(names: Iterable[str]) -> "re.Pattern[str]":
    alt = "|".join(sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w.\\/-])({alt})(?![\w\\/-])")


# --------------------------------------------------------------------------
# source positions
# --------------------------------------------------------------------------

def _line_starts(data: bytes) -> list[int]:
    starts = [0]
    for i, b in enumerate(data):
        if b == 0x0A:
            starts.append(i + 1)
    return starts


def _span(starts: list[int], node: ast.AST) -> tuple[int, int]:
    return (
        starts[node.lineno - 1] + node.col_offset,
        starts[node.end_lineno - 1] + node.end_col_offset,
    )


def apply_edits(data: bytes, edits: list[tuple[int, int, bytes]]) -> bytes:
    out = data
    last = len(data) + 1
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        if end > last:
            raise ValueError("overlapping edits")
        out = out[:start] + repl + out[end:]
        last = start
    return out


# --------------------------------------------------------------------------
# string constants
# --------------------------------------------------------------------------

def _prose_ids(tree: ast.AST) -> set[int]:
    """Constants that are bare expression statements: docstrings and attribute docs."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                ids.add(id(node.value))
    return ids


def string_constants(tree: ast.AST) -> list[ast.Constant]:
    prose = _prose_ids(tree)
    found = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in prose
    ]
    found.sort(key=lambda n: (n.lineno, n.col_offset))
    return found


def site_key(relpath: str, value: str, ordinal: int) -> str:
    return f"{relpath}::{hashlib.sha1(value.encode('utf-8')).hexdigest()[:10]}::{ordinal}"


def string_sites(relpath: str, tree: ast.AST, names: Iterable[str]) -> list[tuple[str, ast.Constant]]:
    """(key, node) for each non-prose string constant that names a legacy root."""
    pattern = re.compile(rf"\b({'|'.join(names)})\b")
    seen: dict[str, int] = {}
    out = []
    for node in string_constants(tree):
        if not pattern.search(node.value):
            continue
        n = seen.get(node.value, 0)
        seen[node.value] = n + 1
        out.append((site_key(relpath, node.value, n), node))
    return out


# --------------------------------------------------------------------------
# import rewriting (shared by the copy and the tests)
# --------------------------------------------------------------------------

def _stmt_segment(data: bytes, starts: list[int], node: ast.AST) -> tuple[int, int, bytes]:
    s, e = _span(starts, node)
    return s, e, data[s:e]


def _alias_text(alias: ast.alias) -> str:
    return alias.name + (f" as {alias.asname}" if alias.asname else "")


def rewrite_import_node(node: ast.AST, seg: bytes, rt: Mapping[str, str],
                        dropped_rel: Optional[set[str]] = None) -> Optional[bytes]:
    """Return replacement bytes for one import statement, or None to keep it."""
    if isinstance(node, ast.Import):
        if not any(a.name.split(".")[0] in rt or a.name == "bootstrap_guard" for a in node.names):
            return None
        pieces: list[str] = []
        bound: set[str] = set()
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in rt:
                rest = alias.name[len(top):]
                target = rt[top]
                if alias.asname:
                    pieces.append(f"import {target}{rest} as {alias.asname}")
                elif not rest:
                    pieces.append(f"import {target} as {top}")
                    bound.add(top)
                else:
                    pieces.append(f"import {target}{rest}")
                    if top not in bound:
                        pieces.append(f"import {target} as {top}")
                        bound.add(top)
            elif alias.name == "bootstrap_guard":
                pieces.append(
                    f"from llm_kit import bootstrap_guard"
                    + (f" as {alias.asname}" if alias.asname else "")
                )
            else:
                pieces.append(f"import {_alias_text(alias)}")
        return "; ".join(pieces).encode("utf-8")
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        top = module.split(".")[0]
        if node.level and dropped_rel is not None and module in dropped_rel:
            m = re.match(rb"(from\s+)\.+" + re.escape(module.encode()) + rb"(\s+import\b)", seg)
            if m is None:
                raise ValueError("unexpected relative import shape: " + seg[:80].decode())
            return m.group(1) + GUARD_MODULE.encode() + seg[m.end(1) + node.level + len(module):]
        if node.level:
            return None
        if top == "bootstrap_guard" and module == "bootstrap_guard":
            m = re.match(rb"(from\s+)bootstrap_guard(\s+import\b)", seg)
            if m is None:
                raise ValueError("unexpected guard import shape")
            return m.group(1) + GUARD_MODULE.encode() + seg[m.end(1) + len("bootstrap_guard"):]
        if top not in rt:
            return None
        # `from llm_scripting_kit import completion, bootstrap_guard` splits.
        if module == top and any(a.name == "bootstrap_guard" for a in node.names):
            keep = [a for a in node.names if a.name != "bootstrap_guard"]
            guard = [a for a in node.names if a.name == "bootstrap_guard"][0]
            parts = []
            if keep:
                parts.append(f"from {rt[top]} import " + ", ".join(_alias_text(a) for a in keep))
            parts.append(
                "from llm_kit import bootstrap_guard"
                + (f" as {guard.asname}" if guard.asname else "")
            )
            return "; ".join(parts).encode("utf-8")
        m = re.match(rb"(from\s+)" + re.escape(module.encode()) + rb"(\s+import\b)", seg)
        if m is None:
            raise ValueError("unexpected from-import shape: " + seg[:80].decode())
        new_module = (rt[top] + module[len(top):]).encode()
        return m.group(1) + new_module + seg[m.end(1) + len(module):]
    return None


def rewrite_imports(data: bytes, tree: ast.AST, rt: Mapping[str, str],
                    dropped_rel: Optional[set[str]] = None) -> tuple[bytes, int]:
    starts = _line_starts(data)
    edits: list[tuple[int, int, bytes]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            s, e, seg = _stmt_segment(data, starts, node)
            repl = rewrite_import_node(node, seg, rt, dropped_rel)
            if repl is not None and repl != seg:
                edits.append((s, e, repl))
    return apply_edits(data, edits), len(edits)


# --------------------------------------------------------------------------
# the copy
# --------------------------------------------------------------------------

def legacy_package_files(mapping: Mapping) -> list[dict]:
    """Every tracked file of the three legacy packages with its copy disposition."""
    rows = []
    for name, spec in mapping["packages"].items():
        for path in git_files(spec["source_dir"]):
            rel_in_pkg = path[len(spec["source_dir"]) + 1:]
            base = os.path.basename(path)
            if path in mapping["dropped"]:
                state = "dropped"
            elif path in mapping["excluded"]:
                state = "excluded"
            elif base.endswith(".py") or base in mapping["data_files"]:
                state = "copy"
            else:
                raise SystemExit(
                    f"unclassified legacy package file: {path} (add it to "
                    f"'excluded' or 'dropped' in {MAP_PATH.name})"
                )
            rows.append({
                "legacy": path, "package": name, "state": state,
                "copy": (spec["copy_dir"] + "/" + rel_in_pkg) if state == "copy" else None,
            })
    return rows


def dropped_relative_modules(mapping: Mapping, legacy_path: str) -> set[str]:
    """Sibling module names (relative-import spelling) dropped from this file's package."""
    pkg_dir = legacy_path.rsplit("/", 1)[0]
    out = set()
    for dropped in mapping["dropped"]:
        if dropped.rsplit("/", 1)[0] == pkg_dir:
            out.add(os.path.basename(dropped)[:-3])
    return out


def rewrite_lib_source(data: bytes, legacy_path: str, mapping: Mapping) -> bytes:
    """The copy of one legacy module: parsed import rewrite plus classified string sites."""
    rt = roots(mapping)
    tree = ast.parse(data.decode("utf-8"))
    starts = _line_starts(data)
    dropped_rel = dropped_relative_modules(mapping, legacy_path)
    edits: list[tuple[int, int, bytes]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            s, e, seg = _stmt_segment(data, starts, node)
            repl = rewrite_import_node(node, seg, rt, dropped_rel)
            if repl is not None and repl != seg:
                edits.append((s, e, repl))
    wanted = mapping_sites_for(legacy_path, mapping)
    token = token_re(rt.keys())
    for key, node in string_sites(legacy_path, tree, rt.keys()):
        entry = wanted.get(key)
        if entry is not None and entry["action"] == "rewrite":
            s, e = _span(starts, node)
            seg = data[s:e].decode("utf-8")
            edits.append((s, e, token.sub(lambda m: rt[m.group(1)], seg).encode("utf-8")))
    return apply_edits(data, edits)


def mapping_sites_for(legacy_path: str, mapping: Mapping) -> dict[str, dict]:
    return {k: v for k, v in mapping["string_sites"].items() if v["file"] == legacy_path}


def unclassified_sites(mapping: Mapping) -> list[tuple[str, str, str]]:
    """(key, file, preview) for each runtime-string site the map does not classify."""
    rt = roots(mapping)
    out = []
    for row in legacy_package_files(mapping):
        if row["state"] != "copy" or not row["legacy"].endswith(".py"):
            continue
        data = _read(REPO / row["legacy"])
        tree = ast.parse(data.decode("utf-8"))
        for key, node in string_sites(row["legacy"], tree, rt.keys()):
            if key not in mapping["string_sites"]:
                out.append((key, row["legacy"], node.value[:70].replace("\n", " ")))
    return out


def stale_sites(mapping: Mapping) -> list[str]:
    rt = roots(mapping)
    live: set[str] = set()
    for row in legacy_package_files(mapping):
        if row["state"] != "copy" or not row["legacy"].endswith(".py"):
            continue
        tree = ast.parse(_read(REPO / row["legacy"]).decode("utf-8"))
        live.update(k for k, _ in string_sites(row["legacy"], tree, rt.keys()))
    return sorted(set(mapping["string_sites"]) - live)


def remaining_legacy_imports(data: bytes, rt: Mapping[str, str]) -> list[str]:
    """Absolute imports of a legacy root still present in a copied module."""
    tree = ast.parse(data.decode("utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names
                      if a.name.split(".")[0] in rt or a.name == "bootstrap_guard"]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            if node.module.split(".")[0] in rt or node.module == "bootstrap_guard":
                found.append(node.module)
    return found


def build_copy(mapping: Mapping) -> dict[str, bytes]:
    """copy path (repo-relative) -> bytes, for every copied module."""
    files: dict[str, bytes] = {}
    for row in legacy_package_files(mapping):
        if row["state"] != "copy":
            continue
        data = _read(REPO / row["legacy"])
        if row["legacy"].endswith(".py"):
            data = rewrite_lib_source(data, row["legacy"], mapping)
        files[row["copy"]] = data
    return files


def existing_copy_files() -> list[str]:
    if not COPY_ROOT.is_dir():
        return []
    out = []
    for p in COPY_ROOT.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            out.append(p.relative_to(REPO).as_posix())
    return sorted(out)


def package_initializers(mapping: Mapping) -> list[str]:
    return [(COPY_ROOT / "__init__.py").relative_to(REPO).as_posix()]


def write_copy(mapping: Mapping, files: Mapping[str, bytes]) -> None:
    moved = {m["copy"] for m in mapping["modules"].values() if m["state"] != "unmoved"}
    for rel, data in files.items():
        if rel in moved:
            continue
        target = REPO / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (COPY_ROOT / "__init__.py").write_bytes(b"")
    wanted = set(files) | set(package_initializers(mapping))
    for rel in existing_copy_files():
        if rel not in wanted and rel not in moved:
            (REPO / rel).unlink()
    for d in sorted((p for p in COPY_ROOT.rglob("*") if p.is_dir()), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


# --------------------------------------------------------------------------
# the mirror
# --------------------------------------------------------------------------

_PLUGIN_DIR_RE_TMPL = (
    r"(?P<q1>[\"'])plugins(?P=q1)(?P<sep>\s*(?:/|,)\s*)"
    r"(?P<q2>[\"'])(?P<name>{names})(?P=q2)"
)
_LIB_PKG_RE = re.compile(
    r"(?P<q1>[\"'])lib(?P=q1)(?P<sep>\s*(?:/|,)\s*)(?P<q2>[\"'])"
    rf"(?P<pkg>{_ROOT_ALT})(?P=q2)"
)
_SLASH_PATH_RE = re.compile(
    rf"plugins/(?P<plugin>llm-scripting-kit|content-pipeline-kit|job-kit)/lib(?P<rest>/(?P<pkg>{_ROOT_ALT})\b)?"
)


def _code_like(value: str) -> bool:
    return bool(re.search(r"(^|\n)\s*(import|from)\s+\w", value)) or "sys.modules" in value \
        or "run_module(" in value or "import_module(" in value


def _is_module_name(value: str, names: Iterable[str]) -> bool:
    return re.fullmatch(rf"({'|'.join(names)})(\.\w+)*\.?", value) is not None


_CODE_IMPORT_RE = re.compile(
    rf"^(?P<ind>[ \t]*)import[ \t]+(?P<top>{_ROOT_ALT})(?P<rest>(?:\.\w+)*)(?P<alias>[ \t]+as[ \t]+\w+)?[ \t]*$",
    re.M,
)


def rewrite_code_string(seg: str, rt: Mapping[str, str]) -> str:
    """Rewrite module names inside a code string's source text."""
    def import_stmt(m: "re.Match[str]") -> str:
        top, rest, alias = m.group("top"), m.group("rest"), m.group("alias") or ""
        target = rt[top]
        if alias:
            return f"{m.group('ind')}import {target}{rest}{alias}"
        if not rest:
            return f"{m.group('ind')}import {target} as {top}"
        return f"{m.group('ind')}import {target}{rest}; import {target} as {top}"

    seg = _CODE_IMPORT_RE.sub(import_stmt, seg)
    token = token_re(rt.keys())
    seg = token.sub(lambda m: rt[m.group(1)], seg)
    seg = re.sub(r"(?m)^([ \t]*)from[ \t]+bootstrap_guard[ \t]+import\b",
                 lambda m: f"{m.group(1)}from {GUARD_MODULE} import", seg)
    seg = re.sub(r"(?m)^([ \t]*)import[ \t]+bootstrap_guard[ \t]*$",
                 lambda m: f"{m.group(1)}from llm_kit import bootstrap_guard", seg)
    return seg


_PATH_CALLS = {"join", "joinpath", "Path", "PurePath", "PurePosixPath", "PureWindowsPath"}


def _is_path_segment(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
    """True for a string literal used as one component of a filesystem path."""
    parent = parents.get(node)
    if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div):
        return True
    if isinstance(parent, ast.Call):
        func = parent.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        return name in _PATH_CALLS and node in parent.args
    return False


def _qualnames(tree: ast.AST) -> dict[str, ast.AST]:
    """qualified name ("Class.test" or "test") -> function node, for tests."""
    out: dict[str, ast.AST] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[f"{prefix}{child.name}"] = child
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


def rewrite_test_source(data: bytes, relpath: str, mapping: Mapping,
                        skips: Optional[Mapping[str, str]] = None) -> tuple[bytes, list[str]]:
    """Re-point one legacy test file at the copy. Returns (bytes, rewrite classes).

    One pass over the original syntax tree collects every edit (imports, module
    and code strings); a second regex pass rewrites the path shapes. A string
    that is a path component, or prose, is never treated as a module name.
    """
    rt = roots(mapping)
    classes: set[str] = set()
    tree = ast.parse(data.decode("utf-8"))
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    starts = _line_starts(data)
    edits: list[tuple[int, int, bytes]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            s, e, seg = _stmt_segment(data, starts, node)
            repl = rewrite_import_node(node, seg, rt)
            if repl is not None and repl != seg:
                edits.append((s, e, repl))
                classes.add("import")

    overrides = mapping.get("test_site_overrides", {})
    seen: dict[str, int] = {}
    pattern = re.compile(rf"\b({_ROOT_ALT}|bootstrap_guard)\b")
    for node in string_constants(tree):
        value = node.value
        if not pattern.search(value):
            continue
        n = seen.get(value, 0)
        seen[value] = n + 1
        override = overrides.get(site_key(relpath, value, n))
        if override is not None and override["action"] == "keep":
            classes.add("string-kept")
            continue
        forced = override is not None and override["action"] == "rewrite"
        if not forced and _is_path_segment(node, parents):
            continue
        module_like = _is_module_name(value, rt.keys())
        code_like = _code_like(value)
        if not (forced or module_like or code_like):
            classes.add("prose-kept")
            continue
        s, e = _span(starts, node)
        seg = data[s:e].decode("utf-8")
        new_seg = rewrite_code_string(seg, rt)
        if new_seg != seg:
            edits.append((s, e, new_seg.encode("utf-8")))
            classes.add("code-string" if code_like else "module-string" if module_like else "named-message")
    if skips:
        defs = _qualnames(tree)
        for qual, reason in skips.items():
            node = defs.get(qual)
            if node is None:
                raise SystemExit(f"{relpath}: declared skip names no test: {qual}")
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            at = starts[first - 1]
            indent = " " * (node.col_offset)
            line = f'{indent}@__import__("pytest").mark.skip(reason={json.dumps(reason)})\n'
            edits.append((at, at, line.encode("utf-8")))
        classes.add("declared-skip")
    text = apply_edits(data, edits).decode("utf-8")

    plugin_names = "|".join(re.escape(spec["plugin"]) for spec in mapping["packages"].values())
    plugin_re = re.compile(_PLUGIN_DIR_RE_TMPL.format(names=plugin_names))

    def plugin_dir(m: "re.Match[str]") -> str:
        classes.add("path-plugin-dir")
        return f"{m.group('q1')}plugins{m.group('q1')}{m.group('sep')}{m.group('q2')}llm-kit{m.group('q2')}"

    text = plugin_re.sub(plugin_dir, text)

    def lib_pkg(m: "re.Match[str]") -> str:
        classes.add("path-package-dir")
        sep, q1, q2 = m.group("sep"), m.group("q1"), m.group("q2")
        parts = ["llm_kit", "_copy", m.group("pkg")]
        return f"{q1}lib{q1}" + "".join(f"{sep}{q2}{p}{q2}" for p in parts)

    text = _LIB_PKG_RE.sub(lib_pkg, text)

    def slash_path(m: "re.Match[str]") -> str:
        classes.add("path-string")
        if m.group("pkg"):
            return f"plugins/llm-kit/lib/llm_kit/_copy/{m.group('pkg')}"
        return "plugins/llm-kit/lib"

    text = _SLASH_PATH_RE.sub(slash_path, text)
    return text.encode("utf-8"), sorted(classes)


def render_sitecustomize(mapping: Mapping) -> str:
    legacy_libs = sorted({
        spec["lib_dir"] for spec in mapping["packages"].values()
    })
    legacy_plugins = sorted({spec["plugin_dir"] for spec in mapping["packages"].values()})
    tops = sorted(list(mapping["packages"]) + ["job_kit_entrypoint"])
    return _SITECUSTOMIZE.format(
        repo=str(REPO).replace("\\", "/"),
        mirror=str(MIRROR_ROOT).replace("\\", "/"),
        libs=json.dumps(legacy_libs),
        plugins=json.dumps(legacy_plugins),
        tops=json.dumps(tops),
    )


_SITECUSTOMIZE = '''\
"""Import-root enforcement for the re-pointed legacy test mirror (generated).

Loaded by the parent pytest process and by every child interpreter that
inherits the mirror directory on PYTHONPATH. It rejects the three legacy
top-level packages and any legacy plugin directory on sys.path, and it keeps
the mirror directory on PYTHONPATH of every child process, including children
launched with an explicit environment.
"""
import importlib.abc
import os
import subprocess
import sys

_REPO = {repo!r}
_MIRROR = {mirror!r}
_LEGACY_LIBS = {libs}
_LEGACY_PLUGINS = {plugins}
_LEGACY_TOPS = frozenset({tops})


def _norm(path):
    try:
        return os.path.normcase(os.path.abspath(path)).replace("\\\\", "/")
    except (TypeError, ValueError):
        return ""


_LEGACY_PREFIXES = tuple(_norm(os.path.join(_REPO, p)) for p in _LEGACY_PLUGINS)
_MIRROR_NORM = _norm(_MIRROR)


def _is_legacy_path(path):
    n = _norm(path)
    return any(n == p or n.startswith(p + "/") for p in _LEGACY_PREFIXES)


def _scan_sys_path():
    for entry in sys.path:
        if entry and _is_legacy_path(entry):
            raise ImportError("legacy plugin directory on sys.path in a mirrored run: " + entry)


class _LegacyBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] in _LEGACY_TOPS:
            raise ImportError("legacy package imported in a mirrored run: " + fullname,
                              name=fullname)
        _scan_sys_path()
        return None


if not any(isinstance(f, _LegacyBlocker) for f in sys.meta_path):
    sys.meta_path.insert(0, _LegacyBlocker())


def _guard_value(value, where):
    text = os.fspath(value) if isinstance(value, os.PathLike) else value
    if not isinstance(text, str):
        return
    for part in text.split(os.pathsep):
        if part and _is_legacy_path(part):
            raise RuntimeError("legacy plugin path handed to a child process (" + where + "): " + part)


_orig_init = subprocess.Popen.__init__


def _patched_init(self, args, *a, **kw):
    argv = [args] if isinstance(args, (str, bytes, os.PathLike)) else list(args)
    for item in argv:
        if isinstance(item, (str, os.PathLike)):
            _guard_value(item, "argv")
    env = kw.get("env")
    if env is not None:
        env = dict(env)
        current = env.get("PYTHONPATH", "")
        _guard_value(current, "PYTHONPATH")
        parts = [p for p in current.split(os.pathsep) if p]
        if not any(_norm(p) == _MIRROR_NORM for p in parts):
            parts.append(_MIRROR)
        env["PYTHONPATH"] = os.pathsep.join(parts)
        kw["env"] = env
    _orig_init(self, args, *a, **kw)


if not getattr(subprocess.Popen.__init__, "_mirror_patched", False):
    _patched_init._mirror_patched = True
    subprocess.Popen.__init__ = _patched_init
'''


def mirror_rows(dispositions: Mapping[str, Mapping]) -> list[dict]:
    return [r for led in dispositions.values() for r in led["rows"] if r["disposition"] == "rewrite"]


def load_dispositions() -> dict[str, dict]:
    out = {}
    for suite in SUITES:
        path = DISPOSITIONS_DIR / f"{suite}.json"
        out[suite] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
            "suite": suite, "rows": []}
    return out


def build_mirror(mapping: Mapping, dispositions: Mapping[str, Mapping]) -> dict[str, tuple[bytes, list[str]]]:
    """mirror path (relative to MIRROR_ROOT) -> (bytes, classes)."""
    files: dict[str, tuple[bytes, list[str]]] = {}
    for suite in SUITES:
        led = dispositions[suite]
        for row in led["rows"]:
            if row["disposition"] != "rewrite":
                continue
            src = REPO / row["path"]
            rel = f"{suite}/{src.name}"
            skips = {}
            for node_id, entry in row.get("declared_differences", {}).items():
                if entry["mirror_status"] == "skipped" and entry.get("injected", True):
                    nested = node_id.split("::", 1)[1].split("[")[0].replace("::", ".")
                    skips[nested] = entry["reason"]
            files[rel] = rewrite_test_source(_read(src), row["path"], mapping, skips)
        conftest = REPO / "tests" / suite / "conftest.py"
        files[f"{suite}/conftest.py"] = rewrite_test_source(
            _read(conftest), f"tests/{suite}/conftest.py", mapping)
    files["conftest.py"] = (_read(REPO / "tests" / "conftest.py"), [])
    for p in sorted((REPO / "tests" / "test_support").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            files["test_support/" + p.relative_to(REPO / "tests" / "test_support").as_posix()] = (
                _read(p), [])
    files["sitecustomize.py"] = (render_sitecustomize(mapping).encode("utf-8"), [])
    return files


def write_mirror(files: Mapping[str, tuple[bytes, list[str]]]) -> None:
    """Write the mirror idempotently: unchanged files are left alone and stale
    ones removed, so concurrent callers (parallel test workers) never see a
    half-deleted tree."""
    for rel, (data, _classes) in files.items():
        target = MIRROR_ROOT / rel
        if target.is_file() and target.read_bytes() == data:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    wanted = {MIRROR_ROOT / rel for rel in files}
    for managed in [MIRROR_ROOT / s for s in SUITES] + [MIRROR_ROOT / "test_support"]:
        if not managed.is_dir():
            continue
        for path in managed.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path not in wanted:
                path.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# sync / check
# --------------------------------------------------------------------------

def module_table(mapping: Mapping, files: Mapping[str, bytes]) -> dict[str, dict]:
    old = mapping.get("modules", {})
    table: dict[str, dict] = {}
    for row in legacy_package_files(mapping):
        if row["state"] != "copy":
            continue
        prior = old.get(row["legacy"], {})
        state = prior.get("state", "unmoved")
        legacy_hash = _sha(_read(REPO / row["legacy"]))
        if state != "unmoved":
            copy_hash = prior["copy_sha256"]
            if prior["legacy_sha256"] != legacy_hash:
                recorded = json.loads(PORTING_LEDGER.read_text(encoding="utf-8")) \
                    if PORTING_LEDGER.is_file() else {"entries": []}
                if not any(e["legacy_path"] == row["legacy"] and e["legacy_sha256"] == legacy_hash
                           for e in recorded["entries"]):
                    raise SystemExit(
                        f"{row['legacy']}: legacy edited after the module moved; record it in "
                        f"{PORTING_LEDGER.name} (ported or rejected with evidence)")
                legacy_hash = prior["legacy_sha256"]
        else:
            copy_hash = _sha(files[row["copy"]])
        table[row["legacy"]] = {
            "copy": row["copy"], "state": state,
            "legacy_sha256": legacy_hash, "copy_sha256": copy_hash,
        }
    return table


def collect_counts(suite: str) -> dict[str, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"tests/{suite}", "--collect-only", "-q",
         "-pno:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    counts: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        if "::" in line and line.startswith("tests/"):
            path = line.split("::", 1)[0]
            counts[path] = counts.get(path, 0) + 1
    if proc.returncode not in (0,):
        raise SystemExit(f"collection of tests/{suite} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    return counts


def cmd_sync(args: argparse.Namespace) -> int:
    mapping = load_map()
    missing = unclassified_sites(mapping)
    if missing:
        for key, file, preview in missing:
            print(f"unclassified runtime-string site: {file}: {preview!r} ({key})", file=sys.stderr)
        print("run 'propose' and classify them in repoint-map.json", file=sys.stderr)
        return 1
    files = build_copy(mapping)
    mapping["modules"] = module_table(mapping, files)
    write_copy(mapping, files)
    dump_json(MAP_PATH, mapping)
    dispositions = load_dispositions()
    if not args.no_counts:
        for suite in SUITES:
            counts = collect_counts(suite)
            led = dispositions[suite]
            known = {r["path"] for r in led["rows"]}
            for path in sorted(counts):
                if path not in known:
                    led["rows"].append({
                        "path": path, "disposition": "rewrite", "reason": "",
                        "rewrite_classes": [], "collection_count": 0, "baseline_failures": [],
                    })
            for row in led["rows"]:
                row["collection_count"] = counts.get(row["path"], 0)
            led["rows"].sort(key=lambda r: r["path"])
            led["collection_total"] = sum(r["collection_count"] for r in led["rows"])
    mirror = build_mirror(mapping, dispositions)
    for suite in SUITES:
        for row in dispositions[suite]["rows"]:
            if row["disposition"] == "rewrite":
                src = REPO / row["path"]
                row["rewrite_classes"] = mirror[f"{suite}/{src.name}"][1]
            else:
                row["rewrite_classes"] = []
        dump_json(DISPOSITIONS_DIR / f"{suite}.json", dispositions[suite])
    write_mirror(mirror)
    print(f"copy: {len(files)} files; mirror: {len(mirror)} files")
    return 0


def cmd_clean(_args: argparse.Namespace) -> int:
    """Remove exactly the files the mirror owns under tmp/."""
    for suite in SUITES:
        shutil.rmtree(MIRROR_ROOT / suite, ignore_errors=True)
    shutil.rmtree(MIRROR_ROOT / "test_support", ignore_errors=True)
    for name in ("conftest.py", "sitecustomize.py"):
        (MIRROR_ROOT / name).unlink(missing_ok=True)
    return 0


def cmd_mirror(_args: argparse.Namespace) -> int:
    mapping = load_map()
    write_mirror(build_mirror(mapping, load_dispositions()))
    return 0


def check_problems() -> list[str]:
    """Disagreements between the legacy trees, the map and the committed copy."""
    mapping = load_map()
    problems: list[str] = []
    for key, file, preview in unclassified_sites(mapping):
        problems.append(f"unclassified runtime-string site {file}: {preview!r}")
    for key in stale_sites(mapping):
        problems.append(f"map classifies a runtime-string site that no longer exists: {key}")
    files = build_copy(mapping)
    table = mapping.get("modules", {})
    for row in legacy_package_files(mapping):
        if row["state"] != "copy":
            continue
        entry = table.get(row["legacy"])
        if entry is None:
            problems.append(f"module missing from the map: {row['legacy']}")
            continue
        legacy_hash = _sha(_read(REPO / row["legacy"]))
        copy_path = REPO / row["copy"]
        if entry["state"] == "unmoved":
            if legacy_hash != entry["legacy_sha256"]:
                problems.append(f"legacy module edited since the last sync: {row['legacy']}")
            if not copy_path.is_file():
                problems.append(f"copy missing: {row['copy']}")
            elif _sha(_read(copy_path)) != _sha(files[row["copy"]]):
                problems.append(f"copy differs from its generated form: {row['copy']}")
        else:
            if not copy_path.is_file():
                problems.append(f"moved module missing: {row['copy']}")
            elif _sha(_read(copy_path)) != entry["copy_sha256"]:
                problems.append(f"moved module changed without a map update: {row['copy']}")
    wanted = {r["copy"] for r in legacy_package_files(mapping) if r["state"] == "copy"}
    wanted |= set(package_initializers(mapping))
    for rel in existing_copy_files():
        if rel not in wanted:
            problems.append(f"stray file in the copy: {rel}")
    for legacy in table:
        if legacy not in {r["legacy"] for r in legacy_package_files(mapping)}:
            problems.append(f"map lists a module the legacy tree no longer has: {legacy}")
    return problems


def cmd_check(_args: argparse.Namespace) -> int:
    problems = check_problems()
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


def cmd_propose(_args: argparse.Namespace) -> int:
    mapping = load_map()
    rt = roots(mapping)
    out = {}
    for key, file, preview in unclassified_sites(mapping):
        tree = ast.parse(_read(REPO / file).decode("utf-8"))
        node = dict(string_sites(file, tree, rt.keys()))[key]
        pure = _is_module_name(node.value, rt.keys()) or re.fullmatch(r"(-m|[\w.]+)", node.value)
        out[key] = {
            "file": file, "preview": node.value[:80].replace("\n", " "),
            "action": "rewrite" if pure else "keep-human",
            "reason": "module loader or argv target" if pure else "human-facing text",
        }
    print(json.dumps(out, indent=2))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sync", help="refresh copy, hashes, counts and mirror")
    p.add_argument("--no-counts", action="store_true", help="skip pytest collection counts")
    p.set_defaults(func=cmd_sync)
    sub.add_parser("mirror", help="regenerate the mirror only").set_defaults(func=cmd_mirror)
    sub.add_parser("clean", help="remove the mirror under tmp/").set_defaults(func=cmd_clean)
    sub.add_parser("check", help="verify copy and map against the legacy trees").set_defaults(func=cmd_check)
    sub.add_parser("propose", help="print unclassified string sites").set_defaults(func=cmd_propose)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
