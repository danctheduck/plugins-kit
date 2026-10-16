# Shipped SKILL.md standards

The frontmatter-hygiene criteria (description and skill-type) skills-kit
ships for every SKILL.md. This file
is layer 0 of the standards configuration: `standards_resolve.resolve()` reads
it before the user and project layers, and every SKILL.md audit applies the
criteria below. It must exist; when it is missing, the audit stops with an error
rather than skipping these rows.

The block below is the single source of truth for each criterion's id,
statement, severity and threshold default. Each criterion is `mechanical`: the
check itself is a registered evaluator in `audit.py` (`MECHANICAL_EVALUATORS`),
keyed by the criterion `id`. The evaluator holds no default of its own.

A user or project layer tunes these criteria the same way as any other optional
opinion:

- `rules: {<id>: off}` in a layer's `config.yaml` removes that criterion's row
  from the audit.
- `thresholds: {desc_max_chars: <positive int>}` replaces the length limit that
  `desc-160-char` declares below.

Two criteria apply only to some documents: `skill-type-tag` reports a row only
when the SKILL.md carries no `skill-type` frontmatter, and `skill-type-valid`
only when it does. The evaluator's `applies` gate decides this, not the file.

An authored standards file may not declare a criterion with one of these ids:
a criterion id repeated anywhere in the resolved layers is an error.

```yaml
standards_set:
  _schema_version: "1"
  identity: Shipped frontmatter-hygiene standards (description and skill-type) for every SKILL.md.
  applies_to: skill_md
  criteria:
    - id: desc-160-char
      statement: The description frontmatter field is at most `desc_max_chars` characters.
      severity: fail
      keywords: [description length, desc_max_chars, 160 characters, description hygiene]
      enforcement: mechanical
      threshold:
        name: desc_max_chars
        default: 160
    - id: desc-directive-form
      statement: The description opens with "Use when..." or "Invoke when...".
      severity: fail
      keywords: [directive form, use when, invoke when, description hygiene]
      enforcement: mechanical
    - id: desc-exclusion-clause
      statement: The description carries a "Do NOT use for..." exclusion clause.
      severity: fail
      keywords: [exclusion clause, do not use for, description scope, description hygiene]
      enforcement: mechanical
    - id: skill-type-tag
      statement: A `skill-type` advisory tag is present in frontmatter (else the agent infers the type).
      severity: judgment
      keywords: [skill-type tag, advisory tag, skill type frontmatter, frontmatter hygiene]
      enforcement: mechanical
    - id: skill-type-valid
      statement: The `skill-type` value is one of the canonical skill types.
      severity: fail
      keywords: [skill-type value, canonical skill types, skill type validity, frontmatter hygiene]
      enforcement: mechanical
```
