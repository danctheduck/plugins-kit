# llm-kit

Dev-only consolidation of `llm-scripting-kit`, `job-kit` and
`content-pipeline-kit` into one plugin with one shared library, `llm_kit`.
The plugin manifest sets `"published": false`, so no marketplace entry exists and
a publish of any other plugin does not ship it. The three legacy plugins stay
installed, published and unchanged.

## Contents

`lib/llm_kit/` holds a quarantined copy of the three legacy libraries under
`llm_kit/_copy/{llm_scripting_kit,content_pipeline,job_kit}`, plus the canonical
`llm_kit/bootstrap_guard.py`. Nothing in `_copy` imports a legacy top-level
package: absolute imports and the classified runtime module names are rewritten
to the copy, and `bootstrap_guard` resolves to `llm_kit.bootstrap_guard`. The
root `llm_kit/__init__.py` is empty.

## Environment

- Python 3.12 or newer.
- The base library path is standard-library only. Extras: `config` (pyyaml),
  `sdk` (openai), `local` (psutil), `frontdoor` (fastapi, uvicorn, httpx),
  `jobs` and `pipeline` (pyyaml).
- Credentials, configuration and routing use the legacy names, precedence and
  locations. llm-kit seeds no configuration of its own.
