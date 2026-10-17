"""Bootstrap script for llm-kit.

Single entry point ``bootstrap(ctx)`` runs at session start and checks the
OpenRouter credential:

1. Resolves the key from the environment variable, the per-project ``.env`` or
   the user-scoped credential file, through ``llm_kit.registry.api_key``. The
   credential locations are the shared legacy ones (the user ``.env`` is
   ``USER_ENV_FILE``); this script reads them and seeds none.
2. If the key is missing, records a DEFERRED REQUIREMENT -- never a fix-all
   entry. An OpenRouter key is a precondition only some sessions need, so
   bootstrap does not ask for it at session start; the skill that needs the key
   preflights and asks at the point of need. See the bootstrap skill's
   deferred-requirement pattern.
3. If present, validates the key against ``GET /auth/key``. Failures (401, 402)
   are deferred the same way, with specific remediation. Successful checks are
   content-hashed into ``last_validated.sha256`` (hash + validation timestamp)
   under ``ctx.data_dir`` so subsequent sessions skip the network round-trip
   when the key has not changed -- but only for about 7 days, so revocation or
   credit exhaustion is re-detected without a key change.

The script is stdlib-only -- it imports ``llm_kit`` from ``lib/`` beside this
file. No venv required.
"""

import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional, Tuple

# Make the bundled lib/ importable (the engine runs this file by path).
_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from llm_kit.adapters.account import AccountCheckError, check_account  # noqa: E402
from llm_kit.registry.api_key import get_api_key  # noqa: E402
from llm_kit.registry.constants import USER_ENV_FILE, cli_command  # noqa: E402

# A successful /auth/key validation is cached against the key's hash, but never
# forever: past this age the key is re-validated so revocation or credit
# exhaustion is detected even when the key text has not changed.
_REVALIDATE_AFTER_SECONDS = 7 * 24 * 60 * 60  # ~7 days


def _set_key_command() -> str:
    return f"{cli_command()} account set-key"


def _defer(ctx: Any, *, user_msg: str, agent_msg: str) -> None:
    """Record the credential requirement without escalating it.

    An OpenRouter key is a precondition only SOME sessions need -- most never
    call the API at all -- so bootstrap does not ask for it. It records the
    requirement and the skill that needs the key asks at the point of need
    (see the bootstrap skill's deferred-requirement pattern).

    Guarded on the engine actually providing the API: on a bootstrap older
    than 0.71.0 the requirement is simply dropped. Falling back to add_failure
    there would resurrect the session-start nag this exists to remove.
    """
    defer = getattr(ctx, "add_deferred_requirement", None)
    if defer is None:
        return
    defer(
        "openrouter_credential",
        user_msg=user_msg,
        agent_msg=agent_msg,
        satisfied_by=_set_key_command(),
    )


def bootstrap(ctx: Any) -> None:
    """Validate the OpenRouter credential.

    ``llm_kit`` is published as a shared library to the standalone Python (and
    consuming plugin venvs) declaratively via the ``shared_libs`` key in this
    plugin's bootstrap.json -- the bootstrap engine handles the .pth
    registration, so this script only checks the API credential.
    """
    project_root = _resolve_project_root(ctx)
    set_key = _set_key_command()

    # 1. The canonical resolution path (env -> project .env -> user .env).
    lookup = get_api_key(project_root)

    # 2. Missing -> deferred requirement, NOT a fix-all entry.
    if lookup.key is None:
        _defer(
            ctx,
            user_msg=(
                "llm-kit has no OpenRouter API key yet. Nothing to do "
                "until you run something that calls the API -- it will ask then."
            ),
            agent_msg=(
                "llm-kit needs an OpenRouter API key. Give the user "
                "this prepared statement, verbatim:\n\n"
                "  > llm-kit needs an API key. Two ways to set it:\n"
                "  >   1. (preferred -- key stays out of the transcript) Type "
                "this in the prompt with the leading `!`:\n"
                f"  >        ! {set_key}\n"
                "  >      It'll prompt for the key with a hidden input. "
                "Paste from https://openrouter.ai/keys (starts with `sk-or-v1-`).\n"
                "  >   2. If you'd rather paste the key here and have me set "
                "it for you, paste it. WARNING: the key will be visible in "
                "the transcript, so prefer option 1 unless you don't mind.\n\n"
                "If the user picks option 2 and pastes a key, run:\n"
                f"  {set_key} --key <THE_KEY>\n"
                "It validates against GET /auth/key before writing to "
                f"{USER_ENV_FILE}. Do NOT run `{set_key}` "
                "without --key yourself -- it requires an interactive hidden "
                "prompt you cannot provide; it must be the user who runs the "
                "bang-prefixed form."
            ),
        )
        # log_ok, not log: a missing key is the expected state on a machine
        # that has never called the API, so it belongs in verbose output only.
        ctx.log_ok("openrouter: no API key (deferred until a capability needs it)")
        return

    # 3. Have a key. Validate against /auth/key, with content-hash caching.
    # The cache is honored only while fresh (< _REVALIDATE_AFTER_SECONDS); a
    # matching hash with a missing/old timestamp (incl. a hash-only file)
    # re-validates so revocation / credit exhaustion is re-detected.
    cache_file = Path(ctx.data_dir) / "last_validated.sha256"
    key_hash = hashlib.sha256(lookup.key.encode("utf-8")).hexdigest()
    cached_hash, cached_epoch = _read_cache(cache_file)

    if (
        cached_hash == key_hash
        and cached_epoch is not None
        and (time.time() - cached_epoch) < _REVALIDATE_AFTER_SECONDS
    ):
        ctx.log_ok(f"openrouter: key validated (cached, source={lookup.source})")
        return

    try:
        status = check_account(lookup.key)
    except AccountCheckError as e:
        # Network failure / unexpected status. Don't block bootstrap on
        # transient connectivity issues -- log and continue. The next
        # session-start retry validates again because no cache was written.
        ctx.log(f"openrouter: validation skipped ({e})")
        return

    if status.ok:
        _write_cache(ctx, cache_file, key_hash)
        label = status.label or "<unlabeled>"
        ctx.log(f"openrouter: key validated ({label}, source={lookup.source})")
        return

    if status.failure_reason == "auth":
        _defer(
            ctx,
            user_msg=(
                "Your OpenRouter API key was rejected (HTTP 401). "
                "Generate a new one at https://openrouter.ai/keys and run "
                f"`{set_key}`."
            ),
            agent_msg=(
                f"OpenRouter rejected the API key currently in {lookup.source_path or USER_ENV_FILE} "
                f"with HTTP 401. Ask the user to generate a fresh key at "
                f"https://openrouter.ai/keys and run `{set_key}`."
            ),
        )
        ctx.log_ok("openrouter: key REJECTED (HTTP 401) -- deferred to point of use")
        return

    if status.failure_reason == "no_credit":
        _defer(
            ctx,
            user_msg=(
                "Your OpenRouter account is out of credit (HTTP 402). "
                "Add credit at https://openrouter.ai/credits."
            ),
            agent_msg=(
                "OpenRouter returned HTTP 402 (insufficient credit). The key "
                "is valid but the account has no balance. Ask the user to "
                "add credit at https://openrouter.ai/credits."
            ),
        )
        ctx.log_ok("openrouter: account OUT OF CREDIT (HTTP 402) -- deferred to point of use")
        return


def _resolve_project_root(ctx: Any) -> Path:
    """Project root for per-project .env lookup.

    ``ctx.project_dir`` is the canonical Claude Code launch CWD (may be None
    for non-project sessions). When None, falls back to the actual CWD.
    """
    if getattr(ctx, "project_dir", None):
        return Path(ctx.project_dir)
    return Path.cwd()


def _read_cache(path: Path) -> Tuple[Optional[str], Optional[float]]:
    """Return (key_hash, validated_epoch) from the cache file.

    File format: hash on line 1, epoch seconds on line 2. A hash-only file
    yields (hash, None), which callers treat as stale.
    """
    try:
        lines = path.read_text(encoding="utf-8").split()
    except OSError:
        return (None, None)
    if not lines:
        return (None, None)
    epoch: Optional[float] = None
    if len(lines) > 1:
        try:
            epoch = float(lines[1])
        except ValueError:
            epoch = None
    return (lines[0], epoch)


def _write_cache(ctx: Any, path: Path, value: str) -> None:
    """Write the validation cache; an unwritable cache only costs a re-check, so say so."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{value}\n{int(time.time())}\n", encoding="utf-8")
    except OSError as e:
        ctx.log(f"openrouter: validation cache not written ({e})")
