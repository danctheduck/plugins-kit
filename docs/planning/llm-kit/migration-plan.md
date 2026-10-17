# llm-kit migration and freeze plan

Status: approved migration plan. llm-kit 0.1.9 was published on 2026-10-17. The
user controls every user and machine of these plugins; there are no unknown
external consumers. `docs/reference/llm-kit-architecture.md` controls conflicts.

The user decisions that gate migration increments are:

- `[USER: stability]`: declare a published llm-kit version stable.
- `[USER: delete]`: choose when to delete the three legacy plugins.

llm-kit may be published at any time without another decision. After stability,
each consumer migration ships as soon as its increment passes. Each consumer
increment is self-contained and includes its own version bump.

## 1. Migration rules

- Frozen legacy plugins remain independently functional. They do not import or
  delegate to llm-kit, and their existing CLIs and registrations do not change.
- Migrated code uses only `llm_kit`, the `llm-kit` CLI, and final qualified
  registrations. There is no silent legacy fallback.
- Keep each consumer's existing install policy while pointing it at llm-kit:
  automatic stays automatic and optional stays optional. Add no new installation
  mechanism or plugin dependency edge.
- Raise migrated consumer Python declarations and CI to Python 3.12 where needed.
- Every consumer declares every third-party package reachable from the llm-kit
  paths it imports. A guarded or lazy cross-plugin import does not waive this.
- Preserve persisted protocol identities unless the signed design explicitly
  maps them. A branding rename is not a data migration.

### Activation checks

The signed design requires these checks before an affected consumer ships:

1. Source and manifest scans find no unsupported old qualified reference.
2. Old-created resumable fixtures resume through both the old name and the final
   llm-kit name.
3. Rollback fixtures disable llm-kit registration and resume through old names.

Mixed installed versions and persisted qualified names exist during migration.
These checks protect those records and make consumer rollback safe.

Each added guard must be shown to fail with a planted prohibited reference, then
pass after restoration.

## 2. Consumer inventory and contracts

### awesome-kit

- Move orchestration model discovery, declaration, seat, and harness imports to
  `llm_kit.registry`, `llm_kit.dispatch`, and `llm_kit.adapters`.
- Point orchestration defaults at the llm-kit venv and grouped CLI, including
  `llm-kit models describe` and OpenCode's `llm-kit models resolve` preflight.
- Change the optional shared import and owner/API/CLI wording to llm-kit; update
  fixtures, patch targets, command expectations, and absence/too-old tests.
- Contract: guidance is `DEGRADE`; a requested endpoint dispatch is `REFUSE`
  without a sufficient llm-kit. No legacy backend is selected silently.

### task-kit

- Move `CodexCliBackend` and `BackendOptions` to
  `llm_kit.adapters.codex_backend` and `llm_kit.completion.types`.
- Change the optional shared import, comments, task-review tests, diagnostics,
  packaging, and CI to llm-kit and Python 3.12.
- Contract: the task-review summary-repair unit is `REFUSE`. Absence names the
  llm-kit install command; an insufficient or stale library names the update
  command and minimum owner version. Each affected task is reported failed.

### git-kit and p4-kit

- Move both review runners to `llm_kit.dispatch.review_lane`; change optional
  shared imports and diagnostics.
- Make the shared generator emit the llm-kit venv and
  `llm-kit models describe`, regenerate both review skills and configuration
  references, and align both packages with Python 3.12.
- Update runner, generator-drift, lane-prompt, retry-prose, and runner-drift tests.
- Contract: agent review is `DEGRADE`; an endpoint lane without a sufficient
  llm-kit is `REFUSE`.

### skills-kit

- Change the md-domain job emitter from the job-kit manifest, executable, probe,
  and command to llm-kit and `llm-kit jobs run`.
- Update lane defaults, owner wording, manifest, packaging, CI, and emitter tests.
- Contract: ordinary md-domain use is `DEGRADE`; unattended job emission is
  `REFUSE` without a sufficient, provisioned llm-kit.

### workflow-kit

- Move declaration, completion, registry, schema, and dispatch imports to final
  llm-kit components.
- Point the automatic provider, shared import, probes, examples, docs, generated
  material, and tests at llm-kit; align packaging and CI with Python 3.12.
- Contract: llm-kit is `REQUIRED` and automatically installed for endpoint/model declarations and schema-typed artifacts. A provisioning gap or insufficient version is `REFUSE` at that boundary.

### yaml-data-editor-kit

- Move dispatch modules to final `llm_kit.pipeline`, `llm_kit.scaffold`,
  registry, and dispatch components.
- Point the automatic provider and both legacy shared imports at llm-kit; update
  probes, description, docs, generated HTML, tests, packaging, and CI.
- Contract: dispatch is `REQUIRED`; absence, insufficient version, or provisioning failure is `REFUSE`. The plugin stays dev-only absent separate publication authority.

### Bootstrap ownership and non-consumers

- Keep both libraries in `bootstrap_lib.engine._FIRST_PARTY_LIBS` through
  coexistence. Remove `llm_scripting_kit` only at deletion.
- Preserve interrupt validator and schema-subset protocol identities while old
  persisted records can exist; final code uses `llm_kit.schema.json_schema`.
- bootstrap owns provisioning contracts and allowlists, not a runtime consumer
  migration.
- secrets-kit, claude-ui-kit, and `p4kit_vcs` contain comments, docstrings, or
  examples only. Update standing ownership wording where needed.

## 3. Install edges and dependency declarations

| Consumer | Existing policy kept | Migration |
|---|---|---|
| awesome-kit | Optional | Optional shared import becomes `llm_kit`. |
| task-kit | Optional | Optional shared import and comment become `llm_kit`. |
| git-kit, p4-kit | Optional | Optional shared import becomes `llm_kit`. |
| skills-kit | Optional | Optional job capability points at llm-kit. |
| workflow-kit | Automatic, REQUIRED | Automatic provider and shared import become llm-kit/`llm_kit`; align probes. |
| yaml-data-editor-kit | Automatic, REQUIRED | Automatic provider becomes llm-kit; legacy imports collapse to `llm_kit`; align probes. |

Preserve existing `.claude-plugin/plugin.json` dependency arrays. awesome-kit
keeps bootstrap plus skills-kit, task-kit keeps bootstrap plus skills-kit plus
awesome-kit, and the other inventoried consumers keep bootstrap.

Run `tests/bootstrap/test_dependency_completeness.py` in every consumer increment.

## 4. Persistent state and launcher paths

llm-kit keeps the established legacy-named state locations. Do not copy, rename,
or split them:

- project credentials and config below `.local-data/plugins-kit/llm-scripting-kit/`,
  including the superseded
  `.local-data/llm-scripting-kit/` read path;
- user credentials, config, verdict cache, and frontdoor log below
  `~/.claude/plugins/data/plugins-kit/llm-scripting-kit/`;
- fleet config `~/.claude/config/llm-scripting-kit.yaml`;
- `$MODEL_ENDPOINTS_REGISTRY` or
  `~/.claude/config/model-endpoints.yaml`;
- the job database at `.local-data/plugins-kit/job-kit/runs.sqlite3`;
- established environment variables and persisted job/pipeline identities.

Do not run legacy and llm-kit job workers against one database during handover.
Stop the legacy worker before starting the llm-kit worker. Pipeline takeover
continues to use its lease and fencing contract.

Executable paths do change. Maintained launchers resolve the llm-kit plugin venv
and grouped `llm-kit` commands. The llm-kit launcher owns the llm-kit data root;
do not add a shim at a legacy executable path.

## 5. Freeze releases

After `[USER: stability]`, release pointer-only freezes for llm-scripting-kit,
content-pipeline-kit, and job-kit. For each provider:

- bump `.claude-plugin/plugin.json` and `pyproject.toml`;
- change the plugin description to say the provider is frozen and point to
  llm-kit;
- add a README pointer and surface mapping.

The mapping covers llm-scripting-kit's API, CLI, and `openrouter-account` skill;
content-pipeline-kit's API, four pipeline skills, `pipeline-worker`, and
`run-ready-wave`; and job-kit's API and `llm-kit jobs` commands.

Do not change legacy skill descriptions, package `__version__` constants,
registrations, runtime code, bootstrap declarations, or plugin-local
`CLAUDE.md` files. Legacy fixes during coexistence are limited to security, critical
correctness, or installability and receive their own version and regression test.

No dedicated freeze-tree guard is needed: all users are known and frozen-tree
changes are visible in review, so the guard would add machinery without
protecting an unknown consumer.

## 6. Repository checks and retained material

- `.claude-plugin/marketplace.json` is derived; regenerate it through the normal
  publisher and never hand-edit it.
- Update root and plugin guidance, shared-library tables, provider examples,
  generated indexes, and active-owner wording at the increment that changes the
  represented state. Preserve dated records and compatibility identifiers.
- Keep all three legacy test suites throughout freeze. A frozen fix must pass
  its provider suite.
- Keep llm-kit parity tests, repoint metadata, the porting ledger,
  `scripts/llm_kit_repoint.py`, and the reproducible ignored mirror until
  deletion.
- Consumer rollback is a new release: restore that consumer's legacy imports,
  launcher paths, and manifest declarations, then bump past every used version.
  Never rewrite or republish an existing version.

## 7. Legacy deletion

Deletion timing is the user's call. After `[USER: delete]`, deletion proceeds
only when maintained code has no unsupported legacy-name references and the
affected tests pass.

Deletion removes:

- `plugins/{llm-scripting-kit,content-pipeline-kit,job-kit}/` and their complete
  test trees;
- their generated marketplace listings;
- legacy shared-library/provider declarations, including `llm_scripting_kit`
  from `_FIRST_PARTY_LIBS`;
- the five duplicate-skill allowlist entries after the matching skill directories
  are gone;
- parity/differential-only tests after equivalent final-only coverage exists;
- the repoint generator, maps, dispositions, ledger, tests, and ignored mirror;
- stale legacy examples, launcher exceptions, and ownership-table entries in
  standing docs and generated indexes.

The deletion scan covers maintained imports, manifests, launchers, CLI calls,
and qualified registrations. Legacy-name hits after deletion must be established
state paths, persisted compatibility identities, or dated records with an
explicit allowlist reason.

## 8. Implementation increments

1. **M1 - llm-kit publication (DONE).** llm-kit 0.1.9 was published on 2026-10-17.
   Any llm-kit release needs no user decision; stability remains separate.
2. **M2 - Pointer-only freeze releases.** After `[USER: stability]`, apply
   section 5, bump and test each provider, then publish all three.
3. **M3 - Activation checks.** Add the maintained-reference scan plus old/final
   resume and rollback fixtures required by section 1. Show each guard red and
   green. Consumer increments extend these fixtures before their own release.
4. **M4 - workflow-kit migration and release.** Migrate runtime, manifest,
   generated material, docs, tests, dependencies, Python floor, and version;
   run its suite and dependency completeness, then publish.
5. **M5 - yaml-data-editor-kit migration.** Migrate dispatch, manifest, docs,
   generated HTML, tests, dependencies, Python floor, and version; test it and
   keep it dev-only while `published: false`.
6. **M6 - skills-kit migration and release.** Migrate the emitter, defaults,
   manifest, docs, tests, dependencies, Python floor, and version; test and publish.
7. **M7 - git-kit and p4-kit migration and release.** Migrate the shared
   generator, both runners, manifests, generated skills/references, tests,
   dependencies, Python floor, and both versions; run targeted suites and
   dependency completeness, then publish both together.
8. **M8 - task-kit migration and release.** Migrate summary repair, manifest,
   diagnostics, tests, dependencies, Python floor, and version; run task-review
   tests and dependency completeness, then publish.
9. **M9 - awesome-kit migration and release.** Migrate orchestration runtime,
   defaults, manifest, references, tests, dependencies, Python floor, and version;
   run its suite and dependency completeness, then publish.
10. **M10 - Legacy deletion.** After `[USER: delete]` and the section 7 repo
    checks pass, remove the providers and compatibility-only material, run
    final-only llm-kit and affected consumer suites plus the maintained-reference
    scan and publisher preflight, then publish the deletion projection.
