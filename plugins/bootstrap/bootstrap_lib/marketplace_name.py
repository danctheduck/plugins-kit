"""Marketplace name of the tree a bootstrap plugin root lives in.

Two layouts put bootstrap two directories below a marketplace directory:

- cache: ``~/.claude/plugins/cache/<marketplace>/bootstrap/<version>`` -- the
  directory name IS the marketplace name.
- dev checkout: ``<checkout>/plugins/bootstrap`` -- the directory name is
  whatever the checkout was cloned as (``plugins-kit2``), while the marketplace
  is named by ``name`` in ``<checkout>/.claude-plugin/marketplace.json``.

:func:`marketplace_name_for` is the one Python derivation. The two hook scripts
(``hooks/sessionstart/session-bootstrap.sh`` and
``hooks/userpromptsubmit/bootstrap-display.sh``) must agree with it before
Python exists, so they share ``hooks/marketplace-name.sh``, a bash port of this
rule; ``tests/bootstrap/test_marketplace_name.py`` runs both on the same trees.
"""

from __future__ import annotations

import json
import os

MANIFEST_RELPATH = os.path.join(".claude-plugin", "marketplace.json")


class MarketplaceManifestError(RuntimeError):
    """``marketplace.json`` exists but does not yield a marketplace name."""


def marketplace_name_for(plugin_root: str) -> str:
    """Return the marketplace name for a bootstrap ``plugin_root``.

    Uses ``name`` from ``<plugin_root>/../../.claude-plugin/marketplace.json``
    when that file exists; otherwise the basename of ``<plugin_root>/../..``
    (the cache layout, and a checkout without a manifest). A manifest that
    exists but is unreadable, not a JSON object, or lacks a non-empty string
    ``name`` raises :class:`MarketplaceManifestError`.
    """
    marketplace_dir = os.path.normpath(os.path.join(plugin_root, "..", ".."))
    manifest = os.path.join(marketplace_dir, MANIFEST_RELPATH)
    if not os.path.isfile(manifest):
        return os.path.basename(marketplace_dir)
    try:
        with open(manifest, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise MarketplaceManifestError(
            f"{manifest} exists but cannot be read as JSON: {exc}") from exc
    name = data.get("name") if isinstance(data, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise MarketplaceManifestError(
            f"{manifest} has no non-empty string top-level 'name'")
    return name
