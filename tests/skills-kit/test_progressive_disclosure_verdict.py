"""Tests for the Dec-11 size-is-a-signal recalibration of the progressive-
disclosure check in audit.check_universal.

The framework (Dec-11) holds that the 500-line / 3000-token size threshold is
a SIGNAL that a SKILL.md deserves evaluation for a split, NOT a verdict that
splitting is correct. A split is required only if a CRP-passing decomposition
exists (sections serve different reading tasks) -- and the mechanical check
cannot evaluate CRP. So a large body with no references/ must emit
``judgment-required`` (the agent-must-judge case), never ``fail``. Emitting
FAIL was the ``hygiene_as_verdict`` anti-pattern and would push an agent to
split skills whose sections all serve one reading task.

These tests pin:
1. small body                       -> n/a   (conditional does not fire)
2. large body + references/ exists  -> pass  (split was taken)
3. large body + no references/      -> judgment-required (run the CRP test)
"""

from skills_kit_lib.audit import check_universal
from skills_kit_lib.markdown_heuristics import parse_body, parse_frontmatter


HEADER = (
    "---\n"
    "name: example-skill\n"
    "description: Use when doing X. Do NOT use for Y.\n"
    "skill-type: technique-skill\n"
    "---\n\n"
    "# Example\n\n"
)


def _row(results):
    return next(r for r in results if "progressive disclosure" in r.row)


def _make(tmp_path, *, words: int, references: bool):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    if references:
        (skill_dir / "references").mkdir()
    body_text = HEADER + " ".join(f"word{i}" for i in range(words)) + "\n"
    fm = parse_frontmatter(body_text)
    body = parse_body(body_text)
    # The shipped description criteria are irrelevant to this row.
    return check_universal(fm, body, skill_dir, skill_criteria=())


def test_small_body_is_na(tmp_path):
    row = _row(_make(tmp_path, words=50, references=False))
    assert row.verdict == "n/a", f"got {row.verdict}: {row.note}"


def test_large_body_with_references_passes(tmp_path):
    # >3000 token approx (tokens ~= words * 1.3) -> ~2400 words crosses it.
    row = _row(_make(tmp_path, words=2600, references=True))
    assert row.verdict == "pass", f"got {row.verdict}: {row.note}"
    assert "references/ exists" in row.note


def test_large_body_without_references_is_judgment_not_fail(tmp_path):
    """The canonical Dec-11 case: large body, no references/. Must be
    judgment-required (CRP evaluation), never fail.
    """
    row = _row(_make(tmp_path, words=2600, references=False))
    assert row.verdict == "judgment-required", f"got {row.verdict}: {row.note}"
    assert row.verdict != "fail"
    assert "CRP" in row.note
