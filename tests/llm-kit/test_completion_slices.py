"""Join test: the completion split and the shim identity rule in ``_copy``.

- A whole-module shim is one module object under the copy name and the final
  name, so a patch, a fake or an ``except`` clause meets the same thing by
  either path (checked here for every shim row in the map).
- ``claude_runner.AgentTimeoutError`` is the class ``llm_kit.completion.halt``
  defines, so the ``except AgentTimeoutError`` clauses in the copy backends
  and the classifiers in halt match one class.
- The copy ``completion/__init__`` keeps every legacy export importable and
  sources the neutral names from ``llm_kit.completion``.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_LEGACY_LIB = _REPO / "plugins" / "llm-scripting-kit" / "lib"
_COPY = "llm_kit._copy.llm_scripting_kit.completion"
_MAP = json.loads((_REPO / "tests" / "llm-kit" / "repoint-map.json").read_text(encoding="utf-8"))


def _copy_module_name(copy_path: str) -> str:
    dotted = copy_path.split("/lib/", 1)[1][:-3].replace("/", ".")
    return dotted[: -len(".__init__")] if dotted.endswith(".__init__") else dotted


_PLAIN_SHIMS = [
    (_copy_module_name(row["copy"]), row["final"])
    for row in _MAP["modules"].values()
    if row["state"] == "shim" and not row["copy"].endswith("/__init__.py")
]


def test_the_map_declares_plain_shims():
    assert len(_PLAIN_SHIMS) >= 40


@pytest.mark.parametrize("copy_name, final_name", _PLAIN_SHIMS, ids=[c.split("_copy.", 1)[1] for c, _ in _PLAIN_SHIMS])
def test_a_plain_shim_is_its_final_module(copy_name, final_name):
    assert importlib.import_module(copy_name) is importlib.import_module(final_name)


@pytest.fixture(scope="module")
def legacy_completion():
    before = set(sys.modules)
    sys.path.insert(0, str(_LEGACY_LIB))
    try:
        yield importlib.import_module("llm_scripting_kit.completion")
    finally:
        sys.path.remove(str(_LEGACY_LIB))
        for name in list(sys.modules):
            if name not in before and name.split(".")[0] == "llm_scripting_kit":
                del sys.modules[name]


def test_agent_timeout_error_is_one_class():
    halt = importlib.import_module("llm_kit.completion.halt")
    runner = importlib.import_module(f"{_COPY}.claude_runner")
    assert runner.AgentTimeoutError is halt.AgentTimeoutError
    for module in ("backends", "opencode_backend"):
        assert importlib.import_module(f"{_COPY}.{module}").AgentTimeoutError is halt.AgentTimeoutError
    assert importlib.import_module(_COPY).AgentTimeoutError is halt.AgentTimeoutError
    # Raised through the copy path, matched through the final class: the message
    # carries no timeout text, so only the typed check can classify it.
    with pytest.raises(halt.AgentTimeoutError) as caught:
        raise runner.AgentTimeoutError("plain", cmd=["c"], elapsed_s=1, stdout="o", stderr="e")
    assert (caught.value.cmd, caught.value.elapsed_s) == (["c"], 1)
    assert halt.classify_claude_exception(caught.value) == halt.HALT_RATE_LIMIT


def test_copy_init_keeps_every_legacy_export(legacy_completion):
    copy = importlib.import_module(_COPY)
    assert sorted(copy.__all__) == sorted(legacy_completion.__all__)
    missing = [name for name in legacy_completion.__all__ if not hasattr(copy, name)]
    assert missing == []


def test_copy_init_sources_neutral_names_from_llm_kit_completion(legacy_completion):
    copy = importlib.import_module(_COPY)
    neutral = {
        "halt": ("HaltError", "HALT_AUTH", "HALT_QUOTA", "classify_halt_text", "classify_openai_exception"),
        "capabilities": ("Capabilities", "ParamCapability", "SHELL_EXEC"),
        "requirements": ("match_capabilities",),
        "contract": ("OutputContract", "evaluate_output", "POLICY_TEXT_ONLY"),
        "skill_context": ("materialize_skill_context",),
        "skill_context_types": ("SkillContext", "SkillContextError"),
        "results": ("derive_dropped_params", "utc_now_iso"),
        "types": ("LLMResponse", "BackendOptions", "COMPLETED"),
    }
    for module_name, names in neutral.items():
        final = importlib.import_module(f"llm_kit.completion.{module_name}")
        for name in names:
            assert getattr(copy, name) is getattr(final, name), (module_name, name)
            assert name in legacy_completion.__all__
    # The adapter and endpoint-profile names are defined in llm_kit.adapters
    # since I5; the factory stays in the copy until dispatch is built.
    for name, home in (
        ("adapter_capabilities", "llm_kit.adapters."),
        ("EndpointProfile", "llm_kit.adapters."),
        ("OpenRouterBackend", "llm_kit.adapters."),
        ("create_backend", "llm_kit._copy."),
    ):
        assert name in copy.__all__
        assert getattr(copy, name).__module__.startswith(home), name


def test_copy_init_binds_no_name_the_legacy_init_lacks(legacy_completion):
    copy = importlib.import_module(_COPY)
    legacy_names = {n for n in vars(legacy_completion) if not n.startswith("__")}
    copy_names = {n for n in vars(copy) if not n.startswith("__")}
    # Submodule attributes are set by the import system on both packages.
    extra = copy_names - legacy_names
    assert all(isinstance(getattr(copy, n), type(importlib)) for n in extra), sorted(extra)
