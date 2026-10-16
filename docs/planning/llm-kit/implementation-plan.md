# llm-kit implementation plan

Date: 2026-10-16

## Summary

- Build sequencing option A from `docs/reference/llm-kit-architecture.md` without reopening its 14 signed decisions.
- Keep llm-kit private with `"published": false` through the stability gate.
- Consolidate all three products into a quarantined `llm_kit._copy` baseline before moving any boundary.
- Reuse 5,276 collected legacy tests through a deterministic namespace re-pointer, then add direct differential checks.
- Land the exact import-direction guard before the first boundary move and prove that it fails.
- Restructure in dependency-layer order while preserving schemas, events, paths, environment names, failures, and concurrency behavior.
- Finish with the final `llm_kit` packages, CLI, launchers, skills, agent, workflow, rollback tests, and no private copy.
- Stop before `published: true`, marketplace generation, publish, consumer migration, freeze releases, or deletion.

## Contract and stopping point

The contract is `docs/reference/llm-kit-architecture.md` at revision 5,
commit `9b467783`, signed 2026-10-16. The target is a locally testable,
dev-only llm-kit whose final namespace and behavior pass the stability gate.
The old plugins remain unchanged and independently functional.

In this document, `path/**` grants one increment or leaf exclusive ownership
of every descendant. Brace groups enumerate their comma-separated literal
paths; they are not shell syntax. A parallel leaf may not edit a join-only
path. Each joined increment bumps llm-kit's versions together in:

- `plugins/llm-kit/.claude-plugin/plugin.json`
- `plugins/llm-kit/pyproject.toml`

No plugin `uv.lock` is created or committed. `bootstrap_guard.py` is copied
byte-for-byte from `plugins/bootstrap/bootstrap_lib/bootstrap_guard.py`.

## Premise checks

### P1 - Private publication hold: confirmed

Create `plugins/llm-kit/.claude-plugin/plugin.json` with `"published": false`.
This is sufficient to prevent an ordinary publish of other plugins from
shipping llm-kit:

- `scripts/regen_marketplace.py:132-170` treats only explicit false as
  unpublished and builds the listing from published manifests, so llm-kit has
  no marketplace entry.
- `scripts/publish.py:198-204` uses the same predicate.
- `scripts/publish.py:1268-1317` adds every dev-only plugin to the held set,
  removes `plugins/<name>/**` and `tests/<name>/**` from the projected tree,
  and restores master's copy only if one exists.
- `tests/repo-scripts/test_publish.py:1179-1187` proves a dev-only source file
  is absent from master while a published plugin advances.
- `tests/repo-scripts/test_publish.py:1498-1507` rejects a dev-only listing.

Therefore `.claude-plugin/marketplace.json` is not edited in this scope. The
manifest flips to published only after the user declares llm-kit stable and
authorizes the separately gated publish flow.

### P2 - One blind namespace rewrite: refuted

The copy is not import-clean after only
`llm_scripting_kit.* -> llm_kit.*`. Option A separates copying from boundary
restructuring, so increment 1 uses these private mappings:

| Legacy package | Private copy target |
|---|---|
| `llm_scripting_kit` | `llm_kit._copy.llm_scripting_kit` |
| `content_pipeline` | `llm_kit._copy.content_pipeline` |
| `job_kit` | `llm_kit._copy.job_kit` |

Measured executable absolute imports, excluding docstring examples:

| Package tree | Absolute self-imports | Absolute imports of `llm_scripting_kit` |
|---|---:|---:|
| `llm_scripting_kit` | 6 in `review_lane.py` | n/a |
| `content_pipeline` | 99 in 33 files | 13 in 2 files |
| `job_kit` | 0 | 10 in 3 files |

Outside those package trees, llm-scripting-kit has six more executable
self-imports in `custom_bootstrap.py` and `scripts/llm_scripting_kit_cli.py`;
job-kit has one in `lib/job_kit_entrypoint.py`.

Runtime string sites require classification, not text replacement:

- llm-scripting-kit has five loader/entry occurrences: its pyproject entry
  point, two Python `-m` argv targets, and two `frontdoor.sh` module targets.
  `frontdoor/server.py:494` is a sixth, display-only program name.
- content-pipeline-kit has two loader sites in
  `execution/interrupts.py:88,239`, plus the two-module provenance tuple at
  `provenance/record.py:249` and the static checker package at
  `scripts/check_consumer_contract.py:30`.
- job-kit has ten loader/entry/classifier sites: one top-level shared-lib set,
  five `_require_module` literals, two `import_module` literals, one Python
  `-m` argv target, and one pyproject entry point.

The rewrite tool must operate on parsed import and approved loader sites. Its
inventory test fails on every unclassified legacy-name occurrence.

### Do-not-touch list

- Do not change `plugins/bootstrap/bootstrap_lib/interrupt_contract.py:58`;
  the legacy `VALIDATOR_MODULE` stays frozen. llm-kit adds its own validator
  probe in `llm_kit.execution`.
- Do not change `llm-scripting-kit.json-schema-subset/v1`, interrupt envelope
  names, execution-event schemas, event names, or canonical JSON spelling.
- Preserve legacy credential/config environment names, precedence, and paths,
  including `MODEL_ENDPOINTS_REGISTRY`, `OPENROUTER_API_KEY`,
  `LLM_SCRIPTING_KIT_USAGE_SESSION`, the llm-scripting-kit config/data roots,
  and `usage-verdicts.json`. The signed exception is the llm-kit CLI command.
- Preserve job schema 12, pipeline schema 10, spend-ledger schema 1, every DDL
  statement, migration prefix, pragma order, and isolation posture.
- Do not rewrite `bootstrap_lib` or third-party module identities such as
  `mlx_lm.server`.
- Do not edit the three old plugin trees. Human-facing old names in the copy
  change only through a named final-interface test, never through bulk replace.
- Do not modify any vendored `bootstrap_guard.py`; copy the canonical bytes.

### P3 - Test reuse and measured Windows cost: confirmed

The legacy suites remain in place and a harness under `tests/llm-kit/` creates
a transformed mirror under pytest's temporary directory. It rewrites only the
declared import/loader map, runs old and llm-kit cases in separate processes,
and asserts the llm-kit process imported files only from `plugins/llm-kit/`.
No forked test corpus is maintained.

Measured on Windows with `PYTHONDONTWRITEBYTECODE=1` and
`-p no:cacheprovider`:

| Suite | Files | Collected | Representative file | Pytest / wall |
|---|---:|---:|---|---:|
| llm-scripting-kit | 62 | 1,926 | `test_completion_contract.py` (72 pass) | 0.37s / 0.71s |
| content-pipeline-kit | 98 | 2,732 | `test_execution_store.py` (61 pass) | 3.00s / 9.76s |
| job-kit | 21 | 618 | `test_store.py` (27 pass) | 1.05s / 1.37s |

Collection took 1.61s, 1.56s, and 0.65s respectively. These are measured
representative costs, not estimates for full differential runs.

## Ordered increments

### I1 - Private consolidated parity baseline

- Goal: deliver the maximum stability value in one increment: one installable, dev-only plugin containing all three unchanged behavior sets and a reusable old-vs-copy harness.
- Paths: `plugins/CLAUDE.md`; `plugins/llm-kit/{.claude-plugin/plugin.json,bootstrap.json,pyproject.toml,README.md}`; `plugins/llm-kit/lib/llm_kit/{__init__.py,bootstrap_guard.py,_copy/**}`; `tests/llm-kit/{conftest.py,repoint.py,repoint-map.json,test_copy_inventory.py,test_repointed_suites.py}`; `plugins/bootstrap/{bootstrap_lib/engine.py,.claude-plugin/plugin.json,pyproject.toml}`; `tests/bootstrap/{test_transient_import_retry.py,test_dependency_completeness.py}`.
- Fixed interface: only top-level `llm_kit`; empty root initializer; P2 private mappings; Python 3.12; standard-library base; signed extras; `shared_libs` publishes `llm_kit`; no llm-kit config seeding; dependency `bootstrap`; `published: false`.
- Check `C1-copy-parity`: `uv run --extra dev pytest tests/llm-kit/test_copy_inventory.py tests/llm-kit/test_repointed_suites.py tests/bootstrap/test_transient_import_retry.py tests/bootstrap/test_dependency_completeness.py -v`. Prove red by restoring one old absolute import in each copy and removing `llm_kit` from bootstrap's first-party tuple; revert and pass.
- Dependencies: signed architecture only. Parallel: yes after the skeleton and map are fixed. Leaves `copy-lsk`, `copy-content`, and `copy-jobs` own matching `_copy/<package>/**` sources and parity cases; each is done when its representative file passes through the re-pointer. Manifest/version files are join-only.

### I2 - Import-direction guard before restructuring

- Goal: make every final-package move subject to the signed 16-component DAG.
- Paths: `tests/llm-kit/test_import_graph.py` and the two llm-kit version files.
- Fixed interface: architecture lines 103-128 exactly; eager, local, `TYPE_CHECKING`, and literal dynamic imports count; root initializers re-export nothing; final packages cannot import `_copy`; jobs and pipeline execution cannot cross-import; product DDL and migrations stay product-owned. `_copy` imports only within `_copy` until I9.
- Check `C2-import-direction`: `uv run --extra dev pytest tests/llm-kit/test_import_graph.py -v`. Prove red with a temporary completion -> adapters import, observe both packages, mode, and line, revert, and pass.
- Dependencies: I1. Parallel: no.

### I3 - Layer 0 foundations

- Goal: establish the dependency-free packages before any package depends on them.
- Paths: `plugins/llm-kit/lib/llm_kit/{schema/**,registry/**,storage/**,pipeline/core/**,scaffold/**}`; `tests/llm-kit/test_{schema,registry,storage,pipeline_core,scaffold}_parity.py`; join-only version files.
- Fixed interface: architecture lines 78-95; no root re-exports; registry performs no HTTP; storage contains no product DDL or migration loop.
- Check `C3-layer-0`: run the five parity files and import guard. Prove red in each leaf by changing one copied return/exception fixture, revert, and pass.
- Dependencies: I2.
- Parallel: yes. Leaves `schema`, `registry`, `storage`, `pipeline-core`, and `scaffold` own one subtree and one test each; done means legacy fixtures match and that parity file passes.

### I4 - Layer 1 contracts and artifact port

- Goal: create neutral completion/execution contracts and the artifact layer.
- Paths: `plugins/llm-kit/lib/llm_kit/{completion/**,execution/**,pipeline/artifacts/**}`; `tests/llm-kit/test_{completion,execution,pipeline_artifacts}_parity.py`; join-only version files.
- Fixed interface: completion holds only protocols and neutral types; execution owns the llm-kit validator probe; artifacts depend only on pipeline core.
- Check `C4-layer-1`: run three parity files and the guard. Prove red by moving one filled capability record into completion, revert, and pass.
- Dependencies: I3.
- Parallel: yes. Leaves `completion`, `execution`, and `pipeline-artifacts` own exclusive subtrees and one test each; each test is its done statement.

### I5 - Layer 2 integrations and analysis

- Goal: isolate concrete transports from reporting behavior.
- Paths: `plugins/llm-kit/lib/llm_kit/{adapters/**,pipeline/analysis/**}`; `tests/llm-kit/{test_adapters_parity.py,test_pipeline_analysis_parity.py}`; join-only version files.
- Fixed interface: adapters depend only on completion/registry; analysis only on pipeline core/artifacts; optional imports occur at call sites and missing selected capabilities refuse.
- Check `C5-layer-2`: run both parity files and the guard. Prove red with an adapters -> dispatch import, revert, and pass.
- Dependencies: I4.
- Parallel: yes. Leaves `adapters` and `pipeline-analysis` own disjoint package/test roots; passing their parity file is the standalone done state.

### I6 - Layer 3 composition services

- Goal: provide configured dispatch and the HTTP front door without product state machines.
- Paths: `plugins/llm-kit/lib/llm_kit/{dispatch/**,frontdoor/**}`; `tests/llm-kit/{test_dispatch_parity.py,test_frontdoor_parity.py}`; join-only version files.
- Fixed interface: immutable construction spec; injected `completion.BackendFactory`; omitted runner stays omitted; both packages depend only on completion, registry, and adapters.
- Check `C6-layer-3`: run both parity files and the guard. Prove red by passing `runner=None` to a captured constructor, revert, and pass.
- Dependencies: I5.
- Parallel: yes. Leaves `dispatch` and `frontdoor` own exclusive subtrees/tests; each parity file is a standalone done statement.

### I7 - Jobs and pipeline runtime

- Goal: establish the flat job product and pipeline call-policy product above the completed lower layers.
- Paths: `plugins/llm-kit/lib/llm_kit/{jobs/**,pipeline/runtime/**}`; `tests/llm-kit/{test_jobs_parity.py,test_pipeline_runtime_parity.py,fixtures/job-schema-12.sql,fixtures/spend-schema-1.sql}`; join-only version files.
- Fixed interface: schema-12 jobs retain the unsupported/undetected one-process rule; runtime preserves retry, cache, budget, spend, constructor options, and spend schema 1.
- Check `C7-products`: run both parity files and the guard. Prove red by changing one destination DDL byte, revert, and pass.
- Dependencies: I6.
- Parallel: yes. Leaves `jobs` and `pipeline-runtime` own disjoint package/test/fixture paths; DDL/API parity is each leaf's done statement.

### I8 - Leased pipeline execution

- Goal: move schema-10 pipeline execution after runtime is fixed.
- Paths: `plugins/llm-kit/lib/llm_kit/pipeline/execution/**`; `tests/llm-kit/{test_pipeline_execution_parity.py,fixtures/pipeline-schema-10.sql}`; llm-kit version files.
- Fixed interface: one dispatcher lease/fence per run, expiring unit claims, monotonic fences, stale-fence refusal, distinct-run concurrency, and product-owned migrations.
- Check `C8-pipeline-execution`: run its parity file and the guard. Prove red by removing a stale-fence predicate, revert, and pass.
- Dependencies: I7. Parallel: no.

### I9 - Final composition and stability gate

- Goal: expose only final public names, prove cross-version state behavior, and remove the private copy.
- Paths: `plugins/llm-kit/lib/llm_kit/{cli/**,__init__.py,pipeline/__init__.py,_copy/**}`; `plugins/llm-kit/{bin/llm-kit,bin/llm-kit.cmd,scripts/llm_kit_cli.py,skills/**,agents/**,workflows/**,README.md,bootstrap.json,pyproject.toml}`; `tests/llm-kit/{repoint-map.json,test_{cli,persisted_state,verdict_cache,registration,launcher}_parity.py,fixtures/{events,interrupts,cli}/**}`; `tests/repo-scripts/{test_launcher_shim_data_root_redirect.py,test_python_invocation_standard.py}`.
- Fixed interface: `llm-kit = llm_kit.cli:main`; groups `account`, `completion`, `models`, `jobs`, `pipeline`, `frontdoor`, `local`; architecture line 219 registrations; venv-first POSIX/cmd launchers with both refusals; empty root initializers; no `_copy`.
- Check `C9-stability`: run all `tests/llm-kit/`, the three legacy suite directories, the two launcher tests, and `tests/bootstrap/test_bootstrap_guard.py` with targeted pytest commands; run `claudx --all` and exercise every CLI group, one skill, the agent, and the workflow. Prove red with one old qualified name and one changed event byte, revert, and pass.
- Dependencies: I8.
- Parallel: yes before join. Leaves `cli-launchers`, `registrations`, and `cross-state-parity` own CLI/bin/scripts, skills/agents/workflows, and parity tests/fixtures respectively; each has a cheap targeted check and standalone done statement. Join alone updates manifests, removes `_copy`, and runs `C9-stability`.

## Differential parity method

1. Run each legacy suite unchanged to establish its baseline.
2. Run the same test sources in a separate process through the re-pointer.
   Assert imported source paths are under `plugins/llm-kit`, so an installed or
   legacy package cannot create a false pass.
3. For API parity, apply the same call vectors to old and llm-kit modules and
   compare values, exception type/message, warnings, writes, and injected-call
   arguments. Identity-only differences require a named fixture entry.
4. For jobs, create every migration prefix with old and llm-kit code and compare
   `sqlite_master`, version rows, pragmas, isolation, canonical JSON,
   interrupts, event rows, and terminal state against
   `tests/llm-kit/fixtures/job-schema-12.sql`.
5. For pipeline execution, perform the same prefix comparison through schema
   10 and run mixed old/new dispatcher, worker, takeover, stale-fence, and
   distinct-run tests against `pipeline-schema-10.sql`.
6. For spend state, compare fresh schema 1, autocommit, synchronous selection,
   halt rows, and ledger bytes against `spend-schema-1.sql`.
7. Compare emitted event and interrupt documents byte-for-byte with fixtures;
   do not normalize schema, event, plugin, timestamp-field, or JSON spelling.
8. Run barrier-synchronized old/new verdict writers for same-session,
   different-session, and stale-AVAILABLE resurrection. Assert parseable
   legacy shape and last-writer-wins, not merged retention.
9. Run old and llm-kit CLIs with the same argv suffix, stdin, filesystem, and
   environment. Diff exit code, stdout, stderr, and writes. Normalize only the
   executable token where usage text necessarily names `llm-kit`; help-tree
   structure has its own final-interface fixture.
10. Resume llm-kit-created nonterminal job and pipeline records with the old
    plugins. Exercise old and final qualified registrations from old-created
    resumable fixtures, then disable llm-kit registration and resume by the old
    names.

## Import-direction guard

The guard lives in `tests/llm-kit/test_import_graph.py` and lands in I2, before
any final component receives behavior. It parses the entire
`plugins/llm-kit/lib/llm_kit` tree, records eager/local/`TYPE_CHECKING`/literal
dynamic modes, and reports source package, target package, mode, path, and line.
It encodes the exact adjacency set rather than inferred layer numbers.

The counterfactual proof is mandatory: add one real forbidden completion ->
adapters import, run `C2-import-direction` and observe red, revert it, and run
green. I9 also proves the quarantine exception is gone by requiring `_copy` to
be absent.

## Risks and controls

- Copy drift: the inventory test compares every legacy source path with its
  classified copy until that module moves; a legacy edit makes the check red.
- False parity through import leakage: each side runs in its own process with a
  scrubbed path and asserts every module's `__file__` root.
- Bulk rewrite damage: parsed imports and an explicit loader-site ledger replace
  global text substitution; every unmatched old-name occurrence is reviewed.
- Optional dependency leakage: import-matrix tests use only the extras reachable
  from each package; importing completion remains standard-library only.
- Persisted-state drift: checked-in DDL/event fixtures and old/new rollback tests
  cover the bytes, not only successful calls.
- Windows-only launcher defects: both shims run through the repository launcher
  tests, including redirected-data-root and cached-copy refusal.
- Parallel conflict: leaves own disjoint destination and test roots; manifests,
  mapping changes, copy deletion, and version bumps belong only to the join.

## Not covered by this plan

- Flipping llm-kit to `published: true` or generating its marketplace entry.
- Running `scripts/publish.py` or any other publish action.
- Migrating awesome-kit, git-kit, p4-kit, workflow-kit,
  yaml-data-editor-kit, skills-kit, external customers, launch flags, or
  maintained resumable references.
- Raising consumer Python declarations and CI matrices.
- Version-bumping or editing the three old plugins for their freeze releases.
- Starting the two-minor-version freeze clock or deleting any old plugin.

Stopping after I9 is informed: llm-kit is stable and locally verified, remains
structurally unable to ship, and leaves every consumer and old registration on
its pre-merge implementation.

## User decisions needed

None for I1-I9. After I9, the user must separately declare llm-kit stable and
authorize publication before `published` changes or publish tooling runs.

## Design defects found

None. The refuted blind-rewrite premise is an implementation-premise defect,
not a defect in the signed architecture; the architecture's copy-first option A
requires the quarantined baseline used here.
