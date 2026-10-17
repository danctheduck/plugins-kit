# llm-kit migration and freeze plan

Status: draft for user decisions. `plugins/llm-kit` is at 0.1.8. This plan does
not declare stability or authorize publication or deletion. By user ruling,
publication may precede stability but still needs `[USER: publish]`.

Authority markers:

- `[USER: stability]`: the user declares a published llm-kit version stable;
  this gates freeze releases and consumer migration, not llm-kit publication.
- `[USER: publish]`: the user authorizes the named publish.
- `[USER: hold]`: the user chooses how unpublished consumer migrations are kept out of release projections.
- `[USER: install]`: the user chooses how migrated optional consumers acquire llm-kit.
- `[USER: deviation]`: the user authorizes work beyond the signed freeze-release scope.
- `[USER: delete]`: the user chooses the legacy deletion point.

The signed design in `docs/reference/llm-kit-architecture.md` controls conflicts. A freeze release is a pointer release: it does not import or delegate to `llm_kit`, and each legacy CLI remains unchanged.

## 1. Premise outcomes

1. Confirmed: llm-kit 0.1.8 is built. The I9 report records that `tests/llm-kit` passed at commit `46d06a33`; this planning pass did not rerun it.
2. Confirmed with correction: there is no plugin dependency edge to a legacy
   provider or llm-kit. awesome-kit declares `[bootstrap, skills-kit]`, task-kit
   declares `[bootstrap, skills-kit, awesome-kit]`, and the other inventoried
   consumers declare `[bootstrap]`. Cross-plugin library reach uses
   `bootstrap.json` shared imports, lazy probes, and manual or automatic provider
   installation.
3. Confirmed: `tests/bootstrap/test_skill_material.py` and `test_skill_material_declared.py` each allow five duplicate skills: four from content-pipeline-kit and `openrouter-account` from llm-scripting-kit, paired with llm-kit.
4. Refuted: the 2026-10-05 consumer list is too broad and the first planning
   pass omitted task-kit. Production consumers are awesome-kit, task-kit,
   git-kit, p4-kit review dispatch, skills-kit, workflow-kit, and
   yaml-data-editor-kit. bootstrap owns provisioning contracts and allowlists.
   secrets-kit, claude-ui-kit, and `p4kit_vcs` contain comments, docstrings, or
   examples only.
5. Confirmed with correction: `bootstrap_lib.engine._FIRST_PARTY_LIBS` contains `llm_scripting_kit` and `llm_kit`; provider and consumer manifests also name legacy libraries. The bootstrap interrupt validator and schema-subset names are persisted protocol identity, not a runtime legacy import requirement.
6. Confirmed: awesome-kit's orchestration defaults render an executable under `~/.claude/plugins/data/plugins-kit/llm-scripting-kit/.venv`; the shared code-review generator emits the same owner path for git-kit and p4-kit.
7. Refuted as a blanket migration: launcher paths change to the llm-kit venv and CLI, but llm-kit deliberately reuses established credential, model configuration, endpoint registry, verdict cache, frontdoor log, and job database locations. Copying state would fork user data.
8. Untested: repository evidence cannot count installed machines with external scripts, nonterminal jobs, or pipeline leases using a legacy qualified name. Activation and deletion require explicit scans and operational evidence.

## 2. Reference census and consumer inventory

The grep covered `plugins/`, `scripts/`, `tests/`, `docs/`, `.claude/`, and root `CLAUDE.md` for `llm_scripting_kit|llm-scripting-kit|content_pipeline|content-pipeline-kit|job_kit|job-kit`. Its 6,210 matching lines fall into these exhaustive classes:

| Class | Lines | Files | Treatment |
|---|---:|---:|---|
| Legacy-provider implementation and docs | 1,661 | 125 | Preserve for freeze; delete as complete plugin trees at retirement. |
| Legacy-provider tests | 1,770 | 184 | Run during freeze; delete with providers. |
| llm-kit parity and compatibility material | 1,281 | 103 | Preserve through freeze; reduce to final-only tests at retirement. |
| Consumer production code and docs | 513 | 95 | Migrate as inventoried below. |
| Consumer and repository tests | 669 | 61 | Change with the owning consumer or guard. |
| Repository scripts | 30 | 5 | Change generators and guards; retire the repoint tool at deletion. |
| Repository planning and guidance | 286 | 23 | Update standing guidance; preserve dated evidence. |

Directory globs are inventory entries: every match below `plugins/{llm-scripting-kit,content-pipeline-kit,job-kit}/` is provider-owned; every match below the equivalent `tests/` trees is a provider test; and matches below `plugins/llm-kit/` and `tests/llm-kit/` are final implementation, parity, or compatibility material.

### awesome-kit

- Runtime imports: `skills/orchestrate/scripts/{dispatch,orchestration_guidance}.py` move model discovery, declaration, seat, and harness APIs from `llm_scripting_kit` to final components under `llm_kit.{registry,dispatch,adapters}`. Do not add root exports.
- CLI/data path: `skills/orchestrate/defaults/orchestration.yaml` replaces the
  legacy venv and model commands with the llm-kit venv, `llm-kit models
  describe`, and, at line 643's OpenCode preflight, `llm-kit models resolve`.
- Declaration/docs: `bootstrap.json` changes its optional shared import to `llm_kit`; `skills/orchestrate/SKILL.md` and references `{codex-dispatch,configuration,opencode-dispatch,tuning-selection}.md` change owner/API/CLI/install wording.
- Tests: `tests/awesome-kit/{conftest,test_dispatch,test_orchestration_guidance}.py` change fixtures, patch targets, command expectations, and absence/too-old cases.
- Contract: guidance is `DEGRADE`; requested endpoint dispatch is `REFUSE`
  without a sufficient llm-kit. No legacy backend is selected silently.

### task-kit

- Runtime imports: `skills/task/scripts/task_system/summary_ops.py` moves
  `CodexCliBackend` and `BackendOptions` from `llm_scripting_kit.completion` to
  `llm_kit.adapters.codex_backend` and `llm_kit.completion.types`.
- Declaration: `bootstrap.json` changes its `$comment` and optional
  `shared_lib_imports` entry from `llm_scripting_kit` to `llm_kit`.
- Tests and packaging: update all `tests/task-kit/test_task_review*.py` fixtures,
  patch targets, and diagnostics; raise `requires-python` from `>=3.10` to
  `>=3.12`.
- Contract: task review's summary-repair unit is `REFUSE`. An absent llm-kit
  names `claude plugin install llm-kit@plugins-kit`; a present but too-old or
  stale library names `claude plugin update llm-kit@plugins-kit` and the minimum
  owner version. Each affected task is reported failed; no raw `ImportError` or
  silent legacy fallback reaches the user.

### git-kit and p4-kit

- Runtime imports: each `scripts/run_review_lane.py` moves `llm_scripting_kit.review_lane` to `llm_kit.dispatch.review_lane` and changes owner/version diagnostics. Each `bootstrap.json` changes its optional shared import to `llm_kit` without automatic installation.
- Generated CLI: `scripts/gen_code_review_skills.py` emits the llm-kit venv and `llm-kit models describe`, then regenerates both `skills/*-code-review/SKILL.md` and `references/configuration.md`. Align both `pyproject.toml` files without adding a plugin dependency.
- Tests: `tests/git-kit/test_run_review_lane.py`, `tests/bootstrap/code_review/{test_lane_prompts,test_lane_retry_prose,test_skill_drift}.py`, and `tests/bootstrap/test_run_review_lane_drift.py` change with the generator and both generated runners. p4-kit has no dedicated runner test.
- Contract: Agent review remains available (`DEGRADE`). Selecting an endpoint lane without a sufficient llm-kit is `REFUSE`; no legacy fallback.
- Non-consumer: `plugins/p4-kit/lib/p4kit_vcs/{__init__,p4_vcs}.py` names the content-pipeline protocol only in docstrings. Change standing ownership wording only.

### skills-kit

- CLI/manifest: `skills/md-domain/scripts/emit_audit_jobs.py` replaces the job-kit manifest, executable, version probe, and command with llm-kit and `llm-kit jobs run`; `check_project_doc_audit.py` changes owner diagnostics or fixtures only.
- Defaults/docs: `skills_kit_lib/{lane_models.py,defaults/lane_models.yaml}`, `skills/md-domain/SKILL.md`, references `{lanes/audit-lane,provenance/standards-decisions}.md`, and plugin `CLAUDE.md` change owner/invocation wording.
- Tests/contract: `tests/skills-kit/test_emit_audit_jobs.py` changes its manifest, venv, command, version, and refusal fixtures. Ordinary md-domain use is `DEGRADE`; unattended job emission is `REFUSE` without a sufficient, provisioned llm-kit.

### workflow-kit

- Runtime imports: `scripts/{check_artifact,compile_workflow,openrouter_run}.py` and `workflow_kit_lib/{contracts,declarations,model}.py` move declaration, completion, registry, schema, and dispatch imports to final `llm_kit` components.
- Declaration: `bootstrap.json` changes automatic provider, shared import, comments, and probes from llm-scripting-kit to llm-kit.
- Material: `examples/{node-strategies.example.js,node-strategies.workflow.yaml}`, `README.md`, skill `SKILL.md`, references `{contract,node-strategies,preamble,preamble-contracts,workflow-yaml}.md`, and generated preamble expectations change owner/API/CLI names. The comments in `references/preamble.js` and `preamble-contracts.js` are inventory entries. Branding does not alter persisted contract identifiers.
- Tests: every matching site in `tests/workflow-kit/`: `test_bootstrap_manifest`, `test_check_artifact`, `test_compiler`, `test_contract_preamble`, `test_contracts`, `test_contracts_join`, `test_openrouter_run`, `test_workflow_entry_redirect`, and `wk_testlib`.
- Contract: llm-kit is `REQUIRED` and automatically installed for endpoint/model declarations and schema-typed artifacts. A provisioning gap or insufficient version is `REFUSE` at that boundary.

### yaml-data-editor-kit

- Runtime imports: every matching module in `lib/yaml_data_editor_kit/dispatch/` (`__init__`, `adapter`, `background`, `planner`, `protocol`, `run`, `units`, `worker_mount`) moves legacy imports to final `llm_kit.pipeline`, `llm_kit.scaffold`, registry, and dispatch components.
- Declaration/docs: `bootstrap.json` changes automatic provider to llm-kit, collapses two legacy shared imports to `llm_kit`, and changes probes. The plugin description replaces its `content-pipeline-kit` binding claim. Plugin `CLAUDE.md` and docs `{architecture.html,content-pipeline-binding.md,motivation.md}` change owner/API/skill/CLI names; regenerate derived HTML from its source.
- Tests: `tests/yaml-data-editor-kit/{conftest,test_dispatch_background,test_dispatch_background_integration,test_dispatch_imports,test_dispatch_planner,test_dispatch_planner_live,test_dispatch_protocol,test_dispatch_run,test_dispatch_worker_mount}.py`.
- Contract: dispatch is `REQUIRED`; absence, insufficient version, or provisioning failure is `REFUSE`. The plugin stays dev-only absent separate publication authority.

### bootstrap ownership and non-consumers

- `plugins/bootstrap/bootstrap_lib/engine.py::_FIRST_PARTY_LIBS` keeps both libraries through freeze and removes `llm_scripting_kit` only at deletion.
- `bootstrap_lib/interrupt_contract.py::{VALIDATOR_MODULE,VALIDATOR_SUBSET}` preserves protocol identity while old persisted records can exist. Final code uses `llm_kit.schema.json_schema`; identity renaming needs a separate persisted-data design.
- Matches in `bootstrap_lib/{claudx,codex,manifest_merge,model_declaration,shared_lib}.py`, `bootstrap_lib/code_review/{lane_output,lane_prompts}.py`, and bootstrap/plugin-dev references are examples, diagnostics, or guidance. Update active-owner examples and preserve compatibility identifiers.
- `plugins/claude-ui-kit/scripts/statusline.sh`, `plugins/secrets-kit/lib/secrets_kit/repo.py`, and the two `p4kit_vcs` files are comments/docstrings, not runtime consumers.

### Repository scripts, tests, and documentation

- Scripts: `gen_code_review_skills.py` is a live generator; `check_model_dispatch.py` and `check_agent_directives.py` own active-owner wording/guards; `llm_kit_repoint.py` remains through freeze and is deleted at retirement; `review-bakeoff/SPEC.md` is documentation.
- Other test sites: `tests/bootstrap/{test_codex,test_config_resolve,test_deferred_requirements,test_dependency_completeness,test_display_no_paths,test_env_var_check,test_execution_event,test_execution_event_emitters,test_interrupt_contract,test_interrupt_contract_consumers,test_layered_manifests,test_manifest_merge,test_model_declaration,test_skill_material,test_skill_material_declared,test_transient_import_retry,test_venv_check}.py`, fixture `spiritcrossing_tiered_bootstrap.json`, and `tests/repo-scripts/{test_agent_directives,test_check_model_dispatch,test_forced_interpreter_order,test_interpreter_floor,test_launch_paths,test_launcher_shim_data_root_redirect,test_llm_cli_invocation_standard,test_nested_claude_sites,test_python_invocation_standard,test_shell_interpreter_fallback,test_shipped_model_families}.py`. Change active-owner expectations; explicitly allow compatibility fixtures.
- Incidental fixtures: `tests/hue-kit/{test_hue_bootstrap_and_init,test_solver}.py`, `tests/p4-kit/test_vcs_p4.py`, and `tests/unreal-kit/test_unreal_custom_bootstrap.py` change only when asserting a standing example rather than history.
- Documentation sites: root `CLAUDE.md`, `plugins/CLAUDE.md`, `docs/index.html`; planning records `adapters/adapter-design.md`, `bootstrap/stable-channel-design.md`, `content-pipeline-kit/session-recipients-plan.md`, `llm-kit/implementation-plan.md`, `plugin-improvements.md`, `quota-resilient-dispatch/{declaration-format-design,drill-report,requirements}.md`; references `{agent-directive-standards,code-review-mechanical-surface,deprecation-policy,llm-kit-architecture,md-audit-lane-precision-2026-09-03,orchestrate-codex-boundaries,plugin-opinion-razor,plugin-root-variable-sites,publish-reconcile,reusable-libraries,shared-lib-architecture,testing,vacuous-checks}.md`. Update standing claims/generated indexes and preserve dated records plus the signed design.

## 3. Machine states and migration order

| Installed state | Frozen legacy callers | Migrated consumers |
|---|---|---|
| Legacy plugin only | Work unchanged. | REQUIRED boundaries refuse; optional features degrade with disclosure. No legacy fallback. |
| Legacy plugin and llm-kit | Work unchanged against legacy packages and CLIs. | Use only `llm_kit` and `llm-kit`; duplicate skills are invoked by qualified name. |
| llm-kit only | Legacy qualified skills, packages, and CLIs are unavailable. | Work through final APIs and CLI. |
| Neither | Legacy surface is unavailable. | REQUIRED boundaries refuse; optional features degrade with disclosure. |

llm-kit publishes first, before any consumer migration lands. No migrated
published consumer may ship until llm-kit is installable, `[USER: stability]`
has named a published version, and M10 passes. Here, activation means shipping
a migrated consumer, launcher, or maintained qualified reference that selects
the final llm-kit surface; publishing llm-kit alone is not activation.

A plan-file warning is not a publication hold: a bare publish ships dev's whole
tree. Because M1 makes llm-kit installable before migration starts, a hold is
needed only from the first M3-M9 migration landing through M11. Before that
landing, `[USER: hold]` chooses one binding mechanism:

1. Add a named hold in the root `CLAUDE.md` for awesome-kit, task-kit, git-kit,
   p4-kit, skills-kit, and workflow-kit. The hold keeps each named plugin's
   entire tree at master's content until M11; it cannot exclude only migration
   commits. Every intervening release must use repeatable `publish.py --only`
   arguments naming the plugins allowed to advance. The cost is that unrelated
   fixes to any held consumer are also blocked from the first M3-M9 landing
   through M11.
2. Keep M3-M9 migration commits out of release-producing `dev` until the
   coordinated activation window, then land them together immediately before
   M10 and M11. Any publish in that short window must use repeatable `--only`
   arguments naming only safe plugins. An unpushed local `dev` commit is not
   protection if a publish runs from that checkout, because it still projects
   the local tree.

Recommendation: use option 2. Publishing llm-kit first removes the provider-
availability hold, and staging the consumer migrations collapses the remaining
constraint to the M10-M11 validation window. Use option 1 only if the consumer
work must land earlier. yaml-data-editor-kit needs no hold while
`published: false`; its files are structurally absent from release projections.

`[USER: install]` also decides how machines that have only a legacy provider
acquire llm-kit before a migrated optional consumer needs it:

- Option A: keep optionality. Declare `install: "manual"` for llm-kit in
  awesome-kit, task-kit, git-kit, p4-kit, and skills-kit. Their absent-state
  REFUSE/DEGRADE messages name `claude plugin install llm-kit@plugins-kit`, and
  their too-old messages name the update command. workflow-kit and
  yaml-data-editor-kit retain `install: "auto"` because llm-kit is REQUIRED.
- Option B: declare `install: "auto"` in every migrated consumer. This avoids
  point-of-need installation but turns optional use into fleet-wide
  provisioning.
- Option C: add an automatic edge to a legacy freeze release. This installs
  llm-kit for legacy-only machines but exceeds the signed rule that a frozen
  provider receives only a version bump plus README and plugin-description
  pointers.

Recommendation: Option A. It follows the repository's REQUIRED versus optional
dependency rule and gives every affected machine an actionable install path.

Publication order is dependency-driven:

1. `[USER: publish]` publishes llm-kit first. No stability declaration is a
   prerequisite, and no consumer migration has landed.
2. llm-kit-only hardening releases may follow, each with `[USER: publish]`.
   `[USER: stability]` then names one published version.
3. `[USER: publish]` publishes the three pointer-only freeze releases.
4. After stability and the freezes, land M3-M9 under the chosen short hold, run
   M10 over dev's complete migrated tree, and do not activate a consumer before
   every M10 gate passes.
5. `[USER: publish]` publishes migrated consumers in M11. Required consumers
   precede optional consumers if the projection is split; git-kit and p4-kit
   remain together because they share a generator.
6. Keep the legacy releases installable for at least two llm-kit minor release
   lines and until all retirement gates pass.
7. `[USER: delete]` authorizes legacy deletion; `[USER: publish]` publishes the
   deletion projection.

M11 may be one coordinated publish after all targeted suites pass. Separate
version bumps still identify each affected plugin.

Consumer rollback is a forward release: revert that consumer's imports,
launcher paths, and manifest declarations to the frozen providers, then bump the
consumer past every burned version. Do not rewrite or republish an existing
version.

## 4. Persistent state and launcher paths

Do not copy, rename, or split these shared inputs during activation:

- project credentials and config below
  `.local-data/plugins-kit/llm-scripting-kit/`, including the superseded
  `.local-data/llm-scripting-kit/` read path;
- user credentials, `config.yaml`, `usage-verdicts.json`, and
  `frontdoor-access.jsonl` below
  `~/.claude/plugins/data/plugins-kit/llm-scripting-kit/`;
- fleet config `~/.claude/config/llm-scripting-kit.yaml`;
- `$MODEL_ENDPOINTS_REGISTRY` or
  `~/.claude/config/model-endpoints.yaml`;
- default job database `.local-data/plugins-kit/job-kit/runs.sqlite3`;
- established environment-variable names and persisted job/pipeline identities.

Both implementations can observe the same advisory usage-verdict cache; its
last-writer-wins behavior remains unchanged. Do not run old and final job
workers against one job database during handover. Stop the old worker, then
start the llm-kit worker. Pipeline takeover follows its lease and fencing
contract.

Executable paths do change. Maintained launchers must resolve
`~/.claude/plugins/data/plugins-kit/llm-kit/.venv/.../llm-kit` and use grouped
commands. The root `plugins/llm-kit/bin/llm-kit` launcher owns the llm-kit data
root; it must not be replaced by a shim at a legacy path.

## 5. Freeze releases

Recommended freeze versions are the next minor versions: llm-scripting-kit
0.68.0, content-pipeline-kit 0.37.0, and job-kit 0.14.0. The user decides these
versions as part of `[USER: publish]`.

The signed scope is exact for each provider:

- Bump `.claude-plugin/plugin.json` and `pyproject.toml` to the chosen freeze
  version.
- Change only the plugin description to state that the provider is frozen and
  point to llm-kit.
- Add a README pointer and mapping. llm-scripting-kit maps its API, CLI, and
  `openrouter-account` skill. content-pipeline-kit maps its API and all of its
  final qualified registrations, including the four pipeline skills plus
  `llm-kit:pipeline-worker` and `llm-kit:run-ready-wave`. job-kit maps its API
  and commands to `llm-kit jobs`.

Do not edit legacy skill descriptions, package `__version__` constants,
registrations, runtime code, bootstrap declarations, or plugin-local
`CLAUDE.md` files in the freeze release. The shipped legacy implementations and
CLIs remain independently functional and do not import or delegate to llm-kit.

`[USER: deviation]` is required for any extra freeze edit. Options are: (A)
keep the signed scope above; (B) also change skill descriptions; (C) also align
package `__version__` constants. Recommendation: A. Skill descriptions can
affect registration selection, and the persisted/probed constants are runtime
surface, so neither belongs in a pointer-only release.

Freeze policy is maintainer-only material. Put the named freeze in the root
`CLAUDE.md` section every publisher reads and in repository docs, never inside
the shipped provider trees. Record the freeze-release commit for each provider.
Add a repository guard that diffs each frozen tree against that commit and
permits later differences only from an explicit allowlist of authorized fix
commits. Show the guard red with an unauthorized provider-tree edit, then green
after restoring it. An allowed fix is limited to security, critical
correctness, or installability, has its own version and targeted regression
test, and requires `[USER: publish]`.

## 6. Bootstrap declarations

| Site | Activation change | Deletion change |
|---|---|---|
| `plugins/llm-scripting-kit/bootstrap.json` | None; keep `llm_scripting_kit`, default config, and provider checks. | Delete with provider. |
| `plugins/content-pipeline-kit/bootstrap.json` | None; keep `content_pipeline`, legacy owner install, config, and data declarations. | Delete with provider. |
| `plugins/job-kit/bootstrap.json` | None; keep `job_kit`, legacy owner install, and probes. | Delete with provider. |
| `plugins/llm-kit/bootstrap.json` | Keep one `llm_kit` shared library and `bootstrap_lib` import; do not add legacy imports. | Keep. |
| `plugins/awesome-kit/bootstrap.json` | Optional shared import becomes `llm_kit`. | No additional change. |
| `plugins/task-kit/bootstrap.json` | Optional shared import and `$comment` become `llm_kit`; installation follows `[USER: install]`. | No additional change. |
| `plugins/{git-kit,p4-kit}/bootstrap.json` | Optional shared import becomes `llm_kit`. | No additional change. |
| `plugins/workflow-kit/bootstrap.json` | Automatic provider and shared import become llm-kit/`llm_kit`; align probes. | No additional change. |
| `plugins/yaml-data-editor-kit/bootstrap.json` | Automatic provider becomes llm-kit; both legacy imports collapse to `llm_kit`; align probes. | No additional change. |
| `.claude/bootstrap.json` | No legacy name exists; no change. | No change. |
| `bootstrap_lib.engine._FIRST_PARTY_LIBS` | Keep both names through freeze. | Remove `llm_scripting_kit` after all consumers and providers are gone. |

Preserve existing `.claude-plugin/plugin.json` dependency arrays. Do not add an
edge to a legacy provider or llm-kit: awesome-kit keeps bootstrap plus
skills-kit, task-kit keeps bootstrap plus skills-kit plus awesome-kit, and the
other inventoried consumers keep bootstrap.

Every consumer that imports `llm_kit` must declare in its own `pyproject.toml`
every third-party package reachable from the imported llm-kit paths. Run
`tests/bootstrap/test_dependency_completeness.py` in every consumer increment;
a guarded or lazy cross-plugin import does not waive the declaration.

## 7. Repository inventory and tests

- `.claude-plugin/marketplace.json` is derived. Regenerate it through the
  repository generator/publisher; never hand-edit it. The llm-kit publication
  adds its listing, freeze releases update three listings, consumer releases
  update affected versions, and deletion removes three listings.
- Root `CLAUDE.md`: at M1, move llm-kit from the dev-only list
  to the published overview. At deletion, remove the three providers from the
  published list. During coexistence, the launcher-shim exception names
  job-kit, llm-kit, and llm-scripting-kit; after deletion it names llm-kit but
  retains unrelated exceptions.
- `plugins/CLAUDE.md`: update the shared-library consumer table, provider
  examples, optional-dependency guidance, and consolidation exception at the
  matching publication stage. Preserve the rule that the consumer owns
  absence/too-old behavior.
- M9 carries only stage-neutral migration wording. M1, M2, M11, and M13 own
  llm-kit publication, freeze, consumer activation, and deletion-stage edits;
  M9 does not anticipate or restate those publication states.
- Keep all three legacy test suites throughout freeze. A frozen fix must pass
  its provider suite.
- Keep `tests/llm-kit` parity tests, `repoint.py`, `repoint-map.json`,
  `repoint-dispositions/`, `porting-ledger.json`, and
  `scripts/llm_kit_repoint.py` throughout freeze. Keep the ignored repoint
  mirror under `tmp/` reproducible rather than committed.
- At deletion, first convert parity coverage to final-only behavioral tests.
  Then remove `test_*_parity.py`, `test_copy_inventory.py`,
  `test_repoint_generator.py`, `test_repointed_suites.py`, the repoint metadata
  and tool, and all mirror-owned paths: the three suite directories,
  `tmp/{test_support,legacy_names}`, `tmp/conftest.py`, and
  `tmp/sitecustomize.py`.
- Remove the four content-pipeline-kit entries and one llm-scripting-kit entry
  from both `EXPECTED_DUPLICATE_SKILLS` sets only when the corresponding legacy
  skill directory is deleted.

Each guard added for this migration must be shown to fail by restoring one
prohibited legacy consumer reference, then pass after the reference is removed.

## 8. Publication sequence and dev-only projection

1. `[USER: publish]` removes llm-kit's `published: false` and publishes M1 before
   any consumer migration lands. `[USER: stability]` is not an M1 prerequisite.
2. Each llm-kit hardening release needs `[USER: publish]`; `[USER: stability]`
   then names a published version and gates M2 plus M3-M11.
3. `[USER: publish]` publishes M2's pointer-only freeze releases and enforcement
   guard before consumer migration lands.
4. Under option 1, M3-M9 land only after whole-tree holds bind them. Under the
   recommended option 2, land them together immediately before M10. Any publish
   before M11 names only safe plugins with repeatable `--only`.
5. M10 scans dev after M3-M9 and proves old/final resume plus rollback. It gates
   consumer activation, not M1's provider publication.
6. `[USER: publish]` removes temporary consumer holds and publishes M11's
   migrated consumers with their version bumps and final-only bootstrap changes.
7. `[USER: publish]` authorizes each llm-kit minor release used by the minimum
   freeze interval. `[USER: delete]` and `[USER: publish]` authorize M13.

While `published: false` remains in llm-kit's manifest, `publish.py` derives it
as dev-only: the marketplace listing is absent and its files are held back from
the release projection even if its commits are listed. Removing that field is
the load-bearing publication action. `--exclude-dev-only` changes commit
bookkeeping only; it cannot publish llm-kit or override file hold-back.

## 9. Deletion checklist

Deletion is eligible only after two llm-kit minor release lines, zero maintained
legacy consumer references, and the activation resume/rollback suite remains
green. The repository can measure source and manifest references, qualified
registration inventories, fixture-based old/final resume behavior, rollback
with llm-kit registration disabled, and the published version interval. It
cannot inspect every user machine or prove that no external script, nonterminal
job, or pipeline lease retains a legacy identity.

`[USER: delete]` is therefore an operational judgment, not a mechanically
provable zero. Its evidence packet lists the repository measurements above,
known automation owners and their migration status, reports from any machines
the owner chose to inventory, unresolved unknowns, and the rollback window. Do
not report an ecosystem-wide zero from the repository grep.

After `[USER: delete]`:

- Remove `plugins/{llm-scripting-kit,content-pipeline-kit,job-kit}/` in full.
- Remove `tests/{llm-scripting-kit,content-pipeline-kit,job-kit}/` in full.
- Remove each provider's marketplace listing through regeneration.
- Remove legacy shared-library and provider declarations, including
  `llm_scripting_kit` from `_FIRST_PARTY_LIBS`, only after a repository-wide
  import/launcher scan is clean.
- Remove the five duplicate-skill allowlist entries from both bootstrap tests.
- Replace parity/differential coverage with final-only coverage, then remove the
  repoint generator, maps, dispositions, ledger, tests, and ignored mirror.
- Remove stale legacy examples from standing docs and generated indexes while
  keeping dated design and incident records accurate.
- Remove legacy launcher exceptions from root `CLAUDE.md` and update
  `plugins/CLAUDE.md` ownership tables.
- Preserve legacy state paths and persisted identifiers unless the user accepts
  a separate state-migration design with rollback and mixed-version tests.
- Regrep the original expression over the original corpus. Every remaining hit
  must be a compatibility identifier, state path, or dated historical record
  with an explicit allowlist reason.

## 10. Open questions for the user

1. `[USER: hold]` How are M3-M9 kept out of release projections before M11? Recommendation: keep them out of release-producing `dev` until M10-M11; a whole-tree hold blocks every unrelated fix to awesome-kit, git-kit, p4-kit, skills-kit, task-kit, and workflow-kit and forces every intervening publish to name safe plugins with repeatable `--only`.
2. `[USER: install]` How do legacy-only machines acquire llm-kit? Recommendation: manual edges plus exact install/update diagnostics for optional consumers; retain automatic edges only for REQUIRED consumers.
3. `[USER: deviation]` May freeze releases change anything beyond version metadata, README, and plugin description? Recommendation: no; keep skill descriptions, package `__version__`, runtime, registrations, bootstrap, and plugin-local `CLAUDE.md` unchanged.
4. What published version starts the two-minor freeze clock? Recommendation:
   after M1, declare 0.2.0 stable and retain providers through 0.2.x and 0.3.x.
5. Should legacy-named state paths survive provider deletion? Recommendation: yes; make any physical migration a separate dual-read/write design with rollback tests.
6. What operational evidence is sufficient for `[USER: delete]`? Recommendation: require affirmative migration from known automation owners and machine reports where available, disclose unknown external use, and make the final choice as a user judgment rather than claiming a fleet-wide zero.
7. Should consumer releases be one projection or several? Recommendation: one coordinated publish after all targeted suites pass, with separate plugin version bumps.

## 11. Implementation increments

Each increment is sized for one delegated worker. No worker publishes without
the corresponding user marker. M1 publishes llm-kit before any consumer
migration lands. `[USER: stability]` then gates M2-M11. Under option 1, M3-M9
land only after the whole-tree holds bind them. Under option 2, they land
together immediately before M10.

1. **M1 - First llm-kit publication.** Remove `published: false`; update the
   llm-kit manifest, version, description, docs, derived marketplace output, and
   section 7's llm-kit-publication guidance. Publish only llm-kit with `--only`.
   Run `tests/llm-kit`, `claudx --all` over its five skills, agent, workflow, and
   grouped CLI, then publisher preflight. No stability declaration is required;
   execution requires `[USER: publish]`. Any llm-kit-only hardening release also
   requires `[USER: publish]`; after M1, `[USER: stability]` names a published
   version.

2. **M2 - Pointer-only freeze releases and enforcement.** Apply only section
   5's signed metadata/README scope, add the root named freeze, record each
   freeze commit, make section 7's freeze-publication guidance edits, and add
   the allowlisted tree-diff guard. Publish only the three providers with
   repeatable `--only`. Run each legacy suite, plugin-doc/skill-material tests,
   and demonstrate the freeze guard red. Dependencies: M1 and
   `[USER: stability]`; extras require `[USER: deviation]`; execution requires
   `[USER: publish]`.

3. **M3 - workflow-kit migration.** Change runtime modules, bootstrap manifest,
   examples, generated material, docs, and `tests/workflow-kit/`; raise Python
   declarations and CI to 3.12. Declare every reached third-party package and
   run dependency completeness plus the workflow-kit suite. Dependencies: M2
   and the chosen hold/install policies.

4. **M4 - yaml-data-editor-kit migration.** Change the dispatch package,
   bootstrap manifest, plugin description/docs, and owning tests; raise Python
   declarations and CI to 3.12. Declare every reached third-party package and
   run dependency completeness plus the yaml-data-editor-kit suite.
   Dependencies: M2. Its dev-only projection needs no published-plugin hold.

5. **M5 - skills-kit job-emitter migration.** Change the emitter/checker, lane
   defaults, consumer manifest/docs, and owning tests; raise Python declarations
   and CI to 3.12. Declare every reached third-party package and run dependency
   completeness plus `tests/skills-kit/test_emit_audit_jobs.py`. Dependencies:
   M2 and the chosen hold/install policies.

6. **M6 - git-kit/p4-kit review migration.** Change the shared generator, both
   runners/manifests/packaging files, generated skills/references, and owning
   tests. Declare every reached third-party package and run dependency
   completeness plus the runner, generator-drift, lane-prompt, retry-prose, and
   runner-drift tests. Dependencies: M2 and the chosen hold/install policies.

7. **M7 - task-kit migration.** Change `summary_ops.py`, `bootstrap.json`, all
   task-review tests, and packaging/CI from Python 3.10 to 3.12. Add distinct
   absent and too-old REFUSE diagnostics with install/update commands. Declare
   every reached third-party package and run dependency completeness plus the
   task-review tests. Dependencies: M2 and the chosen hold/install policies.

8. **M8 - awesome-kit migration.** Change orchestrate runtime modules,
   orchestration defaults including the OpenCode preflight's
   `llm-kit models resolve`, bootstrap manifest, skill references, and tests;
   raise Python declarations and CI to 3.12. Declare every reached third-party
   package and run dependency completeness plus the awesome-kit suite.
   Dependencies: M2 and the chosen hold/install policies.

9. **M9 - Dual-valid repository integration and stage-neutral docs.** Change
   bootstrap examples, probes, generators, and tests before M11 only when the
   result remains valid with either legacy or final libraries installed;
   preserve persisted identity constants. Update root `CLAUDE.md`,
   `plugins/CLAUDE.md`, omitted consumer docs, standing references, and index
   sources only with stage-neutral migration wording. Defer llm-kit-only
   bootstrap cutovers and consumer-publication state edits to M11. Run targeted
   bootstrap/repo tests, dependency completeness, and a Project-doc audit.
   Dependencies: M3-M8.

10. **M10 - Activation identity, reference, and rollback gates.** Add the
    durable repository scan over maintained source, manifests, launchers,
    qualified registrations, and CLI calls, with narrow allowlists for frozen
    providers, persisted identity/state, and dated records. Prove all three
    design gates: no unsupported old qualified reference; old-created resumable
    fixtures resume through old and final names; rollback fixtures disable
    llm-kit registration and resume through old names. Cover both worker skills,
    maintained launch flags, and persisted workflow, job, and pipeline
    references. Scan dev after M3-M9 have landed and show every guard red against
    a planted violation, then green after restoration. This durable gate remains
    after parity tests retire. Dependencies: M3-M9 and final registrations. It
    gates M11 consumer activation, not M1 provider publication.

11. **M11 - Consumer activation release.** Remove option 1 holds if chosen;
    apply deferred llm-kit-only bootstrap probe, owner-example, and generator
    cutovers; bump each consumer version; make section 7's consumer-publication
    edits; and regenerate marketplace output. Add no source migration beyond
    M3-M9. Rerun all consumer suites, targeted bootstrap/repo tests, dependency
    completeness, M10, and `claudx --all` for migrated surfaces. Dependencies:
    M2-M10 and `[USER: stability]`; execution requires `[USER: publish]`.

12. **M12 - Freeze evidence.** Record the two llm-kit minor lines, rerun M10,
    inventory known external automation, and assemble the operational evidence
    packet without claiming an ecosystem-wide nonterminal-record zero.
    Dependencies: M11 and two release lines; each release requires
    `[USER: publish]`.

13. **M13 - Legacy deletion.** Perform section 9's provider, test, parity,
    repoint, allowlist, and inventory removals; make section 7's deletion-stage
    guidance edits; and run final-only llm-kit tests, affected consumer suites,
    skill-material tests, M10 with its retirement allowlist, the original corpus
    scan, `claudx --all`, and publisher preflight. Dependencies: M12,
    `[USER: delete]`, and `[USER: publish]`.
