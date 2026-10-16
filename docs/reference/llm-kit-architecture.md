# llm-kit Python package architecture

## Decision summary

- Create one published plugin, llm-kit, with one release version and one shared library, llm_kit.
- Consolidate under the final namespace privately, prove differential parity, then restructure one boundary at a time before consumer migration.
- Use 16 import components with the exact acyclic edge set below; namespace initializers re-export nothing.
- Keep completion contracts and capability types below concrete adapters, capability tables, factories, and account probes.
- Route pipeline backend construction through dispatch while preserving every constructor option and injection seam.
- Keep flat jobs and leased pipeline execution separate above shared execution and storage mechanics.
- Preserve job schema 12, pipeline schema 10, spend-ledger schema 1, DDL, pragmas, and event bytes during coexistence.
- Serialize active-run ownership across old and new implementations; keep the verdict file's advisory last-writer-wins semantics.
- Publish only llm_kit; legacy import names remain owned by old plugins through a two-minor deprecation window.
- Migrate qualified skill, agent, workflow, launch-flag, and resumable references before retiring any registration.
- Defer a generic migration runner until differential tests demonstrate a common algorithm worth extracting.
- Require Python 3.12 and raise the four lagging consumer declarations during migration.
- User sign-off on the numbered decisions is required before implementation.

## Ruling, scope, and repository rules

The controlling ruling from 2026-10-16 is:

> how we're going to do this is we're going to create a new plugin called llm-kit which will be the merged plugin. Once this plugin is stable we will migrate customers, freeze the other plugins for a while, and eventually delete them.

The design assumes that llm-kit, llm-scripting-kit, content-pipeline-kit, and job-kit coexist. llm-kit starts from copies; source is not moved out of the old plugins. Publication schedule, freeze duration, and deletion timing remain migration decisions.

The merge is a narrow, user-approved exception to plugins/CLAUDE.md, section "Published-plugin boundaries", which otherwise forbids moving content between plugins or creating a unifying plugin. It must still honor that section's rule against shipping maintainer-only material and the two-minor compatibility window in docs/reference/deprecation-policy.md.

Implementation would propose this amendment to plugins/CLAUDE.md; this design does not edit that file:

> **Approved consolidation exception: llm-kit.** The user-approved llm-kit merge may copy and restructure behavior from llm-scripting-kit, content-pipeline-kit, and job-kit into llm-kit. The old plugins retain their source during migration and freeze. This exception does not generalize to other plugin-boundary cohesion work. Every renamed or removed public name follows docs/reference/deprecation-policy.md.

## Terms and package principles

The plugin is the REP release unit: one manifest, version, marketplace entry, and release cadence. An import package is the component used for CCP, CRP, ADP, SDP, and SAP. The root llm_kit and grouping package llm_kit.pipeline contain no behavior and are not components.

- REP: every component ships in one llm-kit release.
- CCP: code that changes for the same actor and reason belongs together.
- CRP: consumers do not import or initialize unrelated behavior.
- ADP: every allowed import points down the graph.
- SDP: volatile applications depend on stable contracts and utilities.
- SAP: stable packages expose abstractions at actual variation points.

One release prevents undeclared internal skew, but gives up TanStack's ability to version each npm package independently. SAP does not require an interface for frozen formats; schemas, DDL, and event bytes remain concrete and are protected by compatibility fixtures.

## Proposed source tree

~~~text
plugins/llm-kit/
  lib/llm_kit/
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
~~~

Public symbols are exported from their owning component, never the root.

## Package boundaries

| Package | Responsibility | CCP reason to change | CRP reuse without the rest |
|---|---|---|---|
| llm_kit.schema | JSON Schema subset, validation, errors, deterministic repair. | The supported subset or repair rules change. | Bootstrap interrupt validation and both execution products need no transports. |
| llm_kit.registry | Endpoint/model declarations, effort vocabulary, conserve metadata, credential paths and precedence, config resolution. No HTTP. | Configuration, endpoint identity, credential precedence, or declaration syntax changes. | awesome-kit, git-kit, p4-kit, workflow-kit, jobs, runtime, and frontdoor resolve models without pipeline products. |
| llm_kit.storage | SQLite connection/transaction posture, WAL/network handling, atomic JSON, schema and run lock primitives. Product DDL and migration loops stay out. | Safe local persistence and cross-process ownership mechanics change. | Jobs, pipeline execution, and spend ledger reuse mechanics without sharing schemas. |
| llm_kit.scaffold | Command dispatch, scope filtering, suggestions, YAML rendering, stable exit codes. | Reusable command-composition semantics change. | Pipeline authors use it without llm-kit commands. |
| llm_kit.completion | Request/result/usage/halt/capability/requirement/output-contract types plus LLMBackend, BackendFactory, and CapabilityProvider protocols. No filled adapter tables or factories. | The meaning of a completion call or provider-neutral contract changes. | Completion-only consumers type calls without config, transports, jobs, or pipelines. |
| llm_kit.execution | Bootstrap event/interrupt adapters, common request/resolution values, lapse delegation, bounded-pool control. | Bootstrap contract shape or common bounded-execution semantics change. | Jobs and pipeline execution reuse it without sharing state machines. |
| llm_kit.adapters | OpenAI-compatible, Claude, Codex, OpenCode, harness, swapper, process, usage-source and account-probe integrations; adapter capability tables. | An SDK, CLI, wire request, filesystem source, process protocol, or account endpoint changes. | Dispatch and frontdoor reuse integrations; completion-only consumers import none. |
| llm_kit.dispatch | Declaration/run policy, configured backend factory, endpoint profiles, reachability, seats, pacing cache, observer, review-lane service. | Selection, construction, reachability, pacing, or invocation policy changes. | Measured direct LLM consumers need no job or pipeline product. |
| llm_kit.jobs | Flat jobs, schema-12 ledger and migration loop, selection, runner, workers, acceptance, workspaces, events, interrupts. | Flat-job, workspace, acceptance, or job-ledger policy changes. | skills-kit's emitter needs jobs without leased pipeline execution. |
| llm_kit.pipeline.core | Stages, work units, gates, convergence, seeding, validator/rejection contracts, extension ports. | Pipeline unit, stage, validation, or port meaning changes. | Runtime, artifacts, execution, and analysis reuse it. |
| llm_kit.pipeline.artifacts | Stores, unsupported registry, freshness, delivery, round trip, provider assembly, Git/null adapters. | Artifact identity, precedence, freshness, correction, or delivery changes. | Runtime, pipeline execution, and analysis reuse it. |
| llm_kit.pipeline.runtime | Factory binding, retry/backpressure/cache/cost/budget/validate loop, spend ledger, YAML extraction. | Pipeline call economics, retry, cache, validation, or spend policy changes. | Inline callers and yaml-data-editor-kit need no leased reporting or flat jobs. |
| llm_kit.pipeline.execution | Schema-10 migration loop, unit store, claims, fencing, leases, controller, waves, workers, status, drivers. | Worker, lease, claim, wave, or durable-unit policy changes. | yaml-data-editor-kit consumes it without flat jobs. |
| llm_kit.pipeline.analysis | Audit reports, reasoning chains, provenance, call audits, snapshots, replay, impact-per-cost views. | Traceability, replay, audit, or reporting requirements change. | The reporting CLI needs no worker controller. |
| llm_kit.frontdoor | FastAPI routes, translation, group routing, server lifecycle, swapper acceptance. | HTTP compatibility or server lifecycle changes. | Other paths avoid FastAPI, Uvicorn, and httpx. |
| llm_kit.cli | argv parsing, subcommand routing, formatting, bootstrap guard, lazy composition. | User-facing syntax or application composition changes. | Executable entry points only. |

## Execution-overlap ruling

The recommendation in dev/tasks/llm-plugins-merge/execution-overlap.md is adopted with a split shared kernel. Flat jobs and leased pipeline execution keep different state machines, schemas, users, and acceptance rules. A job runner owns a call; a pipeline worker claims a unit under a lease and fencing token. Combining them would violate CRP and weaken the pipeline concurrency contract.

Shared bootstrap execution contracts live in execution; SQLite and ownership mechanics live in storage. Product interrupt records, transitions, schemas, and migration loops remain product-owned. A generic migration runner is not in the first contract. Differential parity tests must first show that the legacy runners share an algorithm rather than only similar syntax.

## Exact dependency graph

A -> {B} is the complete inter-component import set. Same-package imports are unrestricted; an omitted edge is forbidden.

~~~text
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
~~~

### Required moves and composition seams

| Legacy source | Destination or rule | Dependency result |
|---|---|---|
| usage_budget conserve values and parsing | registry.conserve | registry stays below dispatch. |
| declaration._model_declaration and declaration probe | registry.declaration_syntax | Removes lazy registry -> dispatch. |
| Static effort-order tables | registry.effort | Removes lazy registry -> adapters. |
| Raw Claude/Codex usage readers | adapters.usage_sources | Adapters do not import pacing policy. |
| Pacing, session pinning, verdict writes | dispatch.usage_budget | Policy stays above sources. |
| completion.adapter_capabilities filled records | adapters.capabilities | Capability types stay in completion; tables change with adapter emission. |
| account HTTP, decoding, status translation, endpoint probes | adapters.account | Registry keeps credential/config contracts and performs no transport I/O. |
| claude_runner.AgentTimeoutError | completion.halt | Removes completion -> adapters. |
| freshness.seed | pipeline.core.seed | Removes pipeline.core -> artifacts. |
| content_pipeline.llm.backends concrete construction | dispatch.pipeline_backends | Runtime wrappers call dispatch, never adapters. |

pipeline.runtime.backends keeps the public pipeline wrappers and every constructor option: endpoint, project root, client, timeout, retry, diagnostics, executable, argv prefix, runner, and model endpoint. Each wrapper passes an immutable construction spec to an injected completion.BackendFactory; the default is dispatch.ConfiguredBackendFactory. Dispatch maps names to concrete adapter classes. CLI is the composition root and injects the configured factory into jobs, pipeline runtime, and frontdoor. Direct library users either inject the protocol or call the public dispatch builder.

The old llm_scripting_kit.completion facade is split, not copied. Neutral result, option, halt, requirement, output-contract, skill-context, and capability TYPE exports move to llm_kit.completion. The other exports move as follows:

- ADAPTER_CAPABILITIES, adapter_capabilities, OpenRouterBackend, ClaudeCliBackend, CodexCliBackend, OpencodeCliBackend, CodexRunError, OpencodeRunError, run_cli_streaming, run_claude_streaming, looks_like_hard_stop, compose_prompt, and their transport constants -> llm_kit.adapters.
- BackendSelection, create_backend, create_transport_backend, EndpointProfile, and endpoint-profile functions -> llm_kit.dispatch.
- EffortDelivery, EffortPlan, and plan_effort -> llm_kit.registry.effort.

AgentTimeoutError moves to llm_kit.completion.halt as a provider-neutral halt type; the concrete runner imports it from that lower package.

No llm_kit.completion initializer re-export may restore an adapters or dispatch edge. A selected adapter supplies its filled capability record through CapabilityProvider; consumers receive it through the injected factory. The account CLI resolves credentials through registry and injects them into adapters.account. These concrete composition paths, not protocol counts alone, are the SAP mechanism.

### Planned coupling and abstractness

Metrics count the 16 components and exact edges above. I = Ce / (Ca + Ce). Planned A is named protocols divided by projected class count; implementation verifies each denominator.

| Package | Ca | Ce | I | Planned A and variation points |
|---|---:|---:|---:|---|
| schema | 3 | 0 | 0.00 | 1/4: SchemaValidator |
| registry | 6 | 0 | 0.00 | 3/8: model, endpoint, credential resolvers |
| storage | 3 | 0 | 0.00 | 2/6: connection policy, owner lock |
| pipeline.core | 4 | 0 | 0.00 | 6/12: stage, work-unit, validator, VCS, context, artifact ports |
| scaffold | 1 | 0 | 0.00 | 1/2: handler |
| completion | 6 | 1 | 0.14 | 6/12: backend, factory, capability provider, observer, materializer, output judge |
| execution | 2 | 1 | 0.33 | 3/8: event sink, interrupt contract, bounded executor |
| adapters | 3 | 2 | 0.40 | 0/20: concrete implementations |
| dispatch | 3 | 3 | 0.50 | 3/12: declaration runner, reachability probe, usage source |
| jobs | 1 | 5 | 0.83 | 2/30: workspace provider, acceptance check |
| pipeline.artifacts | 3 | 1 | 0.25 | 0/25: ports live in core |
| pipeline.runtime | 2 | 6 | 0.75 | 2/14: pipeline backend, attempt observer |
| pipeline.execution | 1 | 5 | 0.83 | 2/28: run adapter, worker driver |
| pipeline.analysis | 1 | 2 | 0.67 | 2/11: recorder, call auditor |
| frontdoor | 1 | 3 | 0.75 | 0/5: application boundary |
| cli | 0 | 11 | 1.00 | n/a: composition root |

SDP holds because high-I applications point toward lower-I contracts. SAP holds at the listed injected seams. Stable concrete formats are protected by byte and schema fixtures rather than decorative interfaces.

## Cycles removed

The 2026-10-16 inventory found one eager subpackage cycle and five module cycles when lazy imports were included:

1. Root <-> completion: both new namespace initializers are empty.
2. effort -> harness_adapters -> model_endpoints -> effort: effort tables move to registry.
3. swapper <-> _swapper_process: the process primitive imports no service.
4. The ten-module completion/config/declaration cycle: neutral types, concrete tables/transports, registry syntax, and dispatch policy separate as above.
5. workerpack -> controller -> protocol -> workerpack: a private worker-types leaf holds shared values; composition moves to drivers.
6. job_kit.store <-> workspace: workspace calls store; store performs no workspace operations.

## Optional dependencies

The base shared-library path is standard-library only.

| Extra | Reachable package | Requirements |
|---|---|---|
| config | registry and dispatch config paths | pyyaml>=6.0 |
| sdk | OpenAI-compatible adapter | openai>=1.0.0 |
| local | local swapper/process adapter | psutil>=6.0 |
| frontdoor | frontdoor | fastapi>=0.110, uvicorn>=0.29, httpx>=0.27 |
| jobs | job YAML and CLI | pyyaml>=6.0 |
| pipeline | pipeline YAML and CLI | pyyaml>=6.0 |

The owner venv enables every extra its bundled CLI and skills reach. Importing llm_kit.completion costs only the source link and standard library. A dispatch consumer enables config; selecting the SDK adapter also enables sdk. Optional imports occur at the call site and a missing requested capability refuses.

## Namespace and public-name migration

Option A, recommended: publish only llm_kit. Consumers change imports and shared_lib_imports once. Bootstrap recognizes both llm_kit and llm_scripting_kit during coexistence; distinct shared-library names avoid cache and .pth collisions.

Option B: llm-kit also publishes llm_scripting_kit, content_pipeline, and job_kit. This is rejected during coexistence because old plugins own those names and shared-library publication is keyed by package name.

Legacy names remain owned by their old plugins. After llm-kit parity, each old plugin ships deprecation shims that emit DeprecationWarning with stacklevel=2 and delegate to the final llm_kit address for at least two minor versions. llm-kit never publishes the old top-level packages. Removal records remain in each public-surface listing.

| Old surface | New surface |
|---|---|
| Neutral llm_scripting_kit.completion exports | llm_kit.completion |
| Completion transports, runners, capability tables | llm_kit.adapters |
| Completion factory/profile exports | llm_kit.dispatch |
| llm_scripting_kit.account network APIs | llm_kit.adapters.account |
| Model/config/credential resolution | llm_kit.registry |
| Declaration, seats, reachability, pacing | llm_kit.dispatch |
| job_kit.* | llm_kit.jobs.* facades |
| Content pipeline audit/provenance | llm_kit.pipeline.analysis.* |
| content_pipeline.cli.scaffold | llm_kit.scaffold |
| Content pipeline artifacts and VCS implementations | llm_kit.pipeline.artifacts.* |
| Content pipeline stages, validation, convergence, seed, VCS port | llm_kit.pipeline.core.* |
| Content pipeline LLM wrappers and spend policy | llm_kit.pipeline.runtime.* |
| Content pipeline backend construction | llm_kit.dispatch.pipeline_backends |
| content_pipeline.execution.* | llm_kit.pipeline.execution.* facades |

## Skills, agents, workflows, CLIs, and shims

The final qualified names are llm-kit:openrouter-account, llm-kit:content-pipeline-domain, llm-kit:background-pipeline, llm-kit:execute-work-unit, llm-kit:workflow-pipeline, llm-kit:pipeline-worker, and llm-kit:run-ready-wave.

Legacy registrations are not converted to refusals. pipeline-worker can be selected explicitly through launch flags, and resumable workflows can persist qualified names. Before activation, implementation must migrate maintained qualified references, launch flags, and resumable records, or provide a tested old-name translator. Both old and new registrations must execute equivalent behavior if automatic selection chooses either; description wording is not a safety mechanism.

Activation requires all of these machine-checkable conditions:

1. Source and manifest scans find no unsupported old qualified reference.
2. Old-created resumable fixtures resume through both the legacy alias and final llm-kit name.
3. Contract listings record since, remove_after, and replacement names.
4. Legacy bodies remain functional and emit a user-visible deprecation warning.
5. Rollback tests disable llm-kit registration and resume through the old names.

Retirement requires the two-minor window, zero maintained old references, and zero nonterminal persisted records that require an untranslated old identity. Rollback restores routing to the still-functional legacy registrations; it does not reverse persisted data.

The console script is llm-kit = llm_kit.cli:main, with account, completion, models, jobs, pipeline, frontdoor, and local groups. Old executable names remain compatibility shims in old plugins. POSIX and .cmd launchers are venv-first and retain redirected-data-root and cached-copy refusals; launcher tests cover both platforms.

## Sequencing decision

Option A, recommended:

1. Add coordination protocols to the legacy implementations and test them.
2. Consolidate behavior privately under the final llm_kit namespace.
3. Establish old-vs-llm-kit differential parity for API, CLI, events, schemas, state, and failure behavior.
4. Restructure one boundary at a time and enforce the final import graph.
5. Activate the final public namespace and migrate consumers once.
6. Migrate skills, agents, workflows, launch flags, and resumable references; keep functional aliases through the deprecation window.
7. Freeze and retire old plugins under separate acceptance gates.

An llm-kit plugin version may ship before step 5, but it exposes no temporary public namespace and triggers no consumer migration. A generic migration runner is considered only after step 3 demonstrates reusable behavior.

Option B exposes the fully restructured public API first and accepts packaging, persistence coordination, execution refactoring, consumer migration, and legacy retirement together. It shortens the release sequence but makes failures hard to localize and can force a second consumer migration. Option B is not recommended.

## TanStack insights

| Insight | Decision and reason |
|---|---|
| Core plus adapters | Adopt: completion contracts sit below concrete adapters. |
| Durability as a layer | Adopt with two CCP packages: execution contracts and storage mechanics. |
| Uniform naming | Adopt: public components use llm_kit.*. |
| Independent versions | Reject: the plugin is one REP unit and cannot express internal install ranges. |
| Many installed packages | Reject: shared links would recreate cross-plugin skew probes. |

## Persisted-state compatibility

### Credentials, config, and verdict cache

llm-kit uses the legacy credential and config locations and preserves all public environment-variable spelling and precedence until old-plugin deletion. It does not seed competing llm-kit user layers. CLI_COMMAND is the exception: it names the llm-kit venv and executable.

LEGACY_LLM_DATA/usage-verdicts.json remains exactly the legacy single-session pacing cache. The legacy implementation reads one session's dictionary, rewrites the whole file, and uses atomic replacement without an interprocess lock. llm-kit retains those semantics during coexistence:

- Simultaneous writers are last-writer-wins, including writers from different sessions and writers updating different endpoints.
- Atomic replacement prevents torn JSON but does not prevent lost updates.
- A lost verdict causes recomputation and may alter pacing.
- The file is advisory pacing state, not authorization, accounting, reservation, or double-spend prevention.

Barrier-synchronized old/new process tests cover same-session and different-session writers. They assert parseable legacy-shaped output and recomputation by the losing writer; they do not assert merged verdict retention. A stronger merge/lock protocol requires a separate compatibility release in the legacy plugin before llm-kit may use it.

### SQLite compatibility, ownership, and handover

llm-kit preserves job schema 12, pipeline schema 10, spend-ledger schema 1, canonical JSON, interrupt documents, DDL, pragma order, and event bytes. Product migration loops stay in jobs and pipeline.execution; spend ledger keeps its one create schema, autocommit, and configurable synchronous value.

Coexistence permits concurrent readers but exactly one execution owner per logical run. A compatibility release of job-kit and content-pipeline-kit ships the same sidecar lock protocol before llm-kit can resume a legacy nonterminal run:

- The tuple (ledger-id, product, run-id) selects an advisory OS lock held for the full controller or resume lifetime.
- A separate ledger-schema lock covers open/migrate, then releases.
- Every mutating entry point verifies ownership before opening its transaction.
- Clean handover stops the owner, releases the lock, then starts the other.
- Process death releases the OS lock; takeover never relies on a stale timestamp.
- Filesystems without verified cross-process lock semantics refuse active-run sharing rather than simulate ownership.

An unpatched legacy version may read terminal records but cannot coexist as an active writer. llm-kit refuses to resume its nonterminal run. Rollback means the patched freeze version: stop llm-kit, release ownership, acquire through the old implementation, and resume unchanged bytes. Arbitrary pre-protocol downgrade is not a supported active-run rollback.

Compatibility tests use simultaneous processes, not alternating calls:

- Old and new contenders for one run: one owns and one refuses.
- Distinct runs in one ledger: both proceed under distinct run locks.
- Owner termination during execution: SQLite recovers and the other version takes ownership and resumes nonterminal work once.
- Termination during migration: the schema lock releases and SQLite rollback or idempotent migration completes on reopen.
- llm-kit-to-old rollback resumes a new-created nonterminal run with identical events and terminal state.
- Fresh-create and every migration prefix compare sqlite_master, version rows, pragmas, isolation posture, events, interrupts, and canonical JSON.

No schema change is allowed during coexistence. A change requires a separate dual-readable format, conversion, ownership, and rollback decision.

## Python, bootstrap, marketplace, and guard changes

llm-kit requires Python 3.12. Migration raises requires-python in awesome-kit, workflow-kit, yaml-data-editor-kit, and skills-kit and updates their CI matrices.

Implementation also:

- Adds plugins/llm-kit and its generated marketplace entry.
- Publishes llm_kit through shared_libs and imports bootstrap_lib.
- Adds llm_kit to bootstrap first-party recognition while retaining llm_scripting_kit through coexistence.
- Keeps the old interrupt validator constant and adds an llm-kit-specific probe.
- Migrates consumer plugin declarations and shared imports only after parity.
- Keeps all old marketplace entries through their deprecation windows.

An AST guard over plugins/llm-kit/lib/llm_kit uses the exact adjacency set above. It counts eager, local, TYPE_CHECKING, and literal dynamic imports; forbids root re-exports and old-package imports; forbids jobs/execution cross-imports; keeps product DDL and migration loops product-owned; and reports both packages, import mode, and line. Implementation proves the guard by observing a forbidden import fail before removing it and observing the test pass.

## Decisions for sign-off

1. Use only llm_kit as the new top-level package. Recommendation: yes. Cost: consumers change imports once; benefit: deterministic coexistence.
2. Accept the corrected 16-package map, facade splits, factory injection, and exact edges. Recommendation: yes. Cost: code is reorganized rather than copied as three intact trees.
3. Keep jobs and leased pipeline execution separate above shared execution/storage. Recommendation: yes. Cost: two product models remain; benefit: neither receives the other's policy.
4. Choose sequencing option A (legacy coordination, private consolidation, parity, incremental restructuring, one consumer migration) over option B (one combined acceptance event). Recommendation: A. Cost: more gates; benefit: isolated rollback and no temporary namespace.
5. Preserve DDL/events and require per-run ownership plus tested handover before active ledger coexistence. Recommendation: yes. Cost: legacy compatibility releases; benefit: no dual resume.
6. Retain the verdict cache's advisory last-writer-wins semantics rather than add locking during the merge. Recommendation: yes. Cost: concurrent verdict loss and recomputation; benefit: no incompatible state protocol in the merge.
7. Share legacy credential, config, and routing environment contracts until deletion. Recommendation: yes. Cost: llm-kit carries legacy logical names.
8. Replace migrated CLI use with one venv-first llm-kit command while old commands remain deprecation shims. Recommendation: yes. Cost: scripts migrate.
9. Keep final skill short names under llm-kit, migrate explicit and resumable references first, and keep functional old registrations through the deprecation window. Recommendation: yes. Cost: duplicate registrations temporarily exist; benefit: either selection path succeeds.
10. Keep third-party dependencies in extras around a standard-library completion core. Recommendation: yes. Cost: consumers declare reached groups.
11. Require Python 3.12 and raise the four lagging declarations. Recommendation: yes. Cost: metadata, CI, and possible external 3.10/3.11 users.
12. Retain bootstrap's old validator identity and add llm-kit recognition. Recommendation: yes. Cost: dual-name knowledge during coexistence.
13. Release all components under one llm-kit version. Recommendation: yes. Cost: one component change releases the plugin; benefit: no internal skew.
14. Approve the narrow plugin-boundary exception and proposed plugins/CLAUDE.md amendment while retaining maintainer-content and deprecation rules. Recommendation: yes. Cost: one explicit repository-policy exception.

Sign-off accepts all recommendations or names decisions that must change. No implementation begins before that response.

## Appendix A: legacy module map

Prefixes: L is llm_scripting_kit, C is content_pipeline, and J is job_kit. An asterisk means a facade whose internals split by the rules above.

| Destination | Legacy modules |
|---|---|
| Empty namespaces | L:__init__; C:__init__ |
| schema | L:completion/json_repair, completion/json_schema |
| registry | L:api_key, constants, effort*, env_file, model_endpoints*, models*; slices of declaration*, harness_adapters*, usage_budget* |
| completion | Neutral slice of L:completion/__init__; completion/capabilities, contract, contract_types, halt*, prompt_fold, requirements, results, skill_context, skill_context_types, types; request_protocol; AgentTimeoutError slice of completion/claude_runner* |
| adapters | L:account, _swapper_process, client, completion/backends, completion/adapter_capabilities, completion/claude_runner*, completion/codex_backend*, completion/opencode_backend, harness_adapters*, swapper, swapper_acceptance; raw-reader slice of usage_budget* |
| dispatch | L:completion/endpoint_profile, completion/factory, declaration*, observer, reachability, review_lane, seats, usage_budget*; construction slice of C:llm/backends* |
| frontdoor | L:frontdoor/__init__, frontdoor/__main__, frontdoor/acceptance, frontdoor/server |
| scaffold | C:cli/scaffold |
| storage | C:execution/_atomic_json; connection/transaction/lock slices of C:execution/store*, C:llm/spend_ledger*, and J:store*; no product migration loop |
| execution | Shared slices of C:execution/events*, interrupts*, model*, scheduler* and J:events*, interrupts*, model*, run* |
| jobs | J:__init__, events*, interrupts*, model*, run*, select, store*, workspace, including product DDL and migration loop |
| pipeline.core | C:freshness/seed, llm/convergence, pipeline/__init__, cell_policy, convergence_loop, gate, single_pass, stage, workunit, validate/__init__, validate/contract, validate/floor_guard, validate/riders, vcs/seam |
| pipeline.artifacts | C:cli/unsupported, deliver/*, freshness/* except seed, providers/*, roundtrip/*, store/*, vcs/__init__, vcs/git_vcs, vcs/null_vcs |
| pipeline.runtime | C:cli/budget, llm/__init__, runtime wrapper slice of llm/backends*, llm/gate, llm/platform, llm/spend_ledger*, llm/yaml_extract |
| pipeline.execution | C:execution/__init__, adapter, controller, deadlines, drivers/*, events*, failure_cache, interrupts*, model*, parallel_graph, protocol, scheduler*, status, store*, wave, workerpack, including product DDL and migration loop |
| pipeline.analysis | C:audit/__init__, audit/auditor, audit/reasoning_chain, audit/report, provenance/__init__, provenance/call_audit, provenance/record, provenance/replay, provenance/snapshot |
| cli | L:bootstrap_guard, cli, scripts/llm_scripting_kit_cli; C:cli/__init__, cli/run, scripts/check_consumer_contract; J:cli |

## Appendix B: evidence

- dev/tasks/llm-plugins-merge/inventory-coupling.md
- dev/tasks/llm-plugins-merge/execution-overlap.md
