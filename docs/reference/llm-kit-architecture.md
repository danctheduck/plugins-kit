# llm-kit Python package architecture

## Decision summary

- Create one published plugin, `llm-kit`, with one release version and one shared library, `llm_kit`.
- Use 16 import components with the exact acyclic edge set in this document; empty namespace initializers re-export nothing.
- Put schema, registry, storage, pipeline contracts, and reusable CLI scaffolding at the stable bottom of the graph.
- Split adapter mechanics from dispatch policy; move every identified upward import to its owning lower package.
- Keep flat jobs and leased pipeline execution separate above shared execution and storage mechanics.
- Preserve job schema 12, pipeline schema 10, spend-ledger schema 1, DDL bytes, pragmas, and event bytes throughout the freeze.
- Share legacy credentials, configuration, usage verdicts, and routing environment names during coexistence; do not fork state by plugin name.
- Publish only `llm_kit`; retaining the three old top-level imports is incompatible with side-by-side installation.
- Move every public old name by the prefix map below, including `cli.scaffold` and `cli.budget` as library APIs.
- Ship a venv-first `bin/llm-kit` and `.cmd` pair with redirected-data-root and cached-copy refusals.
- Rewrite frozen skill, agent, and workflow descriptions as redirect-only stubs so duplicate descriptions cannot auto-trigger.
- Require Python 3.12 and raise the four lagging consumer declarations during migration; this does not remove a bootstrap-supported host.
- User sign-off on the numbered decisions near the end is required before implementation.

## Ruling and scope

The controlling ruling from 2026-10-16 is:

> how we're going to do this is we're going to create a new plugin called llm-kit which will be the merged plugin. Once this plugin is stable we will migrate customers, freeze the other plugins for a while, and eventually delete them.

This document designs the Python package structure of that plugin.

It does not design the publication schedule, freeze duration, or deletion date; those belong to the migration plan and remain user decisions.

The design assumes a coexistence phase in which all four plugins can be installed:

- `llm-kit`
- `llm-scripting-kit`
- `content-pipeline-kit`
- `job-kit`

The design copies behavior into llm-kit; it does not move code out of the old plugins. The old plugins keep their import names and behavior throughout the freeze.

## Terms and package principles

### Mapping Martin's terms to this repository

The plugin is the release unit for REP, the Reuse-Release Equivalence
Principle. `llm-kit` has one plugin manifest, one version, one marketplace
entry, and one release cadence. A user reuses and receives the plugin as one
unit.

An import package is the component used here for CCP, CRP, ADP, SDP, and SAP analysis. Each listed package has a public boundary and allowed imports. The root `llm_kit` and grouping package `llm_kit.pipeline` contain no behavior and are not counted as components.

REP therefore does not imply independent versions for `llm_kit.jobs` and
`llm_kit.pipeline.execution`. A change in either increments the one llm-kit
version. This prevents the undeclared version skew that forced the old plugins
to probe one another, but it gives up TanStack's ability to release each npm
package independently.

### How the principles decide a boundary

- REP: everything in this document ships in one `llm-kit` release.
- CCP: code that changes for the same actor and reason belongs in one package.
- CRP: a consumer should not import or initialize features it does not use.
- ADP: every allowed import points down the graph; there are no package cycles.
- SDP: volatile application packages depend on stable contracts and utilities.
- SAP: stable packages expose protocols and value contracts where variation is expected.

SAP is not a command to add an interface to every function. Frozen concrete
formats such as canonical JSON and SQLite connection posture are intentionally
concrete. Their stability comes from compatibility tests and append-only change
rules. The planned abstractness values below make those exceptions visible.

## Proposed source tree

The plugin owns this library shape:

```text
plugins/llm-kit/
  lib/
    llm_kit/
      __init__.py
      schema/
      completion/
      registry/
      scaffold/
      adapters/
      dispatch/
      storage/
      execution/
      jobs/
      pipeline/
        __init__.py
        core/
        artifacts/
        runtime/
        execution/
        analysis/
      frontdoor/
      cli/
```

`llm_kit.__init__` contains only version metadata and a deliberately small
package identity. It must not re-export subpackages. `llm_kit.pipeline` is an
empty grouping namespace and also must not re-export children. Those rules
remove the root-package cycle found in `llm_scripting_kit`.

The names below are public import addresses unless a module inside them is
explicitly marked private during implementation. Public symbols are exported
from the package that owns their reason to change, not from the root.

## Package boundaries

Each row names the owned behavior, its one primary reason to change under CCP,
and the measured or intended consumer that can reuse it without the rest under
CRP. The final column names behavior excluded to keep that boundary honest.

| Package | Responsibility and contents | CCP reason to change | CRP reuse without the rest |
|---|---|---|---|
| `llm_kit.schema` | Frozen JSON Schema subset, validation, errors, and deterministic almost-JSON repair. | The supported schema subset or repair rules change. | Bootstrap interrupt validation, jobs, and pipeline execution need it without transports. |
| `llm_kit.registry` | Endpoint/model declarations, effort vocabulary, conserve metadata, credentials, account metadata, config resolution, and declaration syntax. | Configuration schema, endpoint identity, credential precedence, or declaration syntax changes. | awesome-kit, git-kit, p4-kit, workflow-kit, jobs, runtime, and frontdoor resolve models without pipeline products. |
| `llm_kit.storage` | SQLite connection posture, product-parameterized migration runner, WAL/network-path handling, transactions, and atomic JSON. | Safe local persistence posture changes. | Jobs, pipeline execution, and spend ledger reuse it without importing one another. |
| `llm_kit.scaffold` | Public command dispatch, scope filtering, did-you-mean, YAML rendering, and stable exit codes. | Reusable command-composition semantics change. | Pipeline authors documented against `content_pipeline.cli.scaffold` use it without llm-kit CLI commands. |
| `llm_kit.completion` | Provider-neutral request/result/usage/halt/capability/requirement/output-contract/skill-context types and protocols. | The meaning of one completion call or capability changes. | Direct completion consumers type calls without registry parsing, transports, jobs, or pipelines. |
| `llm_kit.execution` | Bootstrap event/interrupt adapters, common request/resolution values, lapse delegation, and bounded-pool control. | Bootstrap contract shape or common bounded-execution semantics change. | Jobs and pipeline execution reuse it without sharing state machines or schemas. |
| `llm_kit.adapters` | OpenAI-compatible, Claude, Codex, OpenCode, harness, local-swapper, process, and raw usage-source integrations. | An external SDK, CLI, filesystem source, process protocol, or transport changes. | Dispatch and frontdoor acceptance reuse transports; completion-only consumers import none. |
| `llm_kit.dispatch` | Declaration describe/run, backend factory, endpoint profiles, reachability, seats, usage pacing/cache, observer, and review-lane service. | Selection, reachability, pacing, or invocation policy changes. | The four measured llm-scripting-kit code consumers invoke models without job or pipeline packages. |
| `llm_kit.jobs` | Flat jobs, schema-12 ledger, selection, runner, workers, acceptance, backpressure, workspaces, status, events, and interrupts. | Flat-job, workspace, acceptance, or job-ledger policy changes. | skills-kit's md-domain emitter needs jobs and no leased pipeline execution. |
| `llm_kit.pipeline.core` | Stages, work units, gates, convergence, deterministic seeding, validator/rejection contracts, and VCS/artifact/provider ports. | Pipeline unit, stage, validation, or extension-port meaning changes. | Runtime, artifacts, execution, and analysis reuse it. yaml-data-editor-kit also imports it, but not alone: it imports runtime and execution too. |
| `llm_kit.pipeline.artifacts` | Attributed/candidate stores, unsupported registry, freshness, delivery, round trip, provider assembly, and Git/null adapters. | Artifact identity, human precedence, freshness, correction, delivery, or concrete VCS behavior changes. | Runtime, pipeline execution, and analysis are measured consumers. No external artifacts-only consumer was found. |
| `llm_kit.pipeline.runtime` | Dispatch binding, retry/backpressure/cache/cost/budget/validate loop, spend ledger, YAML extraction, and public budget guard. | Pipeline call economics, retry, cache, validation, or spend policy changes. | Inline pipeline callers and yaml-data-editor-kit use it without leased reporting or flat jobs. |
| `llm_kit.pipeline.execution` | Schema-10 unit store, claims, fencing, lease, controller, waves, scheduler, worker protocol/packs, status, deadlines, failure cache, and drivers. | Worker, lease, claim, wave, or durable-unit policy changes. | yaml-data-editor-kit consumes it without flat jobs. |
| `llm_kit.pipeline.analysis` | Audit classification/reporting, reasoning chains, provenance, call audits, snapshots, replay, and impact-per-cost views. | Traceability, replay, audit, or reporting requirements change. | llm-kit's reporting CLI consumes it. No external analysis-only library consumer was found. |
| `llm_kit.frontdoor` | FastAPI routes, request translation, group routing, server lifecycle, and swapper acceptance. | HTTP compatibility or server lifecycle changes. | Server operators import it; other paths avoid FastAPI, Uvicorn, and httpx. |
| `llm_kit.cli` | llm-kit argv parsing, subcommand routing, formatting, bootstrap guard, and lazy application composition. | User-facing syntax or command composition changes. | Executable entry points only; reusable scaffold, budget, and unsupported APIs live outside it. |

## Execution-overlap ruling

The recommendation in `dev/tasks/llm-plugins-merge/execution-overlap.md` is adopted with one modification.

Flat jobs and leased pipeline execution remain separate because their state
machines, users, schemas, and acceptance rules differ. A job runner owns the
call and accepts by command result. A pipeline worker claims a unit under a
lease and fencing token. Layering pipeline execution on jobs would erase the
pipeline's concurrency contract; unifying them would make each consumer reuse
the other's unrelated policy, violating CRP.

The proposed shared kernel is split into `llm_kit.execution` and
`llm_kit.storage`. Bootstrap event/interrupt contracts change for a different
reason than SQLite WAL and transaction posture. Keeping those reasons in two
packages satisfies CCP while retaining all measured reuse.

Only common interrupt request/resolution values move into `execution`.
Job-specific and unit-specific interrupt records remain in their product
packages. The state transitions in `resolve_interrupt` and `expire_interrupts`
also remain product-owned because continuation and release behavior differ.

## Exact dependency graph

An entry `A -> {B, C}` is the complete inter-package import set for A.
Same-package imports are unrestricted. An omitted edge is forbidden. This
ASCII layered graph is also the import guard's input.

```text
Layer 6  cli                -> {schema, completion, registry, adapters, dispatch, jobs,
                                pipeline.runtime, pipeline.execution, pipeline.analysis,
                                frontdoor, scaffold}
Layer 5  pipeline.execution -> {execution, storage, pipeline.core,
                                pipeline.artifacts, pipeline.runtime}
Layer 4  jobs               -> {completion, registry, dispatch, execution, storage}
         pipeline.runtime   -> {completion, registry, dispatch, storage,
                                pipeline.core, pipeline.artifacts}
Layer 3  dispatch           -> {completion, registry, adapters}
         frontdoor          -> {completion, registry, adapters}
Layer 2  adapters           -> {completion, registry}
         pipeline.analysis  -> {pipeline.core, pipeline.artifacts}
Layer 1  completion         -> {schema}
         execution          -> {schema}
         pipeline.artifacts -> {pipeline.core}
Layer 0  schema             -> {}
         registry           -> {}
         storage            -> {}
         pipeline.core      -> {}
         scaffold           -> {}
```

`frontdoor` intentionally has no `dispatch` edge. The old server does not
import dispatch; acceptance imports swapper acceptance, so the real edge is
`frontdoor -> adapters`. The graph includes the previously omitted
`jobs -> registry`, `pipeline.runtime -> registry`, and direct CLI edges.

### Required symbol moves

These moves are part of the package contract, not implementation suggestions.

| Old location | Destination | Edge removed |
|---|---|---|
| `usage_budget.ConserveSpec`, `ConserveConfigError`, `parse_conserve_usage` | `registry.conserve` | `registry -> dispatch` from `model_endpoints` and `models` |
| `declaration._model_declaration` and its bootstrap declaration probe | `registry.declaration_syntax` | lazy `registry -> dispatch` from `models` |
| `harness_adapters.harness_effort_order` and the static effort-order tables | `registry.effort` | lazy `registry -> adapters` from `effort` |
| Raw Claude/Codex usage readers and their source result values | `adapters.usage_sources` | `adapters -> dispatch` from `codex_backend` |
| Pacing decisions, session pinning, and verdict-cache writes from `usage_budget` | `dispatch.usage_budget` | keeps policy above adapters and registry |
| `claude_runner.AgentTimeoutError` | `completion.halt` | `completion -> adapters`; runners import the lower exception |
| `freshness.seed` | `pipeline.core.seed` | `pipeline.core -> pipeline.artifacts` from `single_pass` |

`completion.adapter_capabilities` remains in `completion` because it is the
provider-neutral filled capability record. `completion.endpoint_profile` and
`completion.factory` move to `dispatch` because they combine registry facts
with adapter selection. Codex quota classification calls the sibling raw usage
reader in `adapters.usage_sources`; it never imports pacing policy.

### Planned coupling and abstractness

Metrics count only the 16 packages and the exact edges above. `Ca` is fan-in,
`Ce` is fan-out, and `I = Ce / (Ca + Ce)`. Planned A is named abstract
classes/protocols divided by the projected class count after duplicate value
types are consolidated. Implementation verifies the denominator; a changed
edge requires design review.

| Package | Ca | Ce | I | Planned A | Abstract classes/protocols counted |
|---|---:|---:|---:|---:|---|
| `schema` | 3 | 0 | 0.00 | 1/4 = 0.25 | `SchemaValidator` |
| `registry` | 6 | 0 | 0.00 | 3/8 = 0.38 | `ModelResolver`, `EndpointResolver`, `CredentialResolver` |
| `storage` | 3 | 0 | 0.00 | 2/6 = 0.33 | `MigrationVersionPolicy`, `ConnectionPolicy` |
| `pipeline.core` | 4 | 0 | 0.00 | 6/12 = 0.50 | `Stage`, `WorkUnitStrategy`, `Validator`, `VcsBackend`, `ContextProvider`, `ArtifactPort` |
| `scaffold` | 1 | 0 | 0.00 | 1/2 = 0.50 | `Handler` |
| `completion` | 6 | 1 | 0.14 | 4/10 = 0.40 | `CompletionBackend`, `CompletionObserver`, `SkillMaterializer`, `OutputContractJudge` |
| `execution` | 2 | 1 | 0.33 | 3/8 = 0.38 | `EventSink`, `InterruptContract`, `BoundedExecutor` |
| `adapters` | 3 | 2 | 0.40 | 0/18 = 0.00 | none; implementations satisfy completion protocols |
| `dispatch` | 3 | 3 | 0.50 | 3/12 = 0.25 | `DeclarationRunner`, `ReachabilityProbe`, `UsageSource` |
| `jobs` | 1 | 5 | 0.83 | 2/30 = 0.07 | `WorkspaceProvider`, `AcceptanceCheck` |
| `pipeline.artifacts` | 3 | 1 | 0.25 | 0/25 = 0.00 | none; extension ports live in `pipeline.core` |
| `pipeline.runtime` | 2 | 6 | 0.75 | 2/14 = 0.14 | `PipelineBackend`, `AttemptObserver` |
| `pipeline.execution` | 1 | 5 | 0.83 | 2/28 = 0.07 | `RunAdapter`, `WorkerDriver` |
| `pipeline.analysis` | 1 | 2 | 0.67 | 2/11 = 0.18 | `Recorder`, `CallAuditor` |
| `frontdoor` | 1 | 3 | 0.75 | 0/5 = 0.00 | none |
| `cli` | 0 | 11 | 1.00 | n/a | none planned |

Registry is deliberately stable, but it is not left concrete in the zone of
pain. The measured high-change pairs are `default_config.yaml` plus `models.py`
in 18 commits and `model_endpoints.py` plus `models.py` in 12. The three
resolver protocols isolate consumers from parsing and precedence changes;
concrete YAML, environment, and credential resolution remains behind them.

SDP holds because high-I application packages point toward lower-I contracts.
SAP holds at the named variation points. Stable concrete schema and artifact
behavior are exceptions by design: compatibility fixtures, append-only
migrations, and byte contracts protect them.

## Cycles found and how the design breaks them

The 2026-10-16 inventory found no eager module cycle, one eager subpackage
cycle, and five module cycles when lazy imports were included.

1. `llm_scripting_kit` root `<-> completion` disappears because both new namespace initializers are empty.
2. `effort -> harness_adapters -> model_endpoints -> effort` disappears when `harness_effort_order` and its static tables move into `registry.effort`; registry imports no adapter.
3. `swapper <-> _swapper_process` becomes a one-way adapter-internal edge: swapper service imports process primitives, and the primitive module imports no service.
4. The ten-module completion/config/declaration cycle is split: declaration syntax and conserve values move to registry; capability types stay in completion; transports move to adapters; endpoint profile, factory, and run policy move to dispatch.
5. `execution.workerpack -> controller -> protocol -> workerpack` is broken by a private `pipeline.execution.worker_types` leaf; controller, protocol, and workerpack import it, while composition moves to drivers.
6. `job_kit.store <-> workspace` becomes one-way: workspace calls store; store records workspace facts but performs no workspace operations.

The four newly identified upward edges are removed explicitly: raw usage
sources keep adapters below dispatch, timeout error ownership keeps completion
below adapters, deterministic seed ownership keeps pipeline core independent,
and registry-owned declaration/conserve values keep registry at layer 0.

## Optional dependency boundaries

The base shared-library path is standard-library only. Optional dependency
groups are:

| Extra | Packages that may use it | Third-party requirements |
|---|---|---|
| `config` | `registry`, `dispatch` | `pyyaml>=6.0` |
| `sdk` | the OpenAI SDK adapter in `adapters` | `openai>=1.0.0` |
| `local` | local swapper/process adapter | `psutil>=6.0` |
| `frontdoor` | `frontdoor` | `fastapi>=0.110`, `uvicorn>=0.29`, `httpx>=0.27` |
| `jobs` | job file parsing and CLI | `pyyaml>=6.0` |
| `pipeline` | pipeline YAML extraction and CLI | `pyyaml>=6.0` |
| `dev` | tests | the repository's selected pytest floor |

`ruamel.yaml` is not carried forward because the inventory found no import of
it. It can be added only with a concrete caller and test.

The llm-kit owner's bootstrap manifest enables every extra needed by its own
CLI and bundled skills. This makes every shipped command supported in the
owner venv, as required by the optional-dependency contract.

A different plugin that imports the shared library owns the third-party
dependencies of the path it uses. A completion-only consumer importing
`llm_kit.completion` pays for the llm-kit source link and Python's standard
library. It does not need PyYAML, OpenAI, psutil, FastAPI, Uvicorn, httpx, job
code, or pipeline code. A consumer of `dispatch` enables `config`; one that
selects the SDK adapter also enables `sdk`.

Optional third-party imports are lazy at the call site. Missing support must
REFUSE when the requested action cannot produce a true artifact. No adapter
silently substitutes another adapter. A capability that remains true without
an optional adapter may DEGRADE only when the rendered artifact names the
omission.

The edge from llm-kit to bootstrap is REQUIRED. llm-kit's plugin manifest
depends on bootstrap, its bootstrap manifest imports `bootstrap_lib`, and code
that needs a bootstrap contract probes the frontier call shape before opening
a ledger or launching a process.

## Namespace options and public-name migration

### Option A: one `llm_kit` top-level package -- recommended

Every consumer changes its import and `shared_lib_imports` entry once.
Bootstrap adds `llm_kit` to first-party recognition while retaining
`llm_scripting_kit` for the freeze. The package can coexist because its
shared-library directory and `.pth` name are distinct.

### Option B: retain the three old top-level packages -- rejected for coexistence

Consumers could keep imports, but llm-kit would publish
`llm_scripting_kit`, `content_pipeline`, and `job_kit` under names already
owned by frozen plugins. Owners in the same marketplace target the same
`_shared_libs/<name>` directory; standalone `.pth` files are also keyed only
by name. The last bootstrap pass would choose an implementation silently.

Keeping unregistered copies only inside llm-kit's venv avoids the broadcast
collision but does not help shared-library consumers, so they still change
imports. Transparent old-name shims become possible only after old-plugin
deletion and would prolong ambiguous ownership. They are not part of this
design.

### Old-to-new public-name map

The longest matching prefix wins. Every `public` entry in
`plugins/content-pipeline-kit/contract/public-surface.json` follows this map;
entries marked `removed` remain removed.

| Old public name or prefix | New public name or prefix |
|---|---|
| `llm_scripting_kit.completion.{json_schema,json_repair}` | `llm_kit.schema.{json_schema,json_repair}` |
| `llm_scripting_kit.completion.{backends,claude_runner,codex_backend,opencode_backend}` | `llm_kit.adapters.*` |
| `llm_scripting_kit.completion.{endpoint_profile,factory}` | `llm_kit.dispatch.*` |
| other `llm_scripting_kit.completion.*`; `request_protocol` | `llm_kit.completion.*` |
| `llm_scripting_kit.{account,api_key,constants,effort,env_file,model_endpoints,models}` | `llm_kit.registry.*` |
| `llm_scripting_kit.{declaration,observer,reachability,review_lane,seats,usage_budget}` | `llm_kit.dispatch.*` |
| `llm_scripting_kit.{client,harness_adapters,swapper,swapper_acceptance,_swapper_process}` | `llm_kit.adapters.*` |
| `llm_scripting_kit.frontdoor.*` | `llm_kit.frontdoor.*` |
| `llm_scripting_kit.cli.*` | `llm_kit.cli.*` |
| `job_kit.*` | `llm_kit.jobs.*` public facades; shared internals delegate to `execution` and `storage` |
| `content_pipeline.audit.*`; `content_pipeline.provenance.*` | `llm_kit.pipeline.analysis.*` |
| `content_pipeline.cli.scaffold` | `llm_kit.scaffold` |
| `content_pipeline.cli.budget` | `llm_kit.pipeline.runtime.budget` |
| `content_pipeline.cli.unsupported` | `llm_kit.pipeline.artifacts.unsupported` |
| `content_pipeline.cli.run` | `llm_kit.cli.pipeline` |
| `content_pipeline.{deliver,freshness,providers,roundtrip,store,vcs}.*` | `llm_kit.pipeline.artifacts.*` except the next two rows |
| `content_pipeline.freshness.seed` | `llm_kit.pipeline.core.seed` |
| `content_pipeline.vcs.seam` | `llm_kit.pipeline.core.vcs` |
| `content_pipeline.validate.*`; `content_pipeline.pipeline.*`; `content_pipeline.llm.convergence` | `llm_kit.pipeline.core.*` |
| other `content_pipeline.llm.*` | `llm_kit.pipeline.runtime.*` |
| `content_pipeline.execution.*` | `llm_kit.pipeline.execution.*` public facades; shared internals delegate to `execution` and `storage` |

awesome-kit, git-kit, p4-kit, workflow-kit, yaml-data-editor-kit, and skills-kit
move only after llm-kit stability is established. Old consumers keep old
imports during the freeze; provenance version lists add `llm_kit` without
rewriting frozen records.

## Skills, agents, workflows, CLIs, and shims

All five skill identities survive under llm-kit:

| Skill | Qualified identity | Route |
|---|---|---|
| `openrouter-account` | `llm-kit:openrouter-account` | `llm-kit account` through registry and dispatch |
| `content-pipeline-domain` | `llm-kit:content-pipeline-domain` | pipeline core, artifacts, and runtime |
| `background-pipeline` | `llm-kit:background-pipeline` | pipeline execution Claude driver |
| `execute-work-unit` | `llm-kit:execute-work-unit` | pipeline execution worker protocol |
| `workflow-pipeline` | `llm-kit:workflow-pipeline` | `llm-kit:run-ready-wave` workflow |

The pipeline-worker agent and run-ready-wave workflow also move under the
llm-kit namespace. Qualified names solve explicit invocation only. To prevent
description-based auto-trigger collisions, each old plugin's freeze release
rewrites every duplicated skill `description`, the pipeline-worker agent
description, and the run-ready-wave workflow description to begin exactly:
`Do NOT use; use llm-kit:<name>.` Their bodies become redirect-only refusals;
they do not run the frozen implementation.

The one console script is `llm-kit = llm_kit.cli:main`, with command groups
`account`, `completion`, `models`, `jobs`, `pipeline`, `frontdoor`, and
`local`. Old executable names remain owned by old plugins during the freeze.
The qwen server and switch capabilities move under `llm-kit local`.

The plugin ships `bin/llm-kit` and `bin/llm-kit.cmd`. With no redirected data
root, both try the version-independent llm-kit plugin venv first, then a
validated `BOOTSTRAP_PYTHON`, then `python3`/`python` on POSIX or `python.exe`
on Windows. A missing dependency refuses the selected subcommand; it does not
silently use a reduced registry.

Two refusals run before interpreter selection:

1. If `CLAUDE_BOOTSTRAP_DATA_ROOT` is set, the redirected llm-kit venv is the only candidate. If missing, exit 2 and refuse fallback to the production venv or PATH.
2. If `CLAUDE_PLUGIN_TEST` is set and the shim is under the tested marketplace cache, exit 2; when `CLAUDE_PLUGIN_TEST_MARKETPLACE` is unset, refuse every cache marketplace.

Implementation adds llm-kit to both
`tests/repo-scripts/test_launcher_shim_data_root_redirect.py` and
`tests/repo-scripts/test_forced_interpreter_order.py`, for POSIX and `.cmd`.
`CLI_COMMAND` and its redirected form name the llm-kit data directory, venv,
and executable; they never point at llm-scripting-kit's venv.

## TanStack insights

| Insight | Disposition and reason |
|---|---|
| Core plus adapters | Adopt. Stable `completion` contracts sit below concrete `adapters`, matching TanStack's direction without separate plugin versions. |
| Durability as its own layer | Adopt with a finer CCP split. `storage` owns persistence posture and `execution` owns execution contracts; completion and adapters import neither. |
| Uniform naming | Adopt. Every public package uses `llm_kit.*`, making ownership legible and avoiding top-level collisions. |
| Independent versions | Reject. npm can express hard version ranges, but the Claude Code plugin is the release unit and bootstrap cannot install subpackages independently. |
| Many separately installed packages | Reject while keeping internal components. Version-independent shared source links would recreate skew probes across plugins. |

## Persisted-state compatibility

### Plugin-name-keyed files and environment contracts

During coexistence and the freeze, llm-kit shares legacy state in place. It
does not copy state into a second llm-kit-named location. A copy would let two
verdict caches spend from one subscription pool and would strand keys or
overrides depending on which plugin handled a call.

| Contract | llm-kit decision during coexistence and freeze |
|---|---|
| User credential `.env` | Read and write `~/.claude/plugins/data/plugins-kit/llm-scripting-kit/.env`; do not create an llm-kit credential file. |
| Project credential `.env` | Preserve precedence of `.local-data/plugins-kit/llm-scripting-kit/.env`, then `.local-data/llm-scripting-kit/.env`. |
| User configuration | Ship the same default model data under registry; preserve `~/.claude/config/llm-scripting-kit.yaml`, `~/.claude/plugins/data/plugins-kit/llm-scripting-kit/config.yaml`, and `.local-data/plugins-kit/llm-scripting-kit/config.yaml` in the existing precedence. Do not seed parallel llm-kit user layers. |
| `usage-verdicts.json` | Both plugins read, lock, atomically update, and prune `~/.claude/plugins/data/plugins-kit/llm-scripting-kit/usage-verdicts.json`. |
| `LLM_SCRIPTING_KIT_USAGE_SESSION` | Keep this canonical explicit session key, with `CLAUDE_CODE_SESSION_ID` fallback. Do not add a competing variable during the freeze. |
| `CONTENT_PIPELINE_LLM_MODELS` | Keep this process routing variable. Do not add a competing variable during the freeze. |
| Other public endpoint/key/spend-ledger environment names | Preserve their spelling and precedence under the public-name migration. |
| `CLI_COMMAND` | Do not share: llm-kit names `${CLAUDE_BOOTSTRAP_DATA_ROOT:-$HOME/.claude/plugins/data}/plugins-kit/llm-kit/.venv/bin/llm-kit` (or `Scripts/llm-kit.exe`), never llm-scripting-kit's venv. |

Renaming legacy state paths is a separate post-deletion migration requiring a
copy-once marker, conflict policy, and rollback plan. It is not authorized by
this architecture.

### SQLite schemas, runner policy, and coexistence

llm-kit preserves job schema 12, pipeline schema 10, spend-ledger schema 1,
canonical JSON, interrupt documents, and event bytes. The legacy event sources
`job-kit` and `content-pipeline-kit` remain wire identities; they do not claim
which distribution wrote a row.

Product DDL and migration byte strings stay in `jobs`,
`pipeline.execution`, and `pipeline.runtime`. `storage` accepts explicit
product policies rather than imposing one bookkeeping algorithm:

| Product | Version bookkeeping | Connection/pragmas |
|---|---|---|
| Jobs | Migration 1 inserts version 1 inside its unchanged DDL; after each later migration the runner performs the existing update. | Preserve job connection isolation, WAL, foreign keys, busy timeout, and pragma order. |
| Pipeline execution | The runner performs the existing insert-or-update of `schema_version` after each unchanged migration. | Preserve execution-store connection isolation, WAL, foreign keys, busy timeout, and pragma order. |
| Spend ledger | No generic migration loop: one unchanged create schema, `isolation_level=None`, and the caller's configurable `synchronous`. | Preserve autocommit and the exact synchronous value; do not inherit job/execution defaults. |

Fresh-create tests create each database with frozen old code and with llm-kit,
then compare ordered `sqlite_master` and `schema_version` rows. Prefix fixtures
cover every supported migration. Pragma tests compare effective
`journal_mode`, `foreign_keys`, `busy_timeout`, `synchronous`, and isolation
posture. Byte fixtures compare exported events, interrupts, and canonical JSON.

The old and new implementations may open the same ledger during coexistence;
tests alternate old/new readers and writers against one fixture. No job,
pipeline, or spend-ledger schema change is allowed during the freeze: an
llm-kit-only migration would strand the frozen plugin. A schema change waits
until old-plugin deletion or requires a separately signed-off dual-readable
format and conversion plan.

## Python floor

llm-kit requires Python 3.12. This removes no host that can run the supported
plugin graph: `bootstrap_lib` already has a 3.12 floor and is linked into the
same consumer venvs. A `.pth` link does not enforce metadata, so migration must
raise `requires-python` from `>=3.10` to `>=3.12` in awesome-kit, workflow-kit,
yaml-data-editor-kit, and skills-kit and update their CI matrices. The real
cost is declaration/test churn and any unmeasured direct external library
consumer on 3.10 or 3.11, not loss of a supported in-repo host.

## Bootstrap and marketplace changes implied by the design

Implementation and migration would change this infrastructure:

- add `plugins/llm-kit` and a published llm-kit entry to `.claude-plugin/marketplace.json` through the repository's generator;
- declare `shared_libs: [{name: llm_kit, src: lib}]` and `shared_lib_imports: [bootstrap_lib]` in llm-kit's bootstrap manifest;
- add `llm_kit` to bootstrap's `_FIRST_PARTY_LIBS` while retaining `llm_scripting_kit` through the freeze;
- let llm-kit's interrupt adapter probe `llm_kit.schema` while old adapters continue to probe `llm_scripting_kit.completion.json_schema`;
- retain bootstrap's frozen `VALIDATOR_MODULE` and `VALIDATOR_SUBSET` compatibility constants for old consumers, and add a separately named llm-kit validator constant if bootstrap documentation needs one;
- migrate consumer `plugins` entries and `shared_lib_imports` only after llm-kit stability is established;
- keep all three old marketplace entries published throughout the freeze; and
- ship redirect-only freeze releases for duplicate skills, the worker agent, and the workflow.

The singular bootstrap `VALIDATOR_MODULE` must not be changed in place during
the freeze. Frozen job-kit and content-pipeline-kit code explicitly probe the
old validator, and bootstrap tests pin the old constant. llm-kit's adapter can
inject its own validator because the interrupt contract accepts a caller-
provided validator and does not import the named module itself.

## Import-direction guard

Implementation adds an AST-based test over `plugins/llm-kit/lib/llm_kit`.
The guard is generated from the exact adjacency set in the dependency graph
and a checked-in machine-readable copy beside the test. The appendix maps every
source module to a package. The guard asserts:

- every internal import targets the same package or an allowed lower package;
- eager imports, function-local imports, `TYPE_CHECKING` imports, and literal `importlib.import_module` calls all count;
- `llm_kit.__init__` and `llm_kit.pipeline.__init__` do not re-export component symbols;
- no llm-kit source imports `llm_scripting_kit`, `content_pipeline`, or `job_kit`;
- `jobs` and `pipeline.execution` do not import one another;
- the required symbol splits leave `registry`, `storage`, `pipeline.core`, and `scaffold` with no internal package imports;
- product DDL remains in its product package;
- only `cli` is allowed to import every application surface for composition.

The test reports source package, target package, import mode, and line number.
It has no broad allowlist for private modules. A changed edge requires a design
change, not a local exception.

Per the repository's non-vacuous-check rule, implementation must demonstrate
the guard by adding one forbidden import, observing the named test fail, then
removing the import and observing it pass.

## Decisions for sign-off

1. Use `llm_kit` as the only top-level package, with no transparent legacy shims during coexistence. Recommendation: yes. Cost: every consumer changes imports; benefit: deterministic side-by-side installation.
2. Treat the 16 packages, module map, required symbol moves, and exact edge set as the implementation contract. Recommendation: yes. Cost: code is reorganized rather than copied as three intact trees.
3. Keep jobs and leased pipeline execution separate above shared `execution` and `storage`. Recommendation: yes. Cost: two product models and stores remain; benefit: neither consumer receives the other's state machine.
4. Preserve ledger DDL, product-specific runner bookkeeping/pragmas, event bytes, and forbid schema changes throughout the freeze. Recommendation: yes. Cost: frozen fixtures constrain refactoring; benefit: old and new code can share ledgers.
5. Share legacy credential, config, verdict-cache, and routing environment contracts in place until old-plugin deletion. Recommendation: yes. Cost: llm-kit carries legacy path names; benefit: no lost keys, split policy, or double spending.
6. Replace both old CLIs for migrated users with one venv-first `llm-kit` executable and the listed subcommands. Recommendation: yes. Cost: scripts change names; benefit: no shim collision.
7. Keep the five skill short names under llm-kit and make old skill/agent/workflow registrations redirect-only in freeze releases. Recommendation: yes. Cost: old plugins need one freeze release; benefit: no duplicate auto-trigger.
8. Keep third-party dependencies in extras around a standard-library completion core. Recommendation: yes. Cost: each consumer declares the groups it reaches; benefit: completion-only users avoid unrelated dependencies.
9. Require Python 3.12 and raise awesome-kit, workflow-kit, yaml-data-editor-kit, and skills-kit declarations during migration. Recommendation: yes. Cost: metadata and CI changes, plus possible unmeasured external 3.10/3.11 users.
10. Retain bootstrap's old validator constant and add llm-kit recognition rather than replacing old names. Recommendation: yes. Cost: dual-name knowledge lasts through the freeze; benefit: old and new interrupt consumers coexist.
11. Release all subpackages under one llm-kit version. Recommendation: yes. Cost: one product change releases the whole plugin; benefit: no internal install-time skew.

Sign-off means accepting all recommendations or naming the numbered decisions
that must change. No llm-kit implementation should begin before that response.

## Appendix A: complete legacy module-to-package map

Prefixes: `L` is `llm_scripting_kit`, `C` is `content_pipeline`, and `J` is
`job_kit`. Names omit `.py`; within a cell, an unprefixed name inherits the
most recent `L`, `C`, or `J` prefix. Every one of the 133 inventoried modules
appears below. A `*` marks a primary public facade whose shared internals are
extracted by the required-symbol table or the execution/storage ruling.

| Destination package | Legacy modules |
|---|---|
| Empty namespaces | `L:__init__`; `C:__init__` |
| `schema` | `L:completion/json_repair`, `completion/json_schema` |
| `registry` | `L:account`, `api_key`, `constants`, `effort*`, `env_file`, `model_endpoints*`, `models*`; slices of `declaration*`, `harness_adapters*`, `usage_budget*` |
| `completion` | `L:completion/__init__`, `completion/adapter_capabilities`, `completion/capabilities`, `completion/contract`, `completion/contract_types`, `completion/halt*`, `completion/prompt_fold`, `completion/requirements`, `completion/results`, `completion/skill_context`, `completion/skill_context_types`, `completion/types`, `request_protocol`; `AgentTimeoutError` slice of `completion/claude_runner*` |
| `adapters` | `L:_swapper_process`, `client`, `completion/backends`, `completion/claude_runner*`, `completion/codex_backend*`, `completion/opencode_backend`, `harness_adapters*`, `swapper`, `swapper_acceptance`; raw-reader slice of `usage_budget*` |
| `dispatch` | `L:completion/endpoint_profile`, `completion/factory`, `declaration*`, `observer`, `reachability`, `review_lane`, `seats`, `usage_budget*` |
| `frontdoor` | `L:frontdoor/__init__`, `frontdoor/__main__`, `frontdoor/acceptance`, `frontdoor/server` |
| `scaffold` | `C:cli/scaffold` |
| `storage` | `C:execution/_atomic_json`; SQLite slices of `C:execution/store*`, `C:llm/spend_ledger*`, and `J:store*` |
| `execution` | Shared slices of `C:execution/events*`, `execution/interrupts*`, `execution/model*`, `execution/scheduler*`, and `J:events*`, `interrupts*`, `model*`, `run*` |
| `jobs` | `J:__init__`, `events*`, `interrupts*`, `model*`, `run*`, `select`, `store*`, `workspace` |
| `pipeline.core` | `C:freshness/seed`, `llm/convergence`, `pipeline/__init__`, `pipeline/cell_policy`, `pipeline/convergence_loop`, `pipeline/gate`, `pipeline/single_pass`, `pipeline/stage`, `pipeline/workunit`, `validate/__init__`, `validate/contract`, `validate/floor_guard`, `validate/riders`, `vcs/seam` |
| `pipeline.artifacts` | `C:cli/unsupported`, `deliver/__init__`, `deliver/inplace`, `deliver/projection`, `freshness/__init__`, `freshness/classify`, `freshness/ensure`, `freshness/hashing`, `freshness/tier`, `providers/__init__`, `providers/assembly`, `providers/registry`, `roundtrip/__init__`, `roundtrip/questions`, `roundtrip/returns`, `store/__init__`, `store/attributed`, `store/candidate`, `store/intermediary`, `store/projection`, `vcs/__init__`, `vcs/git_vcs`, `vcs/null_vcs` |
| `pipeline.runtime` | `C:cli/budget`, `llm/__init__`, `llm/backends`, `llm/gate`, `llm/platform`, `llm/spend_ledger*`, `llm/yaml_extract` |
| `pipeline.execution` | `C:execution/__init__`, `execution/adapter`, `execution/controller`, `execution/deadlines`, `execution/drivers/__init__`, `execution/drivers/claude_bg`, `execution/drivers/inline`, `execution/events*`, `execution/failure_cache`, `execution/interrupts*`, `execution/model*`, `execution/parallel_graph`, `execution/protocol`, `execution/scheduler*`, `execution/status`, `execution/store*`, `execution/wave`, `execution/workerpack` |
| `pipeline.analysis` | `C:audit/__init__`, `audit/auditor`, `audit/reasoning_chain`, `audit/report`, `provenance/__init__`, `provenance/call_audit`, `provenance/record`, `provenance/replay`, `provenance/snapshot` |
| `cli` | `L:bootstrap_guard`, `cli`, `scripts/llm_scripting_kit_cli`; `C:cli/__init__`, `cli/run`, `scripts/check_consumer_contract`; `J:cli` |

The primary facade rule means, for example, old `job_kit.events` callers move
to `llm_kit.jobs.events`; that facade delegates envelope mechanics to
`llm_kit.execution.events`. It does not permit the implementation to live in
both packages.

## Appendix B: load-bearing evidence

The underlying private task records are
`dev/tasks/llm-plugins-merge/inventory-coupling.md` and
`dev/tasks/llm-plugins-merge/execution-overlap.md`. This design depends on the
following measurements from 2026-10-16:

- Corpus: 133 modules, 20 first-level legacy units, and 55,629 lines across the three import packages and two script entry points.
- Cross-package edges: content-pipeline reaches llm-scripting-kit lazily from execution interrupts and LLM backends/platform; job-kit reaches it eagerly from package init, run, and select and lazily from interrupts. No job-kit/content-pipeline edge exists.
- Legacy cycles: one eager root/completion subpackage cycle and five lazy module cycles, all named in this document.
- Legacy abstractness: maximum A was 0.20; content-pipeline execution had 0/92 abstract classes and job-kit 0/56.
- External code/manifest consumers: awesome-kit, git-kit, p4-kit, workflow-kit, and yaml-data-editor-kit consume llm-scripting-kit; yaml-data-editor-kit consumes content-pipeline; skills-kit consumes the job-kit CLI. No external consumer was found that needs both execution products.
- yaml-data-editor-kit imports `content_pipeline.execution.{adapter,controller,drivers,model,protocol,store,workerpack}`, `content_pipeline.llm`, and `pipeline.workunit`; it is not a pipeline-core-only consumer.
- Change coupling: plugin commit counts were llm-scripting-kit 134, content-pipeline-kit 142, job-kit 54; cross-plugin co-change counts were 26, 18, and 8. Registry pairs were 18 commits for default config/models and 12 for model-endpoints/models.
- Execution overlap: shared logic is contract probes/adapters, interrupt values/lapse, SQLite posture, and bounded-pool control. Product schemas, transitions, leases, workspaces, acceptance, and drivers differ.
- Persisted baselines: job schema 12, pipeline migration list length 10, spend-ledger schema 1; job and pipeline use different version bookkeeping, and spend ledger uses autocommit plus configurable synchronous mode.
- Infrastructure coupling: bootstrap hard-codes `llm_scripting_kit` in first-party recognition and the interrupt validator; shared-library publication and `.pth` links are keyed by package name.

These measurements justify the boundaries and planned Ca/Ce table above; the
appendices are sufficient to review the design without access to the task
repository.
