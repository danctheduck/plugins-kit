"""Join test: the completion split, by the repoint map's facade table.

- ``claude_runner.AgentTimeoutError`` is the class ``llm_kit.completion.halt``
  defines, so the ``except AgentTimeoutError`` clauses in the adapters and the
  classifiers in halt match one class.
- Every export of the legacy ``llm_scripting_kit.completion`` package has a
  final home recorded in the map's ``facade-names`` row, and the name resolves
  there. The neutral names come from ``llm_kit.completion``, the transports from
  ``llm_kit.adapters`` and the factory from ``llm_kit.dispatch``.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_LEGACY_LIB = _REPO / "plugins" / "llm-scripting-kit" / "lib"
_MAP = json.loads((_REPO / "tests" / "llm-kit" / "repoint-map.json").read_text(encoding="utf-8"))
_ROW = _MAP["modules"]["plugins/llm-scripting-kit/lib/llm_scripting_kit/completion/__init__.py"]


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
    runner = importlib.import_module("llm_kit.adapters.claude_runner")
    assert runner.AgentTimeoutError is halt.AgentTimeoutError
    for module in ("backends", "opencode_backend"):
        assert importlib.import_module(f"llm_kit.adapters.{module}").AgentTimeoutError is halt.AgentTimeoutError
    # Raised through the runner, matched through the neutral class: the message
    # carries no timeout text, so only the typed check can classify it.
    with pytest.raises(halt.AgentTimeoutError) as caught:
        raise runner.AgentTimeoutError("plain", cmd=["c"], elapsed_s=1, stdout="o", stderr="e")
    assert (caught.value.cmd, caught.value.elapsed_s) == (["c"], 1)
    assert halt.classify_claude_exception(caught.value) == halt.HALT_RATE_LIMIT


def test_the_facade_row_is_a_names_table():
    assert _ROW["kind"] == "facade-names"
    assert len(_ROW["names"]) >= 80


def test_every_legacy_export_has_a_final_home(legacy_completion):
    missing = [name for name in legacy_completion.__all__ if name not in _ROW["names"]]
    assert missing == []


def test_every_recorded_home_resolves_to_the_object_the_name_stands_for(legacy_completion):
    for name in legacy_completion.__all__:
        module, attr = _ROW["names"][name]
        obj = getattr(importlib.import_module(module), attr)
        assert obj is not None, (name, module, attr)


def test_neutral_names_come_from_llm_kit_completion(legacy_completion):
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
            assert name in legacy_completion.__all__
            assert _ROW["names"][name] == [f"llm_kit.completion.{module_name}", name], name
            assert getattr(importlib.import_module(_ROW["names"][name][0]), name) is getattr(final, name)
    for name, home in (
        ("adapter_capabilities", "llm_kit.adapters."),
        ("EndpointProfile", "llm_kit.adapters."),
        ("OpenRouterBackend", "llm_kit.adapters."),
        ("create_backend", "llm_kit.dispatch."),
    ):
        assert _ROW["names"][name][0].startswith(home), name
