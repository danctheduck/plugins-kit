"""Launcher target for ``bin/task-kit`` and ``bin/task-kit.cmd``.

Two copies of this file exist, and the same code serves both:

- In the plugin (the working copy, or the plugin cache), the dashboard code is
  beside it: ``../skills/task/scripts/task_system/dashboard``. It puts that
  scripts directory on ``sys.path``, moves into the plugin venv when it is not
  already there, and hands over to the dashboard launcher.
- In task-kit's data directory ``bin/`` (the copy bootstrap syncs there and
  puts on PATH, so ``task-kit`` works in any terminal) no dashboard code is
  beside it. The bundle is thin on purpose: it locates the newest installed
  task-kit version in the plugin cache at run time and runs THAT copy's
  entrypoint, so a plugin update needs no PATH or bundle change.

Stdlib only until the dashboard launcher is imported.
"""
from __future__ import annotations

import re
import runpy
import sys
from pathlib import Path

PLUGIN = "task-kit"
ENTRYPOINT_RELATIVE = ("bin", "task_kit_entrypoint.py")
SCRIPTS_RELATIVE = ("skills", "task", "scripts")
DASHBOARD_RELATIVE = SCRIPTS_RELATIVE + ("task_system", "dashboard")
_VERSION = re.compile(r"^\d+(?:\.\d+)*$")


def has_dashboard(root: Path) -> bool:
    """True when ``root`` is a task-kit plugin root that carries the dashboard."""
    return root.joinpath(*DASHBOARD_RELATIVE).is_dir()


def version_key(name: str) -> tuple[int, ...]:
    return tuple(int(part) for part in name.split("."))


def installed_plugin_root(bundle_root: Path) -> Path:
    """The newest task-kit version in the plugin cache, for a data-dir bundle.

    ``bundle_root`` is ``<plugins>/data/<marketplace>/task-kit``; the cache is
    its sibling tree ``<plugins>/cache/<marketplace>/task-kit/<version>``.
    """
    marketplace = bundle_root.parent.name
    data_root = bundle_root.parent.parent
    cache = data_root.parent / "cache" / marketplace / PLUGIN
    candidates = []
    if cache.is_dir():
        for entry in cache.iterdir():
            if (
                entry.is_dir()
                and _VERSION.match(entry.name)
                and has_dashboard(entry)
                and entry.joinpath(*ENTRYPOINT_RELATIVE).is_file()
            ):
                candidates.append((version_key(entry.name), entry))
    if not candidates:
        raise SystemExit(
            f"task-kit: no installed task-kit with the dashboard was found in {cache}. "
            f"Install or update the plugin ({marketplace}:{PLUGIN}) and start a new "
            "Claude Code session so bootstrap can provision it."
        )
    return max(candidates, key=lambda item: item[0])[1]


def main() -> int:
    here = Path(__file__).resolve()
    root = here.parent.parent
    if not has_dashboard(root):
        located = installed_plugin_root(root).joinpath(*ENTRYPOINT_RELATIVE)
        runpy.run_path(str(located), run_name="__main__")
        return 0
    scripts = root.joinpath(*SCRIPTS_RELATIVE)
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from bootstrap_guard import reexec_under_plugin_venv, require_bootstrap  # noqa: PLC0415

    reexec_under_plugin_venv(PLUGIN)
    try:
        from task_system.dashboard import launcher  # noqa: PLC0415
    except ImportError as exc:
        # The failed import is itself proof the provisioned venv (psutil, PyYAML,
        # the skills_kit_lib link) is not what is running; print the real error
        # first so an unrelated ImportError stays diagnosable.
        print(f"[task-kit] underlying error: {type(exc).__name__}: {exc}", file=sys.stderr)
        require_bootstrap(PLUGIN, feature="dashboard", missing="psutil/pyyaml/skills_kit_lib", force=True)
        return 3
    return launcher.main(sys.argv[1:], scripts_dir=scripts, entrypoint=here)


if __name__ == "__main__":
    raise SystemExit(main())
