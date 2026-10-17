# llm-kit

One plugin and one shared library, `llm_kit`, for LLM access, durable agent
jobs and batch content pipelines. It consolidates `llm-scripting-kit`, `job-kit`
and `content-pipeline-kit` (migrated from those plugins; they stay installed,
published and unchanged, and llm-kit never imports them).
The plugin manifest sets `"published": false`, so no marketplace entry exists and
a publish of any other plugin does not ship it.

## Library

`lib/llm_kit/` holds the library, plus `llm_kit/bootstrap_guard.py`. The
sub-packages are `completion`, `adapters`, `dispatch`, `registry`, `schema`,
`storage`, `execution`, `jobs`, `pipeline` (`core`, `artifacts`, `runtime`,
`execution`, `analysis`), `frontdoor` and `scaffold`. The root initializers are
empty: import the sub-package you need.

## CLI

The console script is `llm-kit = llm_kit.cli:main`, with the groups `account`,
`completion`, `models`, `jobs`, `pipeline`, `frontdoor` and `local`. Run it by
its version-free venv path, which works from any shell and directory:

```
"${CLAUDE_BOOTSTRAP_DATA_ROOT:-$HOME/.claude/plugins/data}"/plugins-kit/llm-kit/.venv/bin/llm-kit
(Windows: "${CLAUDE_BOOTSTRAP_DATA_ROOT:-$HOME/.claude/plugins/data}"/plugins-kit/llm-kit/.venv/Scripts/llm-kit.exe)
```

Exit codes are `0` for success, `1` for a runtime failure, `2` for invalid input
or configuration, `3` for a classified persistent halt, `4` for a request the
completion protocol refused and `5` when `models probe` could not determine
reachability. The `jobs` group has its own table (`llm-kit jobs --help`): `0`
every job accepted, `1` a job not accepted, `2` usage, `3` the runner itself
failed, `4` a job waiting on an interrupt.

## Consumer contract

`contract/public-surface.json` lists the public names of the pipeline products
(`llm_kit.pipeline.*`, `llm_kit.scaffold`, `llm_kit.cli.run`) and whether each is
public, deprecated or removed. A stdlib-only scanner reads it over a consumer's
source and reports the deprecated and removed names in use:

```
"${BOOTSTRAP_PYTHON:?requires bootstrap >= 0.120.0}" "${LLM_KIT_ROOT:?requires a bootstrap engine pass; run bootstrap run}/scripts/check_consumer_contract.py" <consumer source path>
```

It exits 1 when a removed name is used (a deprecated name too under `--strict`)
and 2 when the contract cannot be read.

## Local model servers and the front door

`scripts/model-server.sh qwen36|qwen38|qwen38l` starts a local model server on its
measured profile (NInfer for `qwen36` and `qwen38`, llama.cpp for `qwen38l`). It
asks `llm-kit local swapper guard-launch` before it execs, and only that verb's
exit `3` blocks the launch. `scripts/qwen-switch.sh start|status` replaces and
inspects the resident server, freeing the port with
`llm-kit local swapper terminate-listener`. `scripts/frontdoor.sh` runs
`llm-kit frontdoor`. The scripts call the sibling `bin/llm-kit` by path, and
`bin/qwen36-server`, `bin/qwen38-server`, `bin/qwen38l-server` and
`bin/qwen-switch` are thin adapters for a PATH. A command anchors on the plugin
directory:

```
"${LLM_KIT_ROOT:?requires a bootstrap engine pass; run bootstrap run}/scripts/model-server.sh" qwen38 --print-command
```

Paths, ports, hosts and the context keep their legacy environment names, and so
does the guard opt-out, `LLM_SCRIPTING_KIT_LAUNCH_GUARD=off`.
`tests/llm-kit/test_local_launchers.py` runs the scripts against fake binaries.

## Documentation

`CLAUDE.md` is the agent guidance, organized by library package: the layer rules,
the stances and gotchas of each component, and the register of hardcoded
opinions. The long-form documents live in `references/`:

| Document | Covers |
|---|---|
| `references/llm-access.md` | The registry, credentials, the completion seam, model declarations, the `account`, `completion`, `models`, `frontdoor` and `local` groups, the front door and the swapper |
| `references/completion-seam-contract.md` | What one completion call guarantees: the capability advertisement, the response report, output contracts, skill context and the request protocol |
| `references/jobs.md` | The `jobs` group: the job file, selection, acceptance contracts, parallelism, backpressure, events and durable interrupts |
| `references/pipeline-library.md` | The `llm_kit.pipeline` packages: structured output, cost and budget, routing, the adaptive gate, deadlines, durable waits and provenance |

## Registrations

| Kind | Qualified name | Source |
|---|---|---|
| skill | `llm-kit:openrouter-account` | `skills/openrouter-account/` |
| skill | `llm-kit:content-pipeline-domain` | `skills/content-pipeline-domain/` |
| skill | `llm-kit:background-pipeline` | `skills/background-pipeline/` |
| skill | `llm-kit:execute-work-unit` | `skills/execute-work-unit/` |
| skill | `llm-kit:workflow-pipeline` | `skills/workflow-pipeline/` |
| agent | `llm-kit:pipeline-worker` | `agents/pipeline-worker.md` |
| workflow | `llm-kit:run-ready-wave` | `workflows/run-ready-wave.js` |

A command in a document under `references/` or this README that needs the
plugin directory anchors on `"${LLM_KIT_ROOT:?requires a bootstrap engine pass; run bootstrap run}"`.
A skill body uses the harness variables for the plugin and skill directories.
A Python script runs under `"${BOOTSTRAP_PYTHON:?requires bootstrap >= 0.120.0}"`.

`tests/llm-kit/test_registrations.py` checks the names, the absence of legacy
package, CLI and plugin-root references, and the interpreter rule.

## Environment

- Python 3.12 or newer.
- The base library path is standard-library only. Extras: `config` (pyyaml),
  `sdk` (openai), `local` (psutil), `frontdoor` (fastapi, uvicorn, httpx),
  `jobs` and `pipeline` (pyyaml).
- Credentials, configuration and routing use the legacy names, precedence and
  locations (for example the user-scoped `.env` under
  `plugins-kit/llm-scripting-kit/.env`). llm-kit seeds no configuration of its own.
