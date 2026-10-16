# Shipped SKILL.md standards

The frontmatter-hygiene criteria (description and skill-type) and the
body-size and references-layout criteria skills-kit
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

Two criteria always report a row but may report it as n/a: `body-size-signal`
is n/a while the body stays within `body_max_lines` lines and `body_max_tokens`
approximate tokens, and `refs-one-hop-deep` is n/a when the skill has no
`references/` directory. `body-size-signal` reads the two built-in body limits
without declaring them, so tuning `body_max_lines` or `body_max_tokens` through
`thresholds:` moves it and `claude-md-size-signal` together. `body-line-count`
and `body-token-count` are informational count rows: they always pass and carry
the count in their note, and `rules: {body-line-count: off}` removes one.

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
    - id: body-line-count
      statement: Reports the SKILL.md body line count (informational count row that always passes).
      severity: info
      keywords: [body line count, line count, SKILL.md size, informational count]
      enforcement: mechanical
    - id: body-token-count
      statement: Reports the approximate SKILL.md body token count (informational count row that always passes).
      severity: info
      keywords: [body token count, token count, SKILL.md size, informational count]
      enforcement: mechanical
    - id: body-size-signal
      statement: A SKILL.md body within `body_max_lines` lines and `body_max_tokens` approximate tokens needs no split; an over-threshold body with no `references/` directory raises a judgment on whether its sections serve different reading tasks.
      severity: judgment
      keywords: [body size, size signal, progressive disclosure, body_max_lines, body_max_tokens, split judgment]
      enforcement: mechanical
    - id: refs-one-hop-deep
      statement: "`references/` is one hop deep, except that a nested reference file counts as one hop when SKILL.md's `index.references[]` declares that file's own relative path or its containing directory."
      severity: fail
      keywords: [one hop deep, nested references, index.references, references layout, ADP]
      enforcement: mechanical
```
