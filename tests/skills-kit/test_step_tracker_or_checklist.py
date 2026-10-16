"""Tests for the Dec-8 step-tracker-OR-checklist refinement.

The workflow-checklist conditional row in audit.py was originally satisfied
only by a paste-able `- [ ]` markdown checklist. Dec-8 refines the rule:
the row is satisfied by EITHER a tickbox checklist OR an explicit step-
tracker invocation (TaskCreate, scratch file, etc.) at the start of the
procedure. The underlying goal is the discipline of explicit step-tracking;
the markdown syntax is one path, not the only one.

These tests confirm:
1. has_step_tracker_invocation() recognizes TaskCreate / TaskWrite /
   TodoWrite invocations and explicit prose markers.
2. The audit's technique-skill conditional row PASSES when only a
   step-tracker invocation is present (no tickbox checklist).
3. The audit's row PASSES when only a tickbox checklist is present
   (no step-tracker invocation) -- backwards compat.
4. The audit's row FAILS when neither is present and step_count > 3.
"""

from pathlib import Path

import pytest

# _shared/audit were extracted into skills_kit_lib (on sys.path via pyproject.toml pythonpath).
from skills_kit_lib.markdown_heuristics import (
    has_step_tracker_invocation,
    has_tickbox_list,
    parse_body,
)
from skills_kit_lib.audit import audit


SKILL_HEADER = """---
name: example-technique
description: Use when doing X. Do not use for Y.
skill-type: technique-skill
---

# Example technique
"""


def _body_with_steps(extra: str = "") -> str:
    """Build a SKILL.md body with 5 ordered steps + an extra block."""
    steps = "\n".join(f"{n}. Do step {n}." for n in range(1, 6))
    return f"{SKILL_HEADER}\n## Procedure\n\n{steps}\n\n{extra}\n"


def _step_tracking_row(tmp_path, body_text):
    """The step-tracking row of the shipped criterion, through a real audit."""
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    path.write_text(body_text, encoding="utf-8")
    rows = [r for r in audit(path)["type_specific"] if r["rule"] == "step-tracking"]
    assert len(rows) == 1
    return rows[0]


def test_has_step_tracker_invocation_recognizes_taskcreate():
    assert has_step_tracker_invocation("Invoke TaskCreate at the start.")


def test_has_step_tracker_invocation_recognizes_taskwrite():
    assert has_step_tracker_invocation("Use TaskWrite to seed the task list.")


def test_has_step_tracker_invocation_recognizes_todowrite():
    assert has_step_tracker_invocation("Call TodoWrite with the step list.")


def test_has_step_tracker_invocation_recognizes_prose_marker():
    assert has_step_tracker_invocation(
        "At the start of the procedure, track steps in a scratch file."
    )


def test_has_step_tracker_invocation_recognizes_step_tracker_phrase():
    assert has_step_tracker_invocation(
        "Initialize a step tracker before beginning."
    )


def test_has_step_tracker_invocation_negative():
    assert not has_step_tracker_invocation(
        "Just do steps in order. No mention of any tracker here."
    )


def test_audit_row_passes_with_taskcreate_invocation_no_checklist(tmp_path):
    """A technique-skill with TaskCreate invocation in body but no `- [ ]`
    markdown still passes the conditional row. This is the canonical Dec-8
    case.
    """
    body_text = _body_with_steps(
        "Before beginning, invoke TaskCreate to seed the task list."
    )
    body = parse_body(body_text)

    # Sanity: tickbox is absent, tracker is present
    assert not has_tickbox_list(body.text)
    assert has_step_tracker_invocation(body.text)

    row = _step_tracking_row(tmp_path, body_text)
    assert row["verdict"] == "pass", f"expected pass, got {row["verdict"]}: {row["note"]}"
    assert "step-tracker invocation" in row["note"]


def test_audit_row_passes_with_only_tickbox_checklist(tmp_path):
    """Backwards compat: a `- [ ]` checklist alone still satisfies the row."""
    checklist = "\n".join(f"- [ ] step {n}" for n in range(1, 6))
    body_text = _body_with_steps(f"Checklist:\n{checklist}")
    body = parse_body(body_text)

    assert has_tickbox_list(body.text)
    assert not has_step_tracker_invocation(body.text)

    row = _step_tracking_row(tmp_path, body_text)
    assert row["verdict"] == "pass", f"expected pass, got {row["verdict"]}: {row["note"]}"
    assert "tickbox checklist" in row["note"]


def test_audit_row_fails_when_neither_present(tmp_path):
    """When step_count > 3 and neither tickbox checklist nor step-tracker
    invocation is present, the row FAILS.
    """
    body_text = _body_with_steps("No tracker, no checklist, just prose.")
    body = parse_body(body_text)

    assert not has_tickbox_list(body.text)
    assert not has_step_tracker_invocation(body.text)

    row = _step_tracking_row(tmp_path, body_text)
    assert row["verdict"] == "fail", f"expected fail, got {row["verdict"]}: {row["note"]}"
    assert "neither" in row["note"]


def test_audit_row_na_when_3_or_fewer_steps(tmp_path):
    """When step_count <= 3, the conditional does not fire; verdict is n/a."""
    body_text = (
        f"{SKILL_HEADER}\n## Procedure\n\n"
        "1. Do step 1.\n2. Do step 2.\n3. Do step 3.\n"
    )
    body = parse_body(body_text)

    row = _step_tracking_row(tmp_path, body_text)
    assert row["verdict"] == "n/a", f"expected n/a, got {row["verdict"]}: {row["note"]}"
