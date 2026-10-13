"""effort_menu / lower_effort resolve from the endpoint registry entry.

A transport entry resolves through its effort style; a harness entry resolves
through its harness name. Every registry entry here is fake.
"""
from types import SimpleNamespace

import pytest

from llm_scripting_kit import effort, model_endpoints
from llm_scripting_kit.model_endpoints import EndpointRegistryError


def _transport(style):
    return SimpleNamespace(kind=model_endpoints.TRANSPORT_KIND, style=style, harness=None)


def _harness(harness):
    return SimpleNamespace(kind=model_endpoints.HARNESS_KIND, style=None, harness=harness)


@pytest.fixture
def registry(monkeypatch):
    entries = {}

    def fake_entry(name=None, **_):
        if name not in entries:
            raise EndpointRegistryError(f"unknown {name}")
        return entries[name]

    def fake_style(entry):
        return model_endpoints.EffortDelivery(entry.style, "endpoint")

    monkeypatch.setattr(model_endpoints, "resolve_registry_entry", fake_entry)
    monkeypatch.setattr(model_endpoints, "resolve_effort_style", fake_style)
    return entries


def test_menus(registry):
    registry.update(
        n=_transport("ninfer"),
        t=_transport("top-level"),
        c=_transport("chat_template_kwargs"),
        u=_transport("unsupported"),
    )
    assert effort.effort_menu("n") == ("none", "low", "medium", "xhigh")
    assert effort.effort_menu("t") == ("low", "medium", "high")
    assert effort.effort_menu("c") == ("low", "medium", "high")
    assert effort.effort_menu("u") == ()


def test_codex_harness_menu_is_ordered_low_to_high(registry):
    registry["cx"] = _harness("codex")
    assert effort.effort_menu("cx") == ("low", "medium", "high", "xhigh", "max")


def test_codex_harness_lower_effort_walks_down(registry):
    registry["cx"] = _harness("codex")
    assert effort.lower_effort("cx", "max") == "xhigh"
    assert effort.lower_effort("cx", "xhigh") == "high"
    assert effort.lower_effort("cx", "medium") == "low"
    assert effort.lower_effort("cx", "low") is None


def test_codex_harness_lower_effort_unknown_value_is_none(registry):
    registry["cx"] = _harness("codex")
    assert effort.lower_effort("cx", "bogus") is None


def test_claude_harness_menu_and_lower_effort(registry):
    # ClaudeCliBackend passes --effort to the claude CLI, whose help lists
    # (low, medium, high, xhigh, max).
    registry["cl"] = _harness("claude")
    assert effort.effort_menu("cl") == ("low", "medium", "high", "xhigh", "max")
    assert effort.lower_effort("cl", "max") == "xhigh"
    assert effort.lower_effort("cl", "low") is None
    assert effort.lower_effort("cl", "bogus") is None


def test_opencode_harness_has_empty_menu(registry):
    registry["oc"] = _harness("opencode")
    assert effort.effort_menu("oc") == ()
    assert effort.lower_effort("oc", "high") is None


def test_unknown_harness_name_fails_loudly(registry):
    from llm_scripting_kit.harness_adapters import HarnessAdapterError

    registry["zz"] = _harness("nonesuch")
    with pytest.raises(HarnessAdapterError, match="unknown harness"):
        effort.effort_menu("zz")


def test_lower_effort_walks_down(registry):
    registry["n"] = _transport("ninfer")
    assert effort.lower_effort("n", "xhigh") == "medium"
    assert effort.lower_effort("n", "medium") == "low"
    assert effort.lower_effort("n", "low") == "none"
    assert effort.lower_effort("n", "none") is None


def test_lower_effort_remaps_high_on_ninfer(registry):
    registry["n"] = _transport("ninfer")
    assert effort.lower_effort("n", "high") == "medium"


def test_lower_effort_unknown_value_or_no_menu(registry):
    registry.update(n=_transport("ninfer"), u=_transport("unsupported"), t=_transport("top-level"))
    assert effort.lower_effort("n", "bogus") is None
    assert effort.lower_effort("u", "low") is None
    assert effort.lower_effort("t", "low") is None
    assert effort.lower_effort("t", "high") == "medium"


def test_unknown_endpoint_raises(registry):
    with pytest.raises(EndpointRegistryError):
        effort.effort_menu("nope")


def test_real_registry_entry_resolves(tmp_path, monkeypatch):
    path = tmp_path / "model-endpoints.yaml"
    path.write_text(
        "version: 1\ndefault: local\nmodels:\n  local:\n    kind: transport\n"
        "    base_url: http://127.0.0.1:1/v1\n    model: m\n    effort_style: ninfer\n"
    )
    monkeypatch.setenv(model_endpoints.REGISTRY_ENV, str(path))
    assert effort.effort_menu("local") == ("none", "low", "medium", "xhigh")
