# Shipped CLAUDE.md standards

The size and record-floor criteria skills-kit ships for every CLAUDE.md and
AGENTS.md. This file is layer 0 of the standards configuration for the
`claude_md` file type: `standards_resolve.resolve()` reads it before the user
and project layers, and every CLAUDE.md / AGENTS.md audit applies the criteria
below. It must exist; when it is missing, the audit stops with an error rather
than skipping these rows.

The block below is the single source of truth for each criterion's id,
statement, severity and threshold default. Each criterion is `mechanical`: the
check itself is a registered evaluator in `audit.py` (`MECHANICAL_EVALUATORS`),
keyed by the criterion `id`. The evaluator holds no default of its own.

A user or project layer tunes these criteria the same way as any other optional
opinion:

- `rules: {<id>: off}` in a layer's `config.yaml` removes that criterion's row
  from the audit.
- `thresholds: {import_max_lines: <positive int>}` replaces the line limit that
  `claude-md-import-size` declares below.
- `thresholds: {body_max_lines: <positive int>}` and
  `thresholds: {body_max_tokens: <positive int>}` replace the built-in body
  limits. Those two limits are built in, not declared here: the SKILL.md
  `body-size-signal` rule reads the same values, so one override moves both.
  `claude-md-size-signal` reads them without owning them.

`claude-md-record-floor` applies only to a CLAUDE.md that carries a parsed
`claude_md:` contract block; a file without one has no row for it. The
evaluator's `applies` gate decides this, not the file.

The two inoffensive CLAUDE.md integrity checks, `claude-md-links-resolve` and
`claude-md-fences-closed`, are not in this file: they have no config knob.

An authored standards file may not declare a criterion with one of these ids:
a criterion id repeated anywhere in the resolved layers is an error.

```yaml
standards_set:
  _schema_version: "1"
  identity: Shipped size and record-floor standards for every CLAUDE.md and AGENTS.md.
  applies_to: claude_md
  criteria:
    - id: claude-md-import-size
      statement: Every `@import` target in a CLAUDE.md / AGENTS.md is at most `import_max_lines` lines.
      severity: fail
      keywords: [import size, import_max_lines, "@import", ambient context cost]
      enforcement: mechanical
      threshold:
        name: import_max_lines
        default: 50
    - id: claude-md-size-signal
      statement: A CLAUDE.md / AGENTS.md body stays within `body_max_lines` lines and `body_max_tokens` approximate tokens; an over-threshold body raises a judgment on whether its sections serve different reading tasks.
      severity: judgment
      keywords: [body size, size signal, body_max_lines, body_max_tokens, split judgment]
      enforcement: mechanical
    - id: claude-md-record-floor
      statement: A CLAUDE.md that carries a `claude_md:` block declares at least one record across the `insights` / `conventions` union.
      severity: fail
      keywords: [record floor, union floor, insights, conventions, claude_md block]
      enforcement: mechanical
```
