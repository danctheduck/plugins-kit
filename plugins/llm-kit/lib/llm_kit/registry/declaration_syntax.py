"""The model-declaration syntax seam: the validator probe and its support error.

A model declaration is a list of registry ids naming which model(s) may do a
unit of work (the format is specified in bootstrap's plugin-dev skill,
``references/model-declaration.md``, and validated structurally by
``bootstrap_lib.model_declaration``). This module owns only the probe that
returns that validator, so the registry can read a default declaration without
importing the dispatch policy that describes and runs declarations.
"""
from __future__ import annotations

from typing import Any

#: The bootstrap release that shipped ``bootstrap_lib.model_declaration``.
_MODEL_DECLARATION_BOOTSTRAP = "0.129.0"


class DeclarationSupportError(ImportError):
    """``bootstrap_lib.model_declaration`` is absent or too old here.

    llm-scripting-kit links ``bootstrap_lib`` (its ``shared_lib_imports``) and
    bootstrap is a declared dependency of every plugin, so the posture is
    REQUIRED: without the structural validator there is no declaration to
    describe. The two states are diagnosed apart because they have different
    remedies.
    """


def _model_declaration() -> Any:
    """Return ``bootstrap_lib.model_declaration``, probed for the symbols used."""
    try:
        import bootstrap_lib  # noqa: F401, PLC0415
    except ImportError as exc:
        raise DeclarationSupportError(
            "bootstrap_lib is not linked into this environment; declare "
            "'bootstrap_lib' in the consuming plugin's bootstrap.json "
            "shared_lib_imports (llm-scripting-kit's describe/run need "
            f"bootstrap >= {_MODEL_DECLARATION_BOOTSTRAP})"
        ) from exc
    try:
        from bootstrap_lib import model_declaration  # noqa: PLC0415
    except ImportError:
        model_declaration = None
    if (
        model_declaration is None
        or not callable(getattr(model_declaration, "parse", None))
        or not isinstance(getattr(model_declaration, "CORE_IDS", None), frozenset)
    ):
        raise DeclarationSupportError(
            "the linked bootstrap_lib predates model_declaration.parse/CORE_IDS; "
            f"llm-scripting-kit's describe/run need bootstrap >= "
            f"{_MODEL_DECLARATION_BOOTSTRAP} -- update the bootstrap plugin"
        )
    return model_declaration
