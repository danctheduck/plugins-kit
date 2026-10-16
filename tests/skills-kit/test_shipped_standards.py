"""The shipped standards layer (skills_kit_lib/defaults/standards/) and the
mechanical evaluators that serve its criteria.

desc-160-char, desc-directive-form and desc-exclusion-clause are criteria of
the shipped SKILL-standards.md, evaluated by audit.MECHANICAL_EVALUATORS, and
absent from rule_catalog.RULES. These tests pin that the file, not the code,
decides which rows an audit emits (the red-on-revert test drops a criterion
from a copy of the file), and that every way the layer can be broken is loud.
"""

import dataclasses
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from skills_kit_lib import audit as audit_mod
from skills_kit_lib import rule_catalog
from skills_kit_lib import standards_resolve as sr
from skills_kit_lib.audit import FAIL, JUDGMENT, MECHANICAL_EVALUATORS, PASS, audit

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugins" / "skills-kit"
SHIPPED_FILE = PLUGIN / "skills_kit_lib" / "defaults" / "standards" / "SKILL-standards.md"
REFERENCES_STANDARDS = PLUGIN / "skills" / "md-domain" / "references" / "standards"
RESOLVE_CLI = PLUGIN / "scripts" / "resolve_standards.py"

SHIPPED_IDS = ["desc-160-char", "desc-directive-form", "desc-exclusion-clause"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic_user_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))


def _user_layer(tmp_path):
    layer = tmp_path / "config" / "skills-kit"
    layer.mkdir(parents=True, exist_ok=True)
    return layer


def _shipped_block():
    text = SHIPPED_FILE.read_text(encoding="utf-8")
    block = text.split("```yaml\n", 1)[1].split("```", 1)[0]
    return yaml.safe_load(block)


def _write_shipped(tmp_path, mutate):
    """Copy the shipped file into a tmp dir after mutating its block."""
    data = _shipped_block()
    mutate(data["standards_set"]["criteria"])
    d = tmp_path / "shipped"
    d.mkdir()
    (d / "SKILL-standards.md").write_text(
        "# Shipped copy\n\n```yaml\n" + yaml.safe_dump(data, sort_keys=False) + "```\n",
        encoding="utf-8",
    )
    return d


def _skill(tmp_path, description="Use when doing X. Do NOT use for Y."):
    d = tmp_path / "subject"
    d.mkdir()
    p = d / "SKILL.md"
    p.write_text(
        f"---\nname: subject\ndescription: {description}\nskill-type: reference-skill\n---\n"
        "# Subject\n\n## Example\n\nfoo\n\n## Gotcha\n\nbar\n",
        encoding="utf-8",
    )
    return p


def _rows(report):
    return {r["rule"]: r for r in report["universal"]}


def _standards_md(criteria_yaml):
    return (
        "# Authored\n\n```yaml\nstandards_set:\n"
        "  identity: An authored set for SKILL.md files.\n"
        "  applies_to: skill_md\n"
        "  criteria:\n" + textwrap.indent(textwrap.dedent(criteria_yaml), "    ") + "```\n"
    )


# ---------------------------------------------------------------------------
# where the three criteria live
# ---------------------------------------------------------------------------


def test_the_three_ids_left_the_catalog_and_nothing_else_did():
    for rid in SHIPPED_IDS:
        assert rid not in rule_catalog.RULES
    assert "skill-type-tag" in rule_catalog.RULES
    assert "skill-type-valid" in rule_catalog.RULES
    buckets = [b for b, _g, _d in rule_catalog.RULES.values()]
    assert (buckets.count("optional"), buckets.count("inoffensive"),
            buckets.count("architectural")) == (41, 11, 3)


def test_shipped_file_declares_the_three_mechanical_criteria():
    criteria = _shipped_block()["standards_set"]["criteria"]
    assert [c["id"] for c in criteria] == SHIPPED_IDS
    assert all(c["enforcement"] == "mechanical" for c in criteria)
    assert criteria[0]["threshold"] == {"name": "desc_max_chars", "default": 160}
    assert "desc_max_chars" not in audit_mod.THRESHOLDS


def test_registry_keys_are_exactly_the_shipped_mechanical_ids():
    """No evaluator without a shipped criterion, no criterion without one."""
    assert list(MECHANICAL_EVALUATORS) == SHIPPED_IDS


def test_resolve_loads_the_shipped_layer_by_default():
    r = sr.resolve(None)
    files = r.standards_by_primitive["skill_md"]
    assert [(sf.layer, sf.path) for sf in files] == [("shipped", SHIPPED_FILE)]
    assert r.threshold_defaults == {"desc_max_chars": 160}
    assert sr.resolve(None, shipped_dir=None).standards_by_primitive == {}


# ---------------------------------------------------------------------------
# red on revert: the file decides the rows
# ---------------------------------------------------------------------------


def test_removing_a_criterion_from_the_shipped_file_drops_only_its_row(tmp_path, monkeypatch):
    path = _skill(tmp_path)
    baseline = audit(path)
    assert set(SHIPPED_IDS) <= set(_rows(baseline))

    def drop_exclusion(cs):
        cs[:] = [c for c in cs if c["id"] != "desc-exclusion-clause"]

    shipped = _write_shipped(tmp_path, drop_exclusion)
    monkeypatch.setattr(sr, "SHIPPED_STANDARDS_DIR", shipped)
    report = audit(path)

    expected = [r for r in baseline["universal"] if r["rule"] != "desc-exclusion-clause"]
    assert report["universal"] == expected


def test_rows_sit_right_after_desc_present_in_file_order(tmp_path):
    rules = [r["rule"] for r in audit(_skill(tmp_path))["universal"]]
    i = rules.index("desc-present")
    assert rules[i + 1:i + 4] == SHIPPED_IDS


def test_non_fail_severity_reports_judgment_not_fail(tmp_path, monkeypatch):
    def soften(cs):
        for c in cs:
            if c["id"] == "desc-directive-form":
                c["severity"] = "info"
    monkeypatch.setattr(sr, "SHIPPED_STANDARDS_DIR", _write_shipped(tmp_path, soften))
    rows = _rows(audit(_skill(tmp_path, description="Provides X. Do NOT use for Y.")))
    assert rows["desc-directive-form"]["verdict"] == JUDGMENT
    assert rows["desc-exclusion-clause"]["verdict"] == PASS


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


def test_rules_off_removes_the_row(tmp_path):
    (_user_layer(tmp_path) / "config.yaml").write_text(
        "rules:\n  desc-directive-form: off\n", encoding="utf-8")
    report = audit(_skill(tmp_path), sr.resolve(None))
    assert "desc-directive-form" not in _rows(report)
    assert "desc-160-char" in _rows(report)


def test_threshold_override_changes_label_and_verdict(tmp_path):
    (_user_layer(tmp_path) / "config.yaml").write_text(
        "thresholds:\n  desc_max_chars: 20\n", encoding="utf-8")
    row = _rows(audit(_skill(tmp_path), sr.resolve(None)))["desc-160-char"]
    assert row["row"] == "description <= 20 chars"
    assert row["verdict"] == FAIL


def test_shipped_knobs_stay_valid_when_the_shipped_layer_is_opted_out(tmp_path):
    (_user_layer(tmp_path) / "config.yaml").write_text(
        "rules:\n  desc-160-char: off\nthresholds:\n  desc_max_chars: 120\n", encoding="utf-8")
    r = sr.resolve(None, shipped_dir=None)
    assert r.disabled_rules == {"desc-160-char"}
    assert r.thresholds == {"desc_max_chars": 120}


# ---------------------------------------------------------------------------
# loud failures
# ---------------------------------------------------------------------------


def test_missing_shipped_layer_raises_and_audit_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sr, "SHIPPED_STANDARDS_DIR", tmp_path / "absent")
    with pytest.raises(sr.StandardsConfigError):
        sr.resolve(None)
    path = _skill(tmp_path)
    with pytest.raises(sr.StandardsConfigError):
        audit(path)
    assert audit_mod.main([str(path)]) == 1
    assert "absent" in capsys.readouterr().err
    assert audit_mod.main([str(path), "--config"]) == 1


def test_shipped_dir_without_skill_standards_file_raises(tmp_path, monkeypatch):
    d = tmp_path / "shipped"
    d.mkdir()
    (d / "doc-standards.md").write_text(_standards_md("""\
        - id: some-doc-opinion
          statement: A doc names its reader.
          severity: info
          keywords: [reader, audience, doc]
        """).replace("skill_md", "plain_md"), encoding="utf-8")
    monkeypatch.setattr(sr, "SHIPPED_STANDARDS_DIR", d)
    with pytest.raises(sr.StandardsConfigError) as exc:
        sr.resolve(None)
    assert "SKILL-standards.md" in str(exc.value)


def test_claude_md_audit_does_not_need_the_shipped_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "SHIPPED_STANDARDS_DIR", tmp_path / "absent")
    d = tmp_path / "proj"
    d.mkdir()
    for name in ("CLAUDE.md", "AGENTS.md"):
        sub = d / name.split(".")[0]
        sub.mkdir()
        (sub / name).write_text("# Notes\n\nSome guidance.\n", encoding="utf-8")
        assert audit(sub / name).get("kind") == "claude_md"


@pytest.mark.parametrize("doc", ["skill-standards.md", "coverage-standards.md"])
def test_references_standards_docs_are_fatal_as_a_shipped_dir(tmp_path, doc):
    """Both P2 failure modes, separately: a doc without a standards_set block,
    and coverage-standards.md's code_directory subject."""
    d = tmp_path / "shipped"
    d.mkdir()
    shutil.copy(REFERENCES_STANDARDS / doc, d / doc)
    with pytest.raises(sr.StandardsConfigError) as exc:
        sr.resolve(None, shipped_dir=d)
    msg = str(exc.value)
    if doc == "skill-standards.md":
        assert "no fenced `standards_set:` YAML block" in msg
    else:
        assert "code_directory" in msg


def test_duplicate_id_within_one_list_raises(tmp_path):
    (_user_layer(tmp_path) / "SKILL-standards.md").write_text(_standards_md("""\
        - id: one-opinion
          statement: First.
          severity: info
          keywords: [a, b, c]
        - id: one-opinion
          statement: Second.
          severity: info
          keywords: [a, b, c]
        """), encoding="utf-8")
    with pytest.raises(sr.StandardsConfigError) as exc:
        sr.resolve(None)
    assert "criteria[0]" in str(exc.value) and "criteria[1]" in str(exc.value)


def test_authored_id_repeating_a_shipped_criterion_raises_naming_both(tmp_path):
    layer = _user_layer(tmp_path)
    (layer / "SKILL-standards.md").write_text(_standards_md("""\
        - id: desc-160-char
          statement: Mine.
          severity: info
          keywords: [a, b, c]
        """), encoding="utf-8")
    with pytest.raises(sr.StandardsConfigError) as exc:
        sr.resolve(None)
    msg = str(exc.value)
    assert str(SHIPPED_FILE) in msg and str(layer / "SKILL-standards.md") in msg


def test_duplicate_id_across_primitives_raises(tmp_path):
    layer = _user_layer(tmp_path)
    crit = """\
        - id: shared-opinion
          statement: Something.
          severity: info
          keywords: [a, b, c]
        """
    (layer / "SKILL-standards.md").write_text(_standards_md(crit), encoding="utf-8")
    (layer / "doc-standards.md").write_text(
        _standards_md(crit).replace("skill_md", "plain_md"), encoding="utf-8")
    with pytest.raises(sr.StandardsConfigError, match="shared-opinion"):
        sr.resolve(None)


def test_authored_id_equal_to_a_catalog_rule_raises(tmp_path):
    (_user_layer(tmp_path) / "SKILL-standards.md").write_text(_standards_md("""\
        - id: yaml-contract
          statement: Bypass attempt.
          severity: info
          keywords: [a, b, c]
        """), encoding="utf-8")
    with pytest.raises(sr.StandardsConfigError) as exc:
        sr.resolve(None)
    assert "architectural" in str(exc.value) and "rule_catalog" in str(exc.value)


def test_mechanical_criterion_without_an_evaluator_raises(tmp_path):
    (_user_layer(tmp_path) / "SKILL-standards.md").write_text(_standards_md("""\
        - id: no-emoji
          statement: A SKILL.md body carries no emoji.
          severity: fail
          keywords: [emoji, glyph, ascii]
          enforcement: mechanical
        """), encoding="utf-8")
    with pytest.raises(sr.StandardsConfigError) as exc:
        sr.resolve(None)
    assert "no-emoji" in str(exc.value) and "no evaluator" in str(exc.value)


@pytest.mark.parametrize("mutate, needle", [
    (lambda c: c[0].pop("threshold"), "must declare"),
    (lambda c: c[0]["threshold"].update(name="desc_limit"), "evaluator reads"),
    (lambda c: c[0]["threshold"].update(default=0), "positive integer"),
    (lambda c: c[1].update(threshold={"name": "x_max", "default": 3}), "only a"),
])
def test_bad_threshold_declarations_raise(tmp_path, mutate, needle):
    d = _write_shipped(tmp_path, mutate)
    with pytest.raises(sr.StandardsConfigError, match=needle):
        sr.resolve(None, shipped_dir=d)


def test_threshold_declaration_colliding_with_a_builtin_raises(tmp_path, monkeypatch):
    evaluator = dataclasses.replace(MECHANICAL_EVALUATORS["desc-160-char"], threshold="name_max_chars")
    monkeypatch.setitem(MECHANICAL_EVALUATORS, "desc-160-char", evaluator)
    d = _write_shipped(tmp_path, lambda c: c[0]["threshold"].update(name="name_max_chars"))
    with pytest.raises(sr.StandardsConfigError, match="built-in threshold"):
        sr.resolve(None, shipped_dir=d)


def test_unknown_threshold_override_still_raises(tmp_path):
    (_user_layer(tmp_path) / "config.yaml").write_text(
        "thresholds:\n  bogus_max: 3\n", encoding="utf-8")
    with pytest.raises(sr.StandardsConfigError, match="desc_max_chars"):
        sr.resolve(None)


# ---------------------------------------------------------------------------
# consumers
# ---------------------------------------------------------------------------


def _cli(tmp_path, *args):
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(tmp_path / "config")
    env["PYTHONPATH"] = str(REPO_ROOT / "plugins" / "bootstrap")
    env["_BOOTSTRAP_GUARD_VENV_REEXEC"] = "1"
    proc = subprocess.run(
        [sys.executable, str(RESOLVE_CLI), "--project-root", str(tmp_path), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_resolver_cli_never_lists_the_shipped_file(tmp_path):
    assert _cli(tmp_path)["standards"] == {}
    assert _cli(tmp_path, "--primitive", "skill_md")["standards"] == {"skill_md": []}
    layer = _user_layer(tmp_path)
    (layer / "SKILL-standards.md").write_text(_standards_md("""\
        - id: mine
          statement: Mine.
          severity: info
          keywords: [a, b, c]
        """), encoding="utf-8")
    assert _cli(tmp_path)["standards"] == {"skill_md": [str(layer / "SKILL-standards.md")]}


def _load_script(name):
    path = PLUGIN / "skills" / "md-domain" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_m5_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_emit_audit_jobs_opts_out_of_the_shipped_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "SHIPPED_STANDARDS_DIR", tmp_path / "absent")
    emit = _load_script("emit_audit_jobs")
    assert emit.resolve_admitted_endpoints(tmp_path) == frozenset()


def test_evidence_pack_propagates_a_shipped_layer_error(tmp_path, monkeypatch):
    ep = _load_script("evidence_pack")
    path = _skill(tmp_path)
    assert any("description <= 160 chars" in line for line in ep._audit_verdicts(path))
    monkeypatch.setattr(sr, "SHIPPED_STANDARDS_DIR", tmp_path / "absent")
    with pytest.raises(sr.StandardsConfigError):
        ep._audit_verdicts(path)


def test_evidence_pack_still_degrades_without_pyyaml(tmp_path, monkeypatch):
    ep = _load_script("evidence_pack")
    monkeypatch.setattr(sr, "HAVE_YAML", False)
    lines = ep._audit_verdicts(_skill(tmp_path))
    assert lines == ["mechanical-contract-check unavailable: StandardsUnavailableError"]


# ---------------------------------------------------------------------------
# no pyyaml: deferred rows, still loud on a missing file
# ---------------------------------------------------------------------------


def _bare(tmp_path, code):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(PLUGIN)
    prelude = "import sys\nsys.modules['yaml'] = None\n"
    return subprocess.run([sys.executable, "-c", prelude + code],
                          capture_output=True, text=True, env=env, timeout=60)


def test_without_pyyaml_the_rows_are_deferred(tmp_path):
    path = _skill(tmp_path)
    proc = _bare(tmp_path, (
        "import json\nfrom skills_kit_lib.audit import audit\n"
        f"print(json.dumps(audit(__import__('pathlib').Path({str(path)!r}))['universal']))\n"
    ))
    assert proc.returncode == 0, proc.stderr
    rows = {r["rule"]: r for r in json.loads(proc.stdout)}
    for rid in SHIPPED_IDS:
        assert rows[rid]["verdict"] == JUDGMENT
        assert "(deferred)" in rows[rid]["row"]
        assert "160" not in rows[rid]["row"]


def test_without_pyyaml_a_missing_shipped_file_still_exits_1(tmp_path):
    path = _skill(tmp_path)
    proc = _bare(tmp_path, (
        "from pathlib import Path\nfrom skills_kit_lib import standards_resolve as sr\n"
        f"sr.SHIPPED_STANDARDS_DIR = Path({str(tmp_path / 'absent')!r})\n"
        "from skills_kit_lib import audit\n"
        f"raise SystemExit(audit.main([{str(path)!r}]))\n"
    ))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "shipped standards file missing" in proc.stderr
