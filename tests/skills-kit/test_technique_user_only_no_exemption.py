"""I7: the technique ordered-step row does NOT exempt user-only skills
(disable-model-invocation: true). The
skills_kit_lib/CLAUDE.md insight `user_only_via_disable_model_invocation`
claimed the technique check reports n/a for user-only skills; that
is false -- the frontmatter flag is never read, and Dec-2
(tests/skills-kit/test_schemas.py) pins the opposite at the schema layer.
This test pins the same fact at the legacy-fallback audit layer: a
user-only technique skill with no YAML contract and no ordered steps FAILs
technique-ordered-steps, it does not get n/a.
"""

from pathlib import Path

from skills_kit_lib.audit import audit


def _write(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "s"
    d.mkdir()
    p = d / "SKILL.md"
    p.write_text(
        "---\nname: s\ndescription: Use when X. Do NOT use for Y.\n"
        "skill-type: technique-skill\ndisable-model-invocation: true\n---\n"
        + body,
        encoding="utf-8",
    )
    return p


def _row(rows, name_substr):
    for r in rows:
        if name_substr in r["row"]:
            return r
    raise AssertionError(f"row '{name_substr}' not found in {rows}")


class TestUserOnlyDoesNotExemptOrderedSteps:
    def test_no_steps_fails_even_when_user_only(self, tmp_path):
        p = _write(tmp_path, "# S\n\nNo ordered steps at all, just prose.\n")
        report = audit(p)
        row = _row(report["type_specific"], "ordered-step body")
        assert row["verdict"] == "fail", row

    def test_the_trigger_model_flag_does_not_change_any_technique_row(self, tmp_path):
        body = "# S\n\nNo ordered steps.\n"
        user_only = audit(_write(tmp_path, body))
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        plain = plain_dir / "SKILL.md"
        plain.write_text(
            "---\nname: s\ndescription: Use when X. Do NOT use for Y.\n"
            "skill-type: technique-skill\n---\n" + body,
            encoding="utf-8",
        )
        # The disable-model-invocation flag is metadata: it must not change the
        # outcome of any technique row.
        assert user_only["type_specific"] == audit(plain)["type_specific"]
