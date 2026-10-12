"""context_budget: registry key validation and describe --context-tokens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_scripting_kit import declaration as decl
from llm_scripting_kit.cli import main
from llm_scripting_kit.model_endpoints import HARNESS_KIND, EndpointEntry, EndpointMetadataError
from llm_scripting_kit.models import DEFAULT_MODEL_CONFIG, discover_model_entries, load_model_config
from llm_scripting_kit.reachability import STATUS_REACHABLE, Reachability


def _entry(entry_id, budget=None):
    return EndpointEntry(
        id=entry_id, base_url=None, model=f"{entry_id}-model", kind=HARNESS_KIND,
        harness="claude", context_budget=budget,
    )


def _describe(entries, names, **kw):
    cache = {n: Reachability(status=STATUS_REACHABLE, checked="cli-version", detail="") for n in names}
    return decl.describe(
        names, caller="session", entries=entries, reachability_cache=cache, **kw
    )


ENTRIES = {"haiku": _entry("haiku", 100000), "sonnet": _entry("sonnet")}


def test_budgeted_entry_in_menu_below_and_out_above_the_budget():
    below = _describe(ENTRIES, ["haiku", "sonnet"], context_tokens=99999)
    assert [e.id for e in below.rendered_entries] == ["haiku", "sonnet"]
    at = _describe(ENTRIES, ["haiku", "sonnet"], context_tokens=100000)
    assert [e.id for e in at.rendered_entries] == ["haiku", "sonnet"]
    above = _describe(ENTRIES, ["haiku", "sonnet"], context_tokens=100001)
    assert [e.id for e in above.rendered_entries] == ["sonnet"]


def test_no_flag_leaves_budgeted_entry_alone():
    ranking = _describe(ENTRIES, ["haiku", "sonnet"])
    assert [e.id for e in ranking.rendered_entries] == ["haiku", "sonnet"]


def test_floor_names_the_reason_when_all_entries_are_over_budget():
    with pytest.raises(decl.NoUsableRoutingTarget) as excinfo:
        _describe({"haiku": _entry("haiku", 100000)}, ["haiku"], context_tokens=100001)
    payload = excinfo.value.to_json()
    assert payload["dispositions"][0]["detail"] == "over context budget (100000 < 100001)"
    assert "over context budget (100000 < 100001)" in str(excinfo.value)


@pytest.mark.parametrize("bad", [0, -5, "100000", 1.5, True])
def test_invalid_context_budget_raises(bad):
    cfg = {"endpoints": {"x": {"harness": "claude", "model": "x", "context_budget": bad}}}
    with pytest.raises(EndpointMetadataError, match="x.*context_budget"):
        discover_model_entries(config=cfg)


def test_invalid_context_tokens_raises():
    with pytest.raises(ValueError, match="context_tokens"):
        _describe(ENTRIES, ["haiku"], context_tokens=-1)


def test_shipped_haiku_has_a_budget_and_sonnet_does_not():
    endpoints = DEFAULT_MODEL_CONFIG["endpoints"]
    assert endpoints["haiku"]["context_budget"] == 100000
    assert "context_budget" not in endpoints["sonnet"]


def test_cli_flag_rejects_negative(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["describe", "haiku", "--context-tokens", "-1"])
    assert excinfo.value.code == 2


def _layer(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fleet(home: Path) -> Path:
    return home / ".claude" / "config" / "llm-scripting-kit.yaml"


def _machine(home: Path) -> Path:
    return (
        home / ".claude" / "plugins" / "data" / "plugins-kit"
        / "llm-scripting-kit" / "config.yaml"
    )


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path


def _haiku_menu(tokens):
    entries = discover_model_entries(config=load_model_config())
    return [e.id for e in _describe(entries, ["haiku"], context_tokens=tokens).rendered_entries]


def test_fleet_null_removes_the_shipped_haiku_budget(home):
    with pytest.raises(decl.NoUsableRoutingTarget):
        _haiku_menu(500000)  # shipped 100000 filters it
    _layer(_fleet(home), "endpoints:\n  haiku:\n    context_budget: null\n")
    assert _haiku_menu(500000) == ["haiku"]


def test_integer_override_changes_the_threshold(home):
    _layer(_fleet(home), "endpoints:\n  haiku:\n    context_budget: 600000\n")
    assert _haiku_menu(500000) == ["haiku"]
    with pytest.raises(decl.NoUsableRoutingTarget):
        _haiku_menu(600001)


def test_higher_layer_null_beats_lower_integer_and_later_integer_beats_null(home):
    _layer(_fleet(home), "endpoints:\n  haiku:\n    context_budget: 200000\n")
    _layer(_machine(home), "endpoints:\n  haiku:\n    context_budget: null\n")
    assert _haiku_menu(500000) == ["haiku"]
    _layer(_fleet(home), "endpoints:\n  haiku:\n    context_budget: null\n")
    _layer(_machine(home), "endpoints:\n  haiku:\n    context_budget: 300000\n")
    with pytest.raises(decl.NoUsableRoutingTarget):
        _haiku_menu(300001)


def test_invalid_override_in_a_layer_raises(home):
    _layer(_fleet(home), "endpoints:\n  haiku:\n    context_budget: 0\n")
    with pytest.raises(EndpointMetadataError, match="haiku.*context_budget"):
        discover_model_entries(config=load_model_config())
