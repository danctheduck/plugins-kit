#!/usr/bin/env bash
# Launch the llm-kit front door (`llm-kit frontdoor`).
#
# The plugin-relative sibling bin/llm-kit is called by path, never from PATH. That
# shim owns interpreter selection: the llm-kit plugin venv first (it carries the
# front door's web stack), the redirected venv under a claudx data root, and the
# cached-copy refusal. This script names no interpreter of its own.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LLM_KIT_CLI="$PLUGIN_ROOT/bin/llm-kit"

if [[ "${1:-}" == "--print-command" ]]; then
    shift
    printf '%q ' "$LLM_KIT_CLI" frontdoor "$@"
    printf '\n'
    exit 0
fi
if [[ ! -x "$LLM_KIT_CLI" ]]; then
    printf 'frontdoor: llm-kit launcher not found: %s\n' "$LLM_KIT_CLI" >&2
    exit 1
fi
exec "$LLM_KIT_CLI" frontdoor "$@"
