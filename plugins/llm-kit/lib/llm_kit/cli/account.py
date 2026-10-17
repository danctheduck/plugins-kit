"""``llm-kit account``: credential status, source lookup and key storage.

Carries the legacy ``status``, ``which`` and ``set-key`` verbs. The CLI is the
composition root for credentials: it resolves them through
``llm_kit.registry`` (``resolve_endpoint``, ``get_api_key``, the user ``.env``
file) and injects the key into ``llm_kit.adapters.account``, which performs the
network check and reads no credential itself.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from typing import Optional, Sequence

from llm_kit.adapters.account import AccountCheckError, validate_endpoint
from llm_kit.cli._common import (
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    _add_endpoint_arg,
    guarded,
)
from llm_kit.registry.api_key import get_api_key
from llm_kit.registry.constants import USER_ENV_FILE
from llm_kit.registry.env_file import read_env_file, write_env_file
from llm_kit.registry.models import EndpointResolveError, resolve_endpoint


def _resolve_endpoint_or_exit(endpoint: Optional[str]) -> Optional[dict]:
    try:
        return resolve_endpoint(endpoint)
    except EndpointResolveError as exc:
        print(f"Endpoint error: {exc}", file=sys.stderr)
        return None


def _cmd_status(endpoint: Optional[str]) -> int:
    ep = _resolve_endpoint_or_exit(endpoint)
    if ep is None:
        return EXIT_USAGE
    lookup = get_api_key(endpoint=endpoint)
    if lookup.key is None:
        print(f"No API key found for endpoint '{ep['name']}' ({ep['key_env']}).")
        return EXIT_FAILURE
    print(f"Endpoint: {ep['name']} ({ep['base_url']})")
    print(f"Source: {lookup.source}" + (f" ({lookup.source_path})" if lookup.source_path else ""))
    try:
        status = validate_endpoint(ep, lookup.key)
    except AccountCheckError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if status is None:
        print(f"Status: key present (account_check '{ep['account_check']}' -- not validated)")
        return EXIT_OK
    if not status.ok:
        print(f"Status: REJECTED ({status.failure_reason})")
        if status.failure_reason == "auth":
            print("The key was rejected (HTTP 401).")
            if ep["account_check"] == "openrouter":
                print("Generate a new one at https://openrouter.ai/keys.")
        elif status.failure_reason == "no_credit":
            print("Account out of credit (HTTP 402). Add credit at https://openrouter.ai/credits.")
        return EXIT_FAILURE
    print("Status: OK")
    print(f"Label: {status.label or '<unlabeled>'}")
    if status.usage is not None:
        print(f"Usage: {status.usage}")
    if status.limit is not None:
        print(f"Limit: {status.limit}")
    if status.is_free_tier is not None:
        print(f"Free tier: {status.is_free_tier}")
    if status.rate_limit:
        print(f"Rate limit: {json.dumps(status.rate_limit)}")
    return EXIT_OK


def _cmd_set_key(provided: Optional[str], *, validate: bool, endpoint: Optional[str]) -> int:
    ep = _resolve_endpoint_or_exit(endpoint)
    if ep is None:
        return EXIT_USAGE
    key = provided
    if not key:
        try:
            key = getpass.getpass(f"API key for {ep['name']} (input hidden): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            return 130
    if not key:
        print("Empty key, nothing written.", file=sys.stderr)
        return EXIT_FAILURE
    if validate:
        try:
            status = validate_endpoint(ep, key)
        except AccountCheckError as exc:
            print(f"Could not validate key: {exc}", file=sys.stderr)
            print("Pass --no-validate to write the key without checking it.", file=sys.stderr)
            return EXIT_USAGE
        if status is not None and not status.ok:
            print(f"Validation failed: {status.failure_reason}", file=sys.stderr)
            return EXIT_FAILURE
    existing = read_env_file(USER_ENV_FILE)
    existing[ep["key_env"]] = key
    write_env_file(USER_ENV_FILE, existing)
    print(f"Wrote {ep['key_env']} to {USER_ENV_FILE}")
    return EXIT_OK


def _cmd_which(endpoint: Optional[str]) -> int:
    if _resolve_endpoint_or_exit(endpoint) is None:
        return EXIT_USAGE
    lookup = get_api_key(endpoint=endpoint)
    if lookup.key is None:
        print("missing")
        return EXIT_FAILURE
    print(f"{lookup.source}" + (f": {lookup.source_path}" if lookup.source_path else ""))
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-kit account",
        description="Credential status, source lookup and key storage for a configured endpoint.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("status", "which"):
        command = sub.add_parser(name)
        _add_endpoint_arg(command)
    set_key = sub.add_parser("set-key")
    _add_endpoint_arg(set_key)
    set_key.add_argument("--key")
    set_key.add_argument("--no-validate", action="store_true")
    return parser


def run(argv: Sequence[str]) -> int:
    """Run one ``account`` verb and return its exit code."""
    args = _parser().parse_args(list(argv))

    def dispatch() -> int:
        if args.cmd == "status":
            return _cmd_status(args.endpoint)
        if args.cmd == "set-key":
            return _cmd_set_key(args.key, validate=not args.no_validate, endpoint=args.endpoint)
        if args.cmd == "which":
            return _cmd_which(args.endpoint)
        return EXIT_USAGE

    return guarded(dispatch)
