"""Per-chunk input-token estimates for code-review lane routing.

A review lane's model is chosen per (reviewer, chunk) by comparing the lane's
estimated input size with each registry entry's ``context_budget``. This module
computes that estimate from bytes already on disk; it makes no model call and
is stdlib-only.

The estimate is deliberately coarse: a lane reads its prompt, the chunk diff,
and, depending on the lane, the governing CLAUDE.md/AGENTS.md files and the
full post-image of each changed file.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Iterable, Mapping, Optional

from bootstrap_lib.code_review.lane_prompts import LANE_PROMPTS
from bootstrap_lib.code_review.review_profiles import ContextEstimate, resolve_context_estimate
from bootstrap_lib.instruction_files import resolve_instruction_file

# bytes_per_token and lane_base_tokens are preferences, not constants: they
# resolve through the layered review-profile config (key ``context_estimate``;
# measured basis in defaults/review_profiles.yaml).

VALIDATOR_LANE = "validator"

# Lanes whose input includes the governing CLAUDE.md/AGENTS.md text.
_CLAUDE_MD_LANES = frozenset({"reviewer_a_claude_md_compliance", VALIDATOR_LANE})
# Lanes whose input includes the full post-image of each changed file.
_POST_IMAGE_LANES = frozenset({"reviewer_c_introduced_code"})


def lane_names() -> tuple[str, ...]:
    """Every lane name an estimate is emitted for."""
    return (*LANE_PROMPTS.keys(), VALIDATOR_LANE)


def _prompt_bytes(lane: str) -> int:
    """Prompt bytes for a lane; the validator has no canonical lane prompt."""
    prompt = LANE_PROMPTS.get(lane)
    if prompt is None:
        return 0
    return len((prompt.system + prompt.user_preamble).encode("utf-8"))


def file_bytes(path: str) -> int:
    """Size of a file on disk; a missing file (deleted in the change) is 0."""
    try:
        return os.stat(path).st_size
    except FileNotFoundError:
        return 0


def bytes_to_tokens(n_bytes: int, estimate: ContextEstimate) -> int:
    return math.ceil(n_bytes / estimate.bytes_per_token)


def estimate_chunk_tokens(
    chunk_bytes: int,
    estimate: ContextEstimate,
    claude_md_paths: Iterable[str],
    post_image_paths: Iterable[str],
    autoload_paths: Iterable[str] = (),
) -> dict[str, int]:
    """Return {lane name: estimated input tokens} for one diff chunk.

    ``estimate`` carries the resolved ``bytes_per_token`` / ``lane_base_tokens``.

    ``claude_md_paths`` is the union of governing instruction files for the
    chunk's files; duplicates count once. ``post_image_paths`` are the chunk's
    files as they stand after the change. ``autoload_paths`` are the
    instruction files the harness loads into every subagent at the project
    root; they count for every lane. A governing file that is also auto-loaded
    still counts in the standards lanes' term, because those lanes read the
    governing files again as tool results (measured: a reviewer_a lane that
    read the root and plugins CLAUDE.md peaked above the sum of both terms).
    """
    autoload_bytes = sum(file_bytes(p) for p in set(autoload_paths))
    claude_md_bytes = sum(file_bytes(p) for p in set(claude_md_paths))
    post_image_bytes = sum(file_bytes(p) for p in set(post_image_paths))
    out: dict[str, int] = {}
    for lane in lane_names():
        total = chunk_bytes + _prompt_bytes(lane) + autoload_bytes
        if lane in _CLAUDE_MD_LANES:
            total += claude_md_bytes
        if lane in _POST_IMAGE_LANES:
            total += post_image_bytes
        out[lane] = math.ceil(bytes_to_tokens(total, estimate) + estimate.lane_base_tokens)
    return out


def annotate_chunks(
    diff_chunks: list[dict],
    files_by_identifier: Mapping[str, Mapping[str, object]],
    workspace_root: Optional[Path] = None,
    estimate: Optional[ContextEstimate] = None,
) -> None:
    """Attach ``est_tokens`` to every diff chunk entry, in place.

    ``files_by_identifier`` maps a chunk file identifier to a mapping with
    ``local`` (str or falsy) and ``claude_mds`` (list of paths).
    ``workspace_root`` names the project root whose CLAUDE.md / AGENTS.md the
    harness auto-loads. ``estimate`` defaults to the layered
    ``context_estimate`` resolved for ``workspace_root`` (shipped defaults
    alone when there is no root).
    """
    if estimate is None:
        estimate = resolve_context_estimate(workspace_root)
    autoload: list[str] = []
    if workspace_root is not None:
        found = resolve_instruction_file(workspace_root)
        if found is not None:
            autoload.append(str(found))
    for entry in diff_chunks:
        mds: set[str] = set()
        locals_: list[str] = []
        for ident in entry["files"]:
            info: Optional[Mapping[str, object]] = files_by_identifier.get(ident)
            if info is None:
                raise KeyError(f"chunk file {ident!r} has no file record")
            mds.update(info.get("claude_mds") or [])  # type: ignore[arg-type]
            local = info.get("local")
            if local:
                locals_.append(str(local))
        entry["est_tokens"] = estimate_chunk_tokens(entry["bytes"], estimate, mds, locals_, autoload)
