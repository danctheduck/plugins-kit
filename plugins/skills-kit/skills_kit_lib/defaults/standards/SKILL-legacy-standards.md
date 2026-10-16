# Shipped legacy SKILL.md standards

The legacy per-skill-type heuristic criteria skills-kit ships for a SKILL.md
that declares a `skill-type` and has not moved to the YAML contract. This file
is layer 0 of the standards configuration, beside `SKILL-standards.md`:
`standards_resolve.resolve()` reads it before the user and project layers, and
every SKILL.md audit applies the criteria below. It must exist; when it is
missing, the audit stops with an error rather than skipping these rows.

The block below is the single source of truth for each criterion's id,
statement and severity. Each criterion is `mechanical`: the check itself is a
registered evaluator in `audit.py` (`MECHANICAL_EVALUATORS`), keyed by the
criterion `id`. None declares a threshold.

Every criterion here is scoped by the evaluator's `applies` gate, not by this
file, and the scope has three parts:

- The SKILL.md has no YAML contract block. A contract block, parsed or merely
  detected on a bare interpreter, supersedes these heuristics, so a skill on
  the contract gets none of these rows.
- The SKILL.md's `skill-type` frontmatter names the skill type the criterion
  covers (its statement says which). An untagged skill, or one tagged with a
  type that has no criteria here, gets none.
- The evaluator reads the body with fenced code blocks removed, so a marker
  that appears only inside a fenced example does not count.

These rows report in the `type_specific` list, after the YAML-contract rows and
before the mixed-type row. They are the only SKILL.md rows that keep their real
verdict on a bare interpreter without pyyaml: a deferred row would replace a
deterministic heading or marker test with a request to install a parser.
Because the severity below cannot be read there, each evaluator carries a copy
(`MechanicalEvaluator.bare_severity`) that a test pins equal to this file.

A user or project layer tunes these criteria the same way as any other optional
opinion: `rules: {<id>: off}` in a layer's `config.yaml` removes that
criterion's row from the audit. An authored standards file may not declare a
criterion with one of these ids: a criterion id repeated anywhere in the
resolved layers is an error.

```yaml
standards_set:
  _schema_version: "1"
  identity: Shipped legacy per-skill-type heuristic standards for a SKILL.md that declares a skill-type and has no YAML contract.
  applies_to: skill_md
  criteria:
    - id: ref-example-block
      statement: A reference-skill body has an "Example" heading.
      severity: judgment
      keywords: [reference-skill, example heading, example block, legacy heuristics]
      enforcement: mechanical
    - id: ref-gotcha-block
      statement: A reference-skill body has a "Gotcha" heading.
      severity: judgment
      keywords: [reference-skill, gotcha heading, gotcha block, legacy heuristics]
      enforcement: mechanical
    - id: ref-prohibited-discipline
      statement: A reference-skill body omits discipline content (rule+counter, RED/GREEN/REFACTOR).
      severity: fail
      keywords: [reference-skill, prohibited discipline content, rule and counter, legacy heuristics]
      enforcement: mechanical
    - id: ref-prohibited-checklist
      statement: A reference-skill body omits a workflow tickbox checklist.
      severity: fail
      keywords: [reference-skill, prohibited checklist, tickbox list, legacy heuristics]
      enforcement: mechanical
```
