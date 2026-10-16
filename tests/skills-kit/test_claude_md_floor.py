"""Tests for the claude_md insights/conventions union floor (Dec-19).

The schema no longer requires insights: as a key -- a conventions-only
CLAUDE.md validates. The non-empty floor is the insights/conventions UNION,
enforced by the shipped criterion claude-md-record-floor (audit.MECHANICAL_EVALUATORS); an
empty block (neither insights nor conventions) still fails.
"""

import copy

import yaml

from pathlib import Path

from skills_kit_lib.audit import FAIL, MECHANICAL_EVALUATORS, audit, parse_body, ClaudeMdContext
from skills_kit_lib.schema_engine import validate
from skills_kit_lib.schemas.claude_md import CLAUDE_MD_SCHEMA


CONVENTIONS_ONLY = {
    "claude_md": {
        "_schema_version": "1",
        "scope": {
            "directory": "some/dir",
            "covers": ["x"],
        },
        "conventions": [
            {
                "rule": "Do X before Y.",
                "keywords": ["x first", "ordering", "convention"],
                "why": "Y depends on X.",
            },
        ],
    }
}


class TestSchema:
    def test_conventions_only_block_validates(self):
        fails, _ = validate(CONVENTIONS_ONLY, CLAUDE_MD_SCHEMA)
        assert fails == []

    def test_insights_when_present_still_need_one_record(self):
        data = copy.deepcopy(CONVENTIONS_ONLY)
        data["claude_md"]["insights"] = []
        fails, _ = validate(data, CLAUDE_MD_SCHEMA)
        assert fails, "an empty insights list is still a shape error (min_len 1)"

    def test_insights_shape_still_enforced_when_present(self, minimal_claude_md):
        fails, _ = validate(minimal_claude_md, CLAUDE_MD_SCHEMA)
        assert fails == []
        bad = copy.deepcopy(minimal_claude_md)
        del bad["claude_md"]["insights"][0]["origin"]
        fails, _ = validate(bad, CLAUDE_MD_SCHEMA)
        assert fails


def _floor(data: dict) -> tuple[str, bool, str]:
    """The record-floor evaluator over a parsed {"claude_md": {...}} document."""
    ctx = ClaudeMdContext(Path("CLAUDE.md"), "", parse_body(""), data["claude_md"])
    return MECHANICAL_EVALUATORS["claude-md-record-floor"].evaluate(ctx, {})


class TestUnionFloor:
    def test_conventions_only_passes_floor(self):
        assert _floor(CONVENTIONS_ONLY)[1] is True

    def test_insights_only_passes_floor(self, minimal_claude_md):
        assert _floor(minimal_claude_md)[1] is True

    def test_empty_block_fails_floor(self):
        data = copy.deepcopy(CONVENTIONS_ONLY)
        del data["claude_md"]["conventions"]
        assert _floor(data)[1] is False


class TestAuditIntegration:
    def _audit(self, tmp_path, data: dict) -> dict:
        p = tmp_path / "CLAUDE.md"
        p.write_text(
            "# dir insights\n\n```yaml\n" + yaml.safe_dump(data, sort_keys=False) + "```\n",
            encoding="utf-8",
        )
        return audit(p)

    def _fail_rows(self, report):
        return [r for r in report["yaml_contract"] if r["verdict"] == FAIL]

    def test_conventions_only_claude_md_audits_clean(self, tmp_path):
        report = self._audit(tmp_path, CONVENTIONS_ONLY)
        assert self._fail_rows(report) == []

    def test_empty_claude_md_block_fails_audit(self, tmp_path):
        data = copy.deepcopy(CONVENTIONS_ONLY)
        del data["claude_md"]["conventions"]
        report = self._audit(tmp_path, data)
        fails = self._fail_rows(report)
        assert any("union floor" in r["row"] for r in fails)
