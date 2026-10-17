"""Join test: the adapters split and the identity rules in ``_copy`` (I5).

- ``harness_adapters`` is a whole shim over ``llm_kit.adapters.harness_adapters``,
  which re-imports the registry.effort names the copy used to expose, so the
  copy name, the adapters name and the registry name are one object each.
- ``HarnessAdapterError``, ``AgentTimeoutError`` and the swapper error classes
  are each one class across the copy and final names, so an ``except`` clause on
  either side catches what the other raises.
- ``usage_budget`` is a whole shim over ``llm_kit.dispatch.usage_budget`` (I6):
  the pacing policy and the verdict cache are there, the readers are
  ``llm_kit.adapters.usage_sources``. A patch on a reader name, on
  ``VERDICT_CACHE`` or on ``_load_cache``/``_store_cache`` through the copy name
  acts on the one module object that runs, and a reader patch also reaches the
  final codex backend, exactly as when the readers were defined in the copy
  module.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_COPY = "llm_kit._copy.llm_scripting_kit"
_MAP = json.loads((_REPO / "tests" / "llm-kit" / "repoint-map.json").read_text(encoding="utf-8"))

NOW = 1_800_000_000
WEEK = 7 * 24 * 3600


def _mod(name: str):
    return importlib.import_module(name)


# --------------------------------------------------------------------------
# harness_adapters: whole shim
# --------------------------------------------------------------------------

_HARNESS_ROW = _MAP["modules"]["plugins/llm-scripting-kit/lib/llm_scripting_kit/harness_adapters.py"]


def test_harness_adapters_is_a_whole_shim():
    assert _HARNESS_ROW["state"] == "shim"
    assert _HARNESS_ROW["final"] == "llm_kit.adapters.harness_adapters"
    assert _mod(f"{_COPY}.harness_adapters") is _mod("llm_kit.adapters.harness_adapters")


def test_harness_adapters_reexports_the_registry_effort_names_as_the_same_objects():
    effort = _mod("llm_kit.registry.effort")
    copy = _mod(f"{_COPY}.harness_adapters")
    names = (
        "CLAUDE_EFFORT_ORDER", "CLAUDE_HARNESS", "CODEX_EFFORT_ORDER", "CODEX_HARNESS",
        "OPENCODE_HARNESS", "_HARNESS_EFFORT_ORDERS", "HarnessAdapterError",
        "harness_effort_order",
    )
    for name in names:
        assert getattr(copy, name) is getattr(effort, name), name


def test_the_copy_package_root_exports_the_same_harness_error():
    effort = _mod("llm_kit.registry.effort")
    assert _mod(_COPY).HarnessAdapterError is effort.HarnessAdapterError


def test_harness_adapter_error_is_one_class():
    effort = _mod("llm_kit.registry.effort")
    adapters = _mod("llm_kit.adapters.harness_adapters")
    copy = _mod(f"{_COPY}.harness_adapters")
    assert copy.HarnessAdapterError is adapters.HarnessAdapterError is effort.HarnessAdapterError
    # Raised by the final resolver, caught through the copy name.
    with pytest.raises(copy.HarnessAdapterError):
        adapters.resolve_harness_adapter(types.SimpleNamespace(id="x", kind="transport"))


# --------------------------------------------------------------------------
# error classes
# --------------------------------------------------------------------------

def test_agent_timeout_error_is_one_class_across_copy_and_adapters():
    halt = _mod("llm_kit.completion.halt")
    for name in (
        f"{_COPY}.completion.claude_runner", f"{_COPY}.completion.backends",
        f"{_COPY}.completion.opencode_backend", "llm_kit.adapters.claude_runner",
        "llm_kit.adapters.backends", "llm_kit.adapters.opencode_backend",
        f"{_COPY}.completion",
    ):
        assert _mod(name).AgentTimeoutError is halt.AgentTimeoutError, name
    runner = _mod(f"{_COPY}.completion.claude_runner")
    with pytest.raises(halt.AgentTimeoutError):
        raise runner.AgentTimeoutError("t", cmd=["c"], elapsed_s=1, stdout="", stderr="")


_SWAPPER_ERRORS = ("SwapperError", "ProcessNotFound", "InspectionIndeterminate")


@pytest.mark.parametrize("name", _SWAPPER_ERRORS)
def test_swapper_error_classes_are_one_class_across_copy_and_final_names(name):
    leaf = getattr(_mod("llm_kit.adapters._swapper_errors"), name)
    holders = [f"{_COPY}.swapper", "llm_kit.adapters.swapper"]
    if name != "SwapperError":
        holders += [f"{_COPY}._swapper_process", "llm_kit.adapters._swapper_process"]
    for module in holders:
        assert getattr(_mod(module), name) is leaf, (module, name)


def test_a_copy_swapper_error_is_caught_by_the_final_class():
    leaf = _mod("llm_kit.adapters._swapper_errors")
    copy_swapper = _mod(f"{_COPY}.swapper")
    with pytest.raises(leaf.SwapperError):
        raise copy_swapper.ProcessNotFound("boom")
    assert issubclass(copy_swapper.ProcessNotFound, leaf.SwapperError)


# --------------------------------------------------------------------------
# usage_budget: whole shim over dispatch.usage_budget (readers: adapters.usage_sources)
# --------------------------------------------------------------------------

_USAGE_ROW = _MAP["modules"]["plugins/llm-scripting-kit/lib/llm_scripting_kit/usage_budget.py"]
_READERS = (
    "_HOUR", "_DAY", "_CLAUDE_WINDOW_SECONDS", "CLAUDE_SNAPSHOT", "CODEX_SESSIONS_DIR",
    "_PACE_EPSILON", "_CODEX_TAIL_BYTES", "_CODEX_EXHAUSTION_LATCH_SECONDS", "_RESET_TEXT_RE",
    "_epoch", "_used_percentage", "_verdict", "_load_json", "_read_model_scoped",
    "read_claude_pool", "_newest_codex_rollout", "_CodexRateLimitReading",
    "_last_codex_rate_limits", "_find_rate_limits", "_find_usage_limit_message",
    "_parse_reset_text", "read_codex_pool",
)


@pytest.fixture
def ub():
    return _mod(f"{_COPY}.usage_budget")


@pytest.fixture
def src():
    return _mod("llm_kit.adapters.usage_sources")


def test_usage_budget_is_a_whole_shim_over_dispatch(ub):
    assert _USAGE_ROW["state"] == "shim"
    assert _USAGE_ROW["final"] == "llm_kit.dispatch.usage_budget"
    assert ub is _mod("llm_kit.dispatch.usage_budget")


@pytest.mark.parametrize("name", _READERS)
def test_every_reader_name_of_the_copy_is_the_usage_sources_object(ub, src, name):
    assert getattr(ub, name) is getattr(src, name)


def test_registry_names_of_the_copy_are_the_conserve_objects(ub):
    conserve = _mod("llm_kit.registry.conserve")
    for name in (
        "Budget", "ConserveSpec", "ConserveConfigError", "parse_conserve_usage", "POOL_PRIMARY",
        "POOL_SEVEN_DAY", "POOL_MODEL_SCOPED", "STATUS_AVAILABLE", "STATUS_NO_DATA",
        "STATUS_OUT_OF_QUOTA", "STATUS_UNDER_QUOTA",
    ):
        assert getattr(ub, name) is getattr(conserve, name), name


def test_the_policy_is_defined_in_dispatch_not_in_usage_sources(ub, src):
    for name in (
        "evaluate", "pinned_evaluate", "session_key", "record_observed_halt", "quota_pool_key",
        "VERDICT_CACHE", "_load_cache", "_store_cache",
    ):
        assert name not in vars(src), name
        assert name in vars(ub), name


def test_every_exported_name_resolves(ub):
    for name in ub.__all__:
        getattr(ub, name)


def _rollout(directory: Path, used: float) -> Path:
    path = directory / "rollout.jsonl"
    limits = {"primary": {"used_percent": used, "window_minutes": 10080, "resets_at": NOW + WEEK // 2}}
    event = {"type": "event_msg", "payload": {"type": "token_count", "rate_limits": limits}}
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return path


def test_a_patched_codex_sessions_dir_on_the_copy_reaches_the_policy(ub, src, tmp_path, monkeypatch):
    _rollout(tmp_path, used=80.0)             # 20% left with 50% of the window left: under quota
    spec = ub.ConserveSpec(pool="primary")
    real = src.CODEX_SESSIONS_DIR
    monkeypatch.setattr(ub, "CODEX_SESSIONS_DIR", tmp_path)
    assert src.CODEX_SESSIONS_DIR == tmp_path     # the reader the policy calls reads this
    budget = ub.evaluate(spec, "codex", now=NOW)
    assert budget.status == ub.STATUS_UNDER_QUOTA
    assert budget.pool == "primary"
    monkeypatch.undo()
    assert src.CODEX_SESSIONS_DIR == real and ub.CODEX_SESSIONS_DIR == real


def test_a_patched_claude_snapshot_on_the_copy_reaches_the_policy(ub, src, tmp_path, monkeypatch):
    snapshot = tmp_path / "rate-limits.json"
    limits = {"seven_day": {"used_percentage": 10.0, "resets_at": NOW + WEEK // 2}}
    snapshot.write_text(json.dumps({"rate_limits": limits}), encoding="utf-8")
    real = src.CLAUDE_SNAPSHOT
    monkeypatch.setattr(ub, "CLAUDE_SNAPSHOT", snapshot)
    budget = ub.evaluate(ub.ConserveSpec(pool="seven_day"), "claude", now=NOW)
    assert budget.status == ub.STATUS_AVAILABLE
    monkeypatch.undo()
    assert src.CLAUDE_SNAPSHOT == real


def test_a_patched_read_codex_pool_on_the_copy_reaches_evaluate_and_the_final_backend(ub, src, monkeypatch):
    seen = []

    def fake(spec, *, now=None, sessions_dir=None):
        seen.append(spec)
        return ub.Budget(status=ub.STATUS_OUT_OF_QUOTA, pool=spec.pool, detail="faked")

    monkeypatch.setattr(ub, "read_codex_pool", fake)
    assert src.read_codex_pool is fake            # the final codex backend calls this attribute
    spec = ub.ConserveSpec(pool="seven_day")
    assert ub.evaluate(spec, "codex", now=NOW).detail == "faked"
    assert seen == [spec]
    monkeypatch.undo()
    assert src.read_codex_pool is not fake and ub.read_codex_pool is src.read_codex_pool


def test_a_patched_read_claude_pool_on_the_copy_reaches_evaluate(ub, src, monkeypatch):
    def fake(spec, *, now=None, snapshot=None):
        return ub.Budget(status=ub.STATUS_UNDER_QUOTA, pool=spec.pool, detail="faked")

    monkeypatch.setattr(ub, "read_claude_pool", fake)
    assert ub.evaluate(ub.ConserveSpec(pool="seven_day"), "claude", now=NOW).detail == "faked"


def test_the_observed_halt_latch_reads_the_usage_sources_constant(ub, src, tmp_path, monkeypatch):
    monkeypatch.setattr(ub, "_CODEX_EXHAUSTION_LATCH_SECONDS", 60)
    written = ub.record_observed_halt(
        "sol", ub.ConserveSpec(pool="seven_day"), now=NOW,
        cache_path=tmp_path / "v.json", environ={"CLAUDE_CODE_SESSION_ID": "s"},
    )
    assert written.resets_at == NOW + 60


def _pin_args(ub):
    return ("entry-a", ub.ConserveSpec(pool="seven_day"), "claude")


def test_a_patched_verdict_cache_on_the_copy_reaches_pinned_evaluate(ub, tmp_path, monkeypatch):
    # Legacy suites isolate the verdict cache by patching VERDICT_CACHE through
    # the copy name; the pinned verdict must land in that file, not the real one.
    cache = tmp_path / "usage-verdicts.json"
    snapshot = tmp_path / "rate-limits.json"
    snapshot.write_text(json.dumps({"rate_limits": {"seven_day": {
        "used_percentage": 10.0, "resets_at": NOW + WEEK // 2}}}), encoding="utf-8")
    monkeypatch.setattr(ub, "VERDICT_CACHE", cache)
    monkeypatch.setattr(ub, "CLAUDE_SNAPSHOT", snapshot)
    environ = {"CLAUDE_CODE_SESSION_ID": "verdict-cache-session"}
    first = ub.pinned_evaluate(*_pin_args(ub), now=NOW, environ=environ)
    assert first.status == ub.STATUS_AVAILABLE
    stored = json.loads(cache.read_text(encoding="utf-8"))
    assert stored["session_key"] == "verdict-cache-session" and "entry-a" in stored["verdicts"]
    # The pin holds: with the snapshot gone, the stored verdict is served.
    snapshot.unlink()
    assert ub.pinned_evaluate(*_pin_args(ub), now=NOW, environ=environ).status == ub.STATUS_AVAILABLE
    monkeypatch.undo()
    assert ub.VERDICT_CACHE != cache


def test_patched_cache_helpers_on_the_copy_reach_pinned_evaluate(ub, tmp_path, monkeypatch):
    loaded, stored = [], []

    def fake_load(path, key):
        loaded.append((path, key))
        return {}

    def fake_store(path, key, verdicts):
        stored.append((path, key, dict(verdicts)))

    monkeypatch.setattr(ub, "_load_cache", fake_load)
    monkeypatch.setattr(ub, "_store_cache", fake_store)
    monkeypatch.setattr(ub, "evaluate", lambda spec, harness, *, now=None: ub.Budget(
        status=ub.STATUS_AVAILABLE, pool=spec.pool, detail="faked"))
    cache = tmp_path / "v.json"
    got = ub.pinned_evaluate(*_pin_args(ub), now=NOW, cache_path=cache,
                             environ={"CLAUDE_CODE_SESSION_ID": "s"})
    assert got.detail == "faked"
    assert loaded == [(cache, "s")] and stored and stored[0][0] == cache


def test_other_attributes_still_set_on_the_copy_module_itself(ub, monkeypatch):
    original = ub.VERDICT_CACHE
    monkeypatch.setattr(ub, "VERDICT_CACHE", Path("elsewhere.json"))
    assert vars(ub)["VERDICT_CACHE"] == Path("elsewhere.json")
    monkeypatch.undo()
    assert ub.VERDICT_CACHE == original


def test_an_unknown_attribute_still_raises_attribute_error(ub):
    with pytest.raises(AttributeError):
        ub.no_such_name


def test_dir_lists_the_moved_names(ub):
    assert set(_READERS) <= set(dir(ub))


def test_a_from_import_of_a_moved_name_gets_the_usage_sources_object():
    namespace: dict = {}
    exec(f"from {_COPY}.usage_budget import read_codex_pool, CODEX_SESSIONS_DIR, _epoch", namespace)
    assert namespace["read_codex_pool"] is _mod("llm_kit.adapters.usage_sources").read_codex_pool
    assert _COPY + ".usage_budget" in sys.modules
