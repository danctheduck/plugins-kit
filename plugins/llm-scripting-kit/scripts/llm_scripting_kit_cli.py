"""Compatibility launcher for the installed :mod:`llm_scripting_kit.cli`.

This file has no logic of its own -- it exists so ``bin/llm-scripting-kit``
(and its Windows ``.cmd`` twin) has a stable, interpreter-agnostic script path
to invoke. It puts the plugin's bundled ``lib/`` on ``sys.path`` (so the
package resolves without an install step) and delegates straight to
:func:`llm_scripting_kit.cli.main`, which owns every subcommand -- ``status``,
``set-key``, ``which``, ``endpoints``, ``probe``, ``usage``, ``choose``,
``seats``, ``models``, ``resolve``, ``complete`` (with ``--requirements`` and multi-entry
``--models`` fallback), and ``request-schema``.
See ``README.md`` for the full verb set and exit-code contract.

Runs under the plugin venv when bootstrap has provisioned it (PyYAML there lets
the layered config.yaml be read), and degrades to stdlib-only otherwise: without
PyYAML the shipped model baseline is used and a warning goes to stderr, but key
management keeps working. The shims in ``bin/`` pick the interpreter.
"""

import sys
from pathlib import Path

# Make the bundled lib/ importable when invoked directly.
_HERE = Path(__file__).resolve().parent
_LIB_DIR = _HERE.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


if __name__ == "__main__":
    # Guard before the package CLI is imported: under a redirected data root the
    # process moves into the redirected plugin venv (or exits 2 when it is
    # missing) before any of the CLI's own imports run. Same argv rewrite and
    # reason as llm_scripting_kit.cli.main; see the comment there.
    from llm_scripting_kit.bootstrap_guard import reexec_under_plugin_venv

    _entry_argv = list(sys.argv)
    sys.argv = ["-m", "llm_scripting_kit.cli", *_entry_argv[1:]]
    try:
        reexec_under_plugin_venv("llm-scripting-kit")
    finally:
        sys.argv = _entry_argv

    from llm_scripting_kit.cli import main as package_main

    sys.exit(package_main())
