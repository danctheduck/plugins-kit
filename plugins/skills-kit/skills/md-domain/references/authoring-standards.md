# Authoring a standards file

A standards file is a markdown document carrying one fenced `standards_set:`
YAML block. The prose is for a human browsing the standards; the block is the
machine-validated contract skills-kit's own audits consume. One file governs
exactly one subject -- a file-type primitive or a composition such as
`code_directory` -- and carries the optional, tunable opinions skills-kit
applies to it. An authored set may name only a file-type primitive; the
composition `code_directory` is rejected (see below).

Standards files are the authored surface of skills-kit's configurable
standards: architectural opinions stay hard-coded and are never expressed here;
mechanical integrity checks carry no knob. What lives in a standards file is the
optional layer -- opinions a project may keep, disable, or tune.

## Where standards files live

Standards files sit in a skills-kit config layer directory (mirroring
`bootstrap.json` layering), one file per subject. The filename is a
discoverability convention; the block's `applies_to:` key is authoritative.

| Filename | `applies_to` subject |
|---|---|
| `SKILL-standards.md` | `skill_md` |
| `CLAUDE-md-standards.md` | `claude_md` |
| `reference-standards.md` | `reference_doc` |
| `doc-standards.md` | `plain_md` |
| `coverage-standards.md` | `code_directory` (shipped only; an authored set is rejected) |

The primitive ids are the file-type sub-kinds registered in
`audit-framework.yaml` (this same references/ directory). A composition id is
one of that file's `compositions:` entries, and an authored set may not name
one: `code_directory` (and its former spelling `code_subtree`, normalised to it)
raises `StandardsConfigError` naming the file, because the coverage lane applies
only its shipped criteria and would ignore the set. Switch a shipped coverage
criterion off with `rules: {<id>: off}` in `config.yaml` instead. If the
filename and `applies_to` disagree, `applies_to` wins; keep them aligned so the
file is discoverable by name.

## The `standards_set` block

Top-level fields:

- **`identity`** (required) -- one sentence stating what this set governs and
  for which subject. Read aloud, it answers "which opinions does this file
  carry, and over what."
- **`applies_to`** (required) -- the file-type primitive id this set governs.
  A composition id appears only in a shipped set (`coverage-standards.md`); an
  authored set naming one is rejected (see above).
  Authoritative over the filename convention.
- **`criteria`** (required, at least one) -- the list of standards. Each entry
  is one checkable opinion.

Each criterion carries:

- **`id`** (required) -- a stable kebab-case identifier. It is the config knob a
  user disables (`rules: {<id>: off}`) and the key an audit finding quotes, so a
  reader can go from finding to config line. Keep it stable once shipped.
- **`statement`** (required) -- the standard, stated as a single checkable
  proposition. One criterion, one proposition.
- **`severity`** (required) -- one of `fail`, `info`, `judgment` (see below).
- **`keywords`** (required, at least three) -- a chat-term routing cluster, as
  on every load-bearing record in the framework.
- **`example`** (optional) -- illustrative exemplar or before/after for the
  statement.
- **`enforcement`** (optional) -- `mechanical` or `judgment`; default
  `judgment` when absent (see below).
- **`threshold`** (optional) -- `{name, default}`: the numeric limit a
  mechanical criterion's evaluator applies. Only a mechanical criterion whose
  registered evaluator reads that threshold name may declare one, and that
  criterion must declare it. `default` is a positive integer; a layer's
  `thresholds: {<name>: <int>}` overrides it.

A criterion `id` is unique across every resolved layer, including the shipped
layer (`skills_kit_lib/defaults/standards/`), and may not repeat a built-in
rule id from the configuring-standards.md catalog. A repeated id raises
`StandardsConfigError` naming both sources.

## Severity semantics

`severity` declares how a violation is dispositioned:

- **`fail`** -- a violation blocks. The finding is a hard failure the author
  must resolve (or disable the criterion) before the gate passes.
- **`info`** -- surfaced but non-blocking. The finding is reported for the
  author's awareness; it does not fail the audit.
- **`judgment`** -- the agent decides per instance. The finding is raised for a
  human-or-agent call rather than mechanically dispositioned.

## Enforcement

`enforcement` declares how a criterion is evaluated:

- **`judgment`** (default) -- for a set naming a file-type primitive, the audit
  detect lane evaluates the criterion from its `statement` text. No code is
  involved; the standard is enforced entirely from what it says. The coverage
  lane evaluates no authored criteria, so a `code_directory` set is rejected by
  `scripts/resolve_standards.py` with an error.
- **`mechanical`** -- a registered evaluator, keyed by the criterion `id`,
  performs the check (for example a character count or a regex). The standards
  file remains the single source of truth for the statement, id, severity and
  threshold default; the code is only the evaluator. The evaluators are
  registered in `skills_kit_lib/audit.py` (`MECHANICAL_EVALUATORS`), and each
  serves a criterion of the shipped layer. A mechanical criterion whose id has
  no registered evaluator raises `StandardsConfigError`, because nothing would
  evaluate it. An authored file therefore declares `judgment` criteria.

Omit `enforcement` and the criterion is a judgment criterion.

## Verbatim-quote enforcement posture

A standards criterion is enforced by quoting it verbatim, never by paraphrase.
When the audit detect lane raises a finding against a file-type primitive's
criterion, it emits the criterion's exact `statement` text together with the
source path of the standards file that declared it. An agent does not infer a rule the standards
file does not state, and does not restate a criterion in its own words. This
mirrors the ancestor-CLAUDE.md convention enforcement already in the audit
lanes: the standard, its wording, and its provenance travel together so the
author can trace every finding back to the exact line that produced it.

## Complete example

A minimal, valid standards file governing `skill_md`:

```yaml
standards_set:
  identity: Project-authored standards for the body of SKILL.md files.
  applies_to: skill_md
  criteria:
    - id: body-names-its-trigger
      statement: The SKILL.md body names, in its first paragraph, the situation that triggers the skill.
      severity: fail
      keywords: [trigger situation, first paragraph, skill body]
      enforcement: judgment
      example: "Open with 'Run this before a release tag is pushed.' rather than a capability summary."
    - id: gotchas-cite-an-incident
      statement: Every gotcha in the SKILL.md cites the incident or measurement that produced it.
      severity: info
      keywords: [gotcha provenance, incident, measurement]
```

The frontmatter-hygiene criteria (`desc-160-char`, `desc-directive-form`,
`desc-exclusion-clause`, `skill-type-tag`, `skill-type-valid`) and the CLAUDE.md
criteria (`claude-md-import-size`, `claude-md-size-signal`,
`claude-md-record-floor`) are not an example to copy: the shipped layer already
declares them, so repeating one of those ids in an authored file is an error.
Switch one off with `rules: {<id>: off}`, or tune `desc_max_chars` or
`import_max_lines` with
`thresholds:`.
