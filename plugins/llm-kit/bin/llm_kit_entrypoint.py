"""Launcher target for ``bin/llm-kit`` and ``bin/llm-kit.cmd``.

This file has no logic of its own. It puts the plugin's bundled ``lib/`` on
``sys.path`` (so the package resolves from the copy beside the launcher, in
whichever interpreter the launcher chose, with no install step) and delegates to
:func:`llm_kit.cli.main`, which owns every group and, on a provisioned machine,
moves the process into the plugin venv when it is not already there.
"""
from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


def _run() -> int:
    from llm_kit.cli import main  # noqa: PLC0415 -- after the sys.path edit above

    return main()


if __name__ == "__main__":
    raise SystemExit(_run())
