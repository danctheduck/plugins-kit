"""Differential parity: llm_kit.schema vs the legacy completion json modules."""

from __future__ import annotations

import dataclasses
import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_LEGACY_LIB = _REPO / "plugins" / "llm-scripting-kit" / "lib"


@pytest.fixture(scope="module")
def legacy():
    sys.path.insert(0, str(_LEGACY_LIB))
    try:
        schema = importlib.import_module("llm_scripting_kit.completion.json_schema")
        repair = importlib.import_module("llm_scripting_kit.completion.json_repair")
    finally:
        sys.path.remove(str(_LEGACY_LIB))
    return schema, repair


@pytest.fixture(scope="module")
def final():
    from llm_kit.schema import json_repair, json_schema

    return json_schema, json_repair


def _outcome(fn, *args, **kwargs):
    try:
        return ("ok", fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - parity compares any exception
        return ("raise", type(exc).__name__, str(exc))


def _norm(res):
    if res[0] == "ok" and dataclasses.is_dataclass(res[1]):
        return ("ok", dataclasses.asdict(res[1]))
    return res


SCHEMAS = [
    {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "string"}},
     "required": ["a"], "additionalProperties": False},
    {"type": "array", "items": {"$ref": "#/$defs/n"}, "$defs": {"n": {"type": "number", "minimum": 0}}},
    {"anyOf": [{"type": "string"}, {"type": "null"}]},
    {"type": "object", "properties": {"x": {"enum": [1, 2, 3]}}},
    {"type": "object", "$ref": "#/$defs/missing"},
    {"$ref": "#/$defs/a", "$defs": {"a": {"$ref": "#/$defs/a"}}},
    {"type": "object", "patternProperties": {"x": {}}},
    {"type": "wat"},
    {"minItems": -1},
    ["not", "a", "mapping"],
]
VALUES = [
    {"a": 1}, {"a": "x"}, {"b": "s"}, {"a": 1, "z": 2}, [1, 2.5, -1], [True],
    None, "s", {"x": 4}, {"x": 2}, 1.0, [],
]
TEXTS = [
    '{"a": 1}', '{"a": 1', '```json\n{"a": 1}\n```', 'x {"a": 1} y', '{"a": 1,}',
    '[1, 2', '{"a" 1}', '{"a: 1}', '', 'null', 5, None, '{"a": 1}}', '[[1]',
    '{"b": "s", "a": 2', '"str', '[1 2]',
]


def test_check_schema_parity(legacy, final):
    for s in SCHEMAS:
        assert _outcome(final[0].check_schema, s) == _outcome(legacy[0].check_schema, s)
    assert _outcome(final[0].check_schema, {}, subset="v9") == _outcome(
        legacy[0].check_schema, {}, subset="v9"
    )


def test_validate_and_conforms_parity(legacy, final):
    for s in SCHEMAS:
        for v in VALUES:
            assert _outcome(final[0].validate, s, v) == _outcome(legacy[0].validate, s, v)
            if isinstance(s, dict):
                assert _outcome(final[0].conforms, s, s, v) == _outcome(
                    legacy[0].conforms, s, s, v
                )
    assert _outcome(final[0].validate, {}, 1, subset="v9") == _outcome(
        legacy[0].validate, {}, 1, subset="v9"
    )


def test_resolve_local_ref_parity(legacy, final):
    root = {"$defs": {"a": {"type": "string"}, "b/c": {}}}
    for ref in ["#/$defs/a", "#/$defs/b~1c", "#/$defs/zz", "#/x", 5, None, "other"]:
        assert _outcome(final[0].resolve_local_ref, root, ref) == _outcome(
            legacy[0].resolve_local_ref, root, ref
        )


def test_repair_parity(legacy, final):
    for s in SCHEMAS[:4]:
        for t in TEXTS:
            a = _norm(_outcome(final[1].repair_json_structure, s, t))
            b = _norm(_outcome(legacy[1].repair_json_structure, s, t))
            assert a == b, (s, t)
    kw = {"max_edits": 1, "max_walks": 5}
    for t in TEXTS:
        assert _norm(_outcome(final[1].repair_json_structure, SCHEMAS[0], t, **kw)) == _norm(
            _outcome(legacy[1].repair_json_structure, SCHEMAS[0], t, **kw)
        )


def test_constants_and_exports_parity(legacy, final):
    for new, old in ((final[0], legacy[0]), (final[1], legacy[1])):
        assert new.__all__ == old.__all__
        for name in old.__all__:
            o, n = getattr(old, name), getattr(new, name)
            if not callable(o):
                assert n == o, name
    assert final[1].to_json if hasattr(final[1], "to_json") else True
    e_new, e_old = final[1].RepairEdit("insert", "]", 3), legacy[1].RepairEdit("insert", "]", 3)
    assert e_new.to_json() == e_old.to_json()


def test_repair_actually_repairs(final):
    r = final[1].repair_json_structure(SCHEMAS[0], '{"a": 1,}')
    assert r.status == final[1].STATUS_REPAIRED
