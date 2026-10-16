"""Fixtures for pdf-kit tests."""

import os

# Entry points that call bootstrap_guard.reexec_under_plugin_venv() would
# os.execv the pytest process into the plugin venv on a provisioned machine and
# yield a false green. The skip variable makes the re-exec a no-op under tests;
# see plugins/CLAUDE.md, "Test gotcha".
os.environ.setdefault("_BOOTSTRAP_GUARD_SKIP_REEXEC", "1")
