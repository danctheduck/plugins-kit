import os
import sys

import pytest

from wk_testlib import PLUGIN_ROOT

# Scripts that call bootstrap_guard.reexec_under_plugin_venv() would os.execv the
# pytest process into the plugin venv on a provisioned machine and yield a false
# green. The skip variable makes the re-exec a no-op under tests; see
# plugins/CLAUDE.md, "Test gotcha".
os.environ.setdefault("_BOOTSTRAP_GUARD_SKIP_REEXEC", "1")

# Make workflow_kit_lib importable when these tests run under the repo-root pytest.
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))


@pytest.fixture
def write_workflow(tmp_path):
    """Write workflow YAML text to a temp .workflow.yaml file and return its path."""

    def _write(text, name="wf.workflow.yaml"):
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        return p

    return _write
