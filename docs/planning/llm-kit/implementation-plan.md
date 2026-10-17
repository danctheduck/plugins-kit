# llm-kit implementation plan

Date: 2026-10-16

## Summary

- Build sequencing option A from `docs/reference/llm-kit-architecture.md` without reopening its 14 signed decisions.
- Make plugin-code and test changes in `$DEVROOT/plugins-kit2`; keep this plan and task records in their owning checkouts.
- Keep llm-kit private with `"published": false` through the stability gate.
- Generate one serial quarantined copy after three parallel per-suite test-disposition ledgers reconcile all 5,276 tests.
- Reuse eligible legacy tests from an ignored in-repo mirror that preserves repository-relative paths, fixtures, helpers, and child-process import isolation.
- Land the exact import-direction guard before restructuring, including the CLI-owned top-level bootstrap guard, and prove that it fails.
- Repoint tests and patch targets to moved code at every increment so parity failures do not accumulate until final composition.
- Compare normalized legacy and llm-kit failure sets; do not require a green legacy baseline.
- Finish with final packages, CLI, launchers, registrations, rollback tests, and no private copy.
- Stop before publication, consumer migration, freeze releases, or deletion.

## Contract and execution root

The contract is `docs/reference/llm-kit-architecture.md` at revision 5,
commit `9b467783`, signed 2026-10-16. The target is a locally testable,
dev-only llm-kit whose final namespace and behavior pass the stability gate.
The old plugins remain unchanged and independently functional.

Every implementation, resync, and validation command in this plan runs as:

```bash
cd "$DEVROOT/plugins-kit2" && <command>
```

All paths below are repository-relative to that checkout. Documentation and task
records remain in their owning checkouts. No command in this plan changes the
branch or creates a worktree.

In this document, `path/**` grants one serial increment or parallel leaf
exclusive ownership of every descendant. Brace groups enumerate literal paths;
they are not shell syntax. A parallel leaf may not edit a join-only path. Each
joined increment bumps llm-kit's versions together in:

- `plugins/llm-kit/.claude-plugin/plugin.json`
- `plugins/llm-kit/pyproject.toml`

No plugin `uv.lock` is created or committed. The top-level
`llm_kit.bootstrap_guard` is copied byte-for-byte from
`plugins/bootstrap/bootstrap_lib/bootstrap_guard.py` and classified as
CLI-owned startup support. No other top-level implementation module is exempt
from the component graph.

For I3-I8, the serial join owns the moved source under `_copy`,
`tests/llm-kit/repoint-map.json`, and `tests/llm-kit/porting-ledger.json`.
Each moved `_copy` module becomes a generated re-export shim of its final target;
the map rewrites imports, loader strings, and `patch`/`setattr` targets to the
final name in the same join. The affected re-pointed suite must pass for that
increment to complete. Parallel leaves never edit these migration join paths.

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
| `bootstrap_guard` | `llm_kit.bootstrap_guard` |

The fourth row is required by `plugins/job-kit/lib/job_kit/__init__.py:12` and
`plugins/job-kit/lib/job_kit/cli.py:420`. The architecture assigns the legacy
guard to `cli`, while `jobs` consumes it during import and CLI re-exec; I2
therefore permits only `cli` and `jobs` to import the CLI-owned root module.

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
  `plugins/llm-scripting-kit/lib/llm_scripting_kit/frontdoor/server.py:494`
  is a sixth, display-only program name.
- content-pipeline-kit has two loader sites in
  `execution/interrupts.py:88,239`, plus the two-module provenance tuple at
  `provenance/record.py:249` and the static checker package at
  `scripts/check_consumer_contract.py:30`.
- job-kit has ten loader/entry/classifier sites: one top-level shared-lib set,
  five `_require_module` literals, two `import_module` literals, one Python
  `-m` argv target, and one pyproject entry point.

The rewrite tool operates on parsed imports and approved runtime-string sites.
Its inventory test fails on every unclassified legacy-root occurrence.

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

### P3 - Test reuse requires an in-repo mirror and dispositions

The 181 legacy test files cannot be copied unchanged under pytest's temporary
directory. Fifty-six files contain 57 `parents[2]` anchors; the temporary mirror
loses `tests/conftest.py:114-293`, seven `test_support` importers, about 116
legacy-plugin path references, and about 280 quoted module strings. The latter
include 17 llm-scripting-kit patch/setattr targets and 64 strings in
`tests/content-pipeline-kit/test_package_imports.py`. Subprocess tests such as
`tests/content-pipeline-kit/test_execution_events.py:94` also inject a legacy
library through `PYTHONPATH`, so a parent-only import-root assertion can pass
falsely. About 51 files cover non-copied surfaces such as `bin`,
`custom_bootstrap`, scripts, and manifests; the disposition ledgers establish
the authoritative count.

I1 mirrors suites directly under ignored `tmp/` as
`tmp/{llm-scripting-kit,content-pipeline-kit,job-kit}/`, so `parents[2]` still
resolves to the repository root. It also mirrors the root `tests/conftest.py` as
`tmp/conftest.py` and `tests/test_support/**` as `tmp/test_support/**`. A generated
`tmp/sitecustomize.py` checks import roots in the parent and every subprocess and
rejects all legacy plugin libraries, including injected `PYTHONPATH` entries.
The re-pointer also rewrites every classified legacy plugin/lib path constant,
including `_SHARED_LIB`, before collection.

Each source test has one row in one of:

- `tests/llm-kit/repoint-dispositions/llm-scripting-kit.json`
- `tests/llm-kit/repoint-dispositions/content-pipeline-kit.json`
- `tests/llm-kit/repoint-dispositions/job-kit.json`

Each row records source path, `rewrite` / `legacy-only` / `deferred-to-I9`,
reason, rewrite classes, expected collection count, and baseline failures.
`test_copy_inventory.py` reconciles all 181 files and per-row collection totals
to 5,276; missing, duplicate, or unclassified rows fail.

Measured Windows full-suite costs, serial:

| Suite | Tests | Wall time |
|---|---:|---:|
| job-kit | 618 | 32s |
| content-pipeline-kit | 2,732 | 55s |
| llm-scripting-kit | 1,926 | 76s |
| Total | 5,276 | about 2.7 min |

An old-plus-repointed differential is about six minutes. Run it at the I1 and
I9 joins, not per parallel leaf.

## Ordered increments

### I1 - Serial private consolidated parity baseline

- Goal: create one installable dev-only plugin, one generated quarantined copy, and a trustworthy old-vs-copy harness.
- Paths: `CLAUDE.md`; `plugins/CLAUDE.md`; `plugins/llm-kit/{.claude-plugin/plugin.json,bootstrap.json,pyproject.toml,README.md}`; `plugins/llm-kit/lib/llm_kit/{__init__.py,bootstrap_guard.py,_copy/**}`; `tests/llm-kit/{conftest.py,repoint.py,repoint-map.json,repoint-dispositions/**,porting-ledger.json,test_copy_inventory.py,test_repointed_suites.py}`; `plugins/bootstrap/{bootstrap_lib/engine.py,.claude-plugin/plugin.json,pyproject.toml}`; `tests/bootstrap/{test_transient_import_retry.py,test_dependency_completeness.py}`; `tests/repo-scripts/{test_python_invocation_standard.py,test_nested_claude_sites.py,test_launch_paths.py,test_llm_cli_invocation_standard.py}`.
- Fixed interface: only top-level `llm_kit`; empty root initializer; P2 mappings; Python 3.12; signed extras; `shared_libs` publishes `llm_kit`; no config seeding; dependency `bootstrap`; `published: false`; `tests/llm-kit/conftest.py` sets `_BOOTSTRAP_GUARD_SKIP_REEXEC=1`; root `CLAUDE.md` lists llm-kit as dev-only.
- Check `C1-copy-parity`: from `$DEVROOT/plugins-kit2`, run the inventory, re-pointed differential, bootstrap tests, and all four repo-script tests named above. Compare normalized old/copy failure sets after ledger-declared differences; no side is required to be green. Prove red by omitting one path rewrite, allowing one child to import a legacy library, and removing one llm-kit path classification; restore and pass.
- Dependencies: signed architecture only. Parallel: only the three disposition-ledger leaves, each owning one JSON file. Their join is serial: freeze the map, generate all three copies and mirrors, apply join-owned guard changes, and run C1. `copy-lsk`, `copy-content`, and `copy-jobs` are not independent because package initializers cross-import and the inventory is whole-tree.
- Release coupling: adding `llm_kit` to `plugins/bootstrap/bootstrap_lib/engine.py` ships in the bootstrap publication that first contains I1, regardless of who runs that publication; llm-kit's dev-only hold does not hold back bootstrap.

### I2 - Import-direction guard before restructuring

- Goal: make every final-package move subject to the signed 16-component DAG.
- Paths: `tests/llm-kit/test_import_graph.py` and the two llm-kit version files.
- Fixed interface: architecture lines 103-128 exactly; eager, local, `TYPE_CHECKING`, and literal dynamic imports count; root initializers re-export nothing; final packages cannot import `_copy`; declared `_copy` shims may import final targets; jobs and pipeline execution cannot cross-import; DDL and migrations remain product-owned; `llm_kit.bootstrap_guard` is CLI-owned with only `cli` and `jobs` consumers.
- Check `C2-import-direction`: `cd "$DEVROOT/plugins-kit2" && uv run --extra dev pytest tests/llm-kit/test_import_graph.py -v`. Prove red with completion -> adapters and an unclassified root-module import; restore and pass.
- Dependencies: I1. Parallel: no.

### I3 - Layer 0 foundations

- Goal: establish `schema`, `registry`, `storage`, `pipeline.core`, and `scaffold`.
- Paths: final package subtrees and matching `tests/llm-kit/test_*_parity.py`; migration join paths; version files.
- Fixed interface: architecture lines 78-95; no root re-exports; registry performs no HTTP; storage contains no product DDL or migration loop.
- Check `C3-layer-0`: from `$DEVROOT/plugins-kit2`, run five parity files, affected re-pointed tests, and the import guard. Prove red in each leaf with one changed return or exception fixture; restore and pass.
- Dependencies: I2. Parallel leaves: `schema`, `registry`, `storage`, `pipeline-core`, `scaffold`; each owns one subtree and parity file. The serial join converts moved copy modules to shims and updates every import and patch target.

### I4 - Layer 1 contracts and artifact port

- Goal: create neutral `completion`, shared `execution`, and `pipeline.artifacts`.
- Paths: final package subtrees and matching parity files; migration join paths; version files.
- Fixed interface: completion holds only protocols and neutral types; execution owns the llm-kit validator probe; artifacts depend only on pipeline core.
- Check `C4-layer-1`: from `$DEVROOT/plugins-kit2`, run three parity files, affected re-pointed tests, and the guard. Prove red by moving one filled capability record into completion; restore and pass.
- Dependencies: I3. Parallel leaves: `completion`, `execution`, `pipeline-artifacts`; serial migration join.

### I5 - Layer 2 integrations and analysis

- Goal: isolate concrete `adapters` from `pipeline.analysis`.
- Paths: both final package subtrees and parity files; migration join paths; version files.
- Fixed interface: adapters depend only on completion/registry; analysis only on pipeline core/artifacts; optional imports occur at call sites and missing selected capabilities refuse.
- Check `C5-layer-2`: from `$DEVROOT/plugins-kit2`, run both parity files, affected re-pointed tests, and the guard. Prove red with adapters -> dispatch; restore and pass.
- Dependencies: I4. Parallel leaves: `adapters`, `pipeline-analysis`; serial migration join.

### I6 - Layer 3 composition services

- Goal: provide configured `dispatch` and the HTTP `frontdoor` without product state machines.
- Paths: both final package subtrees and parity files; migration join paths; version files.
- Fixed interface: immutable construction spec; injected `completion.BackendFactory`; omitted runner stays omitted; both packages depend only on completion, registry, and adapters.
- Check `C6-layer-3`: from `$DEVROOT/plugins-kit2`, run both parity files, affected re-pointed tests, and the guard. Prove red by passing `runner=None` to a captured constructor; restore and pass.
- Dependencies: I5. Parallel leaves: `dispatch`, `frontdoor`; serial migration join.

### I7 - Jobs and pipeline runtime

- Goal: establish flat `jobs` and `pipeline.runtime` above completed lower layers.
- Paths: both final package subtrees; parity files; job/spend schema fixtures; migration join paths; version files.
- Fixed interface: schema-12 jobs retain the unsupported/undetected one-process rule; runtime preserves retry, cache, budget, spend, constructor options, and spend schema 1.
- Check `C7-products`: from `$DEVROOT/plugins-kit2`, run both parity files, affected re-pointed tests, and the guard. Prove red by changing one destination DDL byte; restore and pass.
- Dependencies: I6. Parallel leaves: `jobs`, `pipeline-runtime`; serial migration join.

### I8 - Leased pipeline execution

- Goal: move schema-10 pipeline execution after runtime is fixed.
- Paths: final subtree; parity file; pipeline schema fixture; migration join paths; version files.
- Fixed interface: one dispatcher lease/fence per run, expiring unit claims, monotonic fences, stale-fence refusal, distinct-run concurrency, and product-owned migrations.
- Check `C8-pipeline-execution`: from `$DEVROOT/plugins-kit2`, run its parity file, affected re-pointed tests, and the guard. Prove red by removing a stale-fence predicate; restore and pass.
- Dependencies: I7. Parallel: no.

### I9 - Final composition and stability gate

- Goal: expose only final public names, complete deferred test dispositions, prove cross-version state behavior, and remove `_copy`.
- Paths: `plugins/llm-kit/lib/llm_kit/{cli/**,__init__.py,pipeline/__init__.py,_copy/**}`; llm-kit bin/scripts/skills/agents/workflows/README/bootstrap/pyproject surfaces; final parity tests and fixtures; disposition, mapping, and porting ledgers; I1 repo-script guards.
- Fixed interface: `llm-kit = llm_kit.cli:main`; groups `account`, `completion`, `models`, `jobs`, `pipeline`, `frontdoor`, `local`; architecture line 219 registrations; venv-first POSIX/cmd launchers with both refusals; empty root initializers; no `_copy`.
- Check `C9-stability`: from `$DEVROOT/plugins-kit2`, run all `tests/llm-kit/`, all three serial legacy suites, all I1 repo-script guards, and `tests/bootstrap/test_bootstrap_guard.py`; compare normalized old/final failure sets with ledger-declared intentional differences; run `claudx --all` and exercise every CLI group, one skill, the agent, and the workflow. Prove red with one stale patch target and one changed event byte; restore and pass.
- Dependencies: I8.
- Parallel leaves: `cli-launchers`, `registrations`, `cross-state-parity`; each owns disjoint paths and a targeted check. The serial join finalizes maps and ledgers, removes `_copy`, and runs the six-minute differential.

## Differential parity and resync method

1. Capture each legacy suite's normalized node-id failure set, including failure type and stable message. `tests/content-pipeline-kit/test_version_matches_plugin_json.py` is an expected baseline failure because `content_pipeline/__init__.py:26` is `0.36.0` while `plugin.json:3` is `0.36.2`.
2. Run only disposition=`rewrite` sources through the in-repo mirror in a separate process. `sitecustomize.py` rejects legacy import roots in that process and every child process.
3. Compare old and re-pointed failure sets after explicit ledger differences. Unexpected added or removed failures fail the differential; legacy green is not a precondition.
4. Apply identical call vectors to old and llm-kit APIs and compare values, exceptions, warnings, writes, and injected-call arguments. Identity-only differences require a named fixture.
5. Compare every job, pipeline, and spend migration prefix, DDL, version row, pragma, isolation mode, event, interrupt, terminal state, and canonical JSON byte.
6. Run mixed legacy/llm-kit dispatch, takeover, stale-fence, verdict-writer, CLI, resumable-record, and registration rollback cases. Normalize only the executable token where usage text necessarily names `llm-kit`.
7. Recreate the generated copy and mirror with `cd "$DEVROOT/plugins-kit2" && uv run python scripts/llm_kit_repoint.py sync`. The command refreshes unmoved modules, hashes, mirrors, and collection counts; it refuses unexplained drift in a moved module.
8. Record every legacy edit made after its module moved in `tests/llm-kit/porting-ledger.json` with legacy path, legacy commit, final target, porting disposition, and validating test. Inventory remains red until the edit is ported or explicitly rejected with evidence.

## Import-direction guard

`tests/llm-kit/test_import_graph.py` parses the complete llm-kit tree and reports
source component, target component, import mode, path, and line. It encodes the
signed adjacency set rather than inferred layer numbers. Its only quarantine
exception is a declared `_copy` re-export shim importing its mapped final target;
no final component may import `_copy`. It also classifies
`llm_kit.bootstrap_guard` as CLI-owned startup support and checks its two allowed
consumers. I9 requires `_copy` and every exception for it to be absent.

## Risks and controls

- Copy drift: inventory plus the resync and porting ledgers account for legacy edits before and after a module moves.
- False parity: in-repo depth, root fixtures/helpers, string-target rewrites, and child-process import checks close parent-only false passes.
- Non-copied tests: every file is explicitly legacy-only or deferred-to-I9; no skipped file disappears from the 5,276 denominator.
- Repo-wide path guards: I1 classifies llm-kit paths in all four scanners, including untracked-copy scans and bare-command text checks.
- Persisted-state drift: checked-in DDL/event fixtures and rollback tests compare bytes, not only successful calls.
- Parallel conflict: only disposition ledgers and disjoint final-package leaves run in parallel; maps, shims, manifests, versions, and copy generation are serial joins.

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

None in the signed architecture; all seven review findings concern
implementation-plan completeness and the architecture remains unchanged. One
scope decision from the I4 join is recorded here:

- The job thread pool and the pipeline `run_graph` are not unified in I4. They
  share no admission algorithm: `job_kit/run.py` submits every job to its pool
  up front and cancels the remainder on the first failure, while the pipeline
  `execution/scheduler.py` `run_graph` admits a unit only into a slot that has
  freed. Both stay unmoved in `_copy`, and `llm_kit.execution` holds only the
  probes, adapters and values the two products demonstrably share. The
  question is revisited at I7, when both runners are built and the two
  admission semantics can be compared on a real runner rather than inferred.

