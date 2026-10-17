"""Differential parity: llm_kit.pipeline.core vs the legacy content_pipeline modules.

Each case drives the legacy module and the final package with the same inputs
and compares normalized results, including exception type name and message.
The legacy tree is imported under a sys.path insert scoped to the fixture.
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LEGACY_LIB = REPO / "plugins" / "content-pipeline-kit" / "lib"

# legacy module (under content_pipeline) -> final module (under llm_kit.pipeline.core)
PAIRS = {
    "freshness.seed": "seed",
    "llm.convergence": "convergence",
    "pipeline.cell_policy": "cell_policy",
    "pipeline.convergence_loop": "convergence_loop",
    "pipeline.gate": "gate",
    "pipeline.single_pass": "single_pass",
    "pipeline.stage": "stage",
    "pipeline.workunit": "workunit",
    "validate.contract": "validate.contract",
    "validate.floor_guard": "validate.floor_guard",
    "validate.riders": "validate.riders",
    "vcs.seam": "vcs_seam",
}


@pytest.fixture(scope="module")
def mods():
    """{legacy key: (legacy_module, final_module)}; legacy import scoped here."""
    saved_path = list(sys.path)
    before = set(sys.modules)
    sys.path.insert(0, str(LEGACY_LIB))
    try:
        out = {}
        for legacy, final in PAIRS.items():
            out[legacy] = (
                importlib.import_module("content_pipeline." + legacy),
                importlib.import_module("llm_kit.pipeline.core." + final),
            )
        yield out
    finally:
        sys.path[:] = saved_path
        for name in set(sys.modules) - before:
            if name == "content_pipeline" or name.startswith("content_pipeline."):
                del sys.modules[name]


def norm(x):
    """Reduce results to plain comparable structures (legacy/final classes differ)."""
    if isinstance(x, enum.Enum):
        return ("enum", type(x).__name__, x.value)
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return (
            "dc",
            type(x).__name__,
            {f.name: norm(getattr(x, f.name)) for f in dataclasses.fields(x)},
        )
    if isinstance(x, BaseException):
        return ("exc", type(x).__name__, str(x))
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return type(x)(norm(v) for v in x)
    return x


def call(fn, *a, **kw):
    """Result or the exception's type name and message."""
    try:
        return ("ok", norm(fn(*a, **kw)))
    except Exception as exc:  # noqa: BLE001 - parity compares the exception itself
        return ("raised", type(exc).__name__, str(exc))


def test_surface_matches(mods):
    for key, (legacy, final) in mods.items():
        if hasattr(legacy, "__all__"):
            assert list(legacy.__all__) == list(final.__all__), key
        else:
            def own(m):
                return {
                    n
                    for n in dir(m)
                    if not n.startswith("__")
                    and getattr(getattr(m, n), "__module__", "") == m.__name__
                }

            assert own(legacy) == own(final), key


def test_seed(mods):
    legacy, final = mods["freshness.seed"]
    for args, kw in [
        (("abc",), {}),
        (("abc", "salt"), {}),
        (("abc",), {"bits": 32}),
        (("",), {"bits": 4}),
        (("abc",), {"bits": 0}),
        (("abc",), {"bits": 7}),
        (("unit-\u00e9",), {"bits": 128}),
    ]:
        assert call(legacy.deterministic_seed, *args, **kw) == call(
            final.deterministic_seed, *args, **kw
        )
    for salt in ("", "s"):
        a = [legacy.seeded_random("id", salt).random() for _ in range(5)]
        b = [final.seeded_random("id", salt).random() for _ in range(5)]
        assert a == b
    sl, sf = mods["pipeline.single_pass"]
    for kw in ({}, {"salt": "x"}):
        assert call(sl.seed_for, "u1", **kw) == call(sf.seed_for, "u1", **kw)
    assert sf.seed_for("u2", salt="q") == final.deterministic_seed("u2", "q")


def _rounds(mod):
    R = mod.Round
    return [
        [],
        [R(0, 0)],
        [R(0, 0, failed=1)],
        [R(3, 2), R(0, 2), R(0, 2)],
        [R(3, 2), R(1, 2), R(0, 0)],
        [R(1, 1), R(0, 0), R(0, 0)],
        [R(0, 0, total=0)],
        [R(2, 5, total=9, detail={"k": 1})],
    ]


def test_convergence(mods):
    legacy, final = mods["llm.convergence"]
    for lh, fh in zip(_rounds(legacy), _rounds(final)):
        for kw in [
            {},
            {"stall_window": None},
            {"stall_window": 1},
            {"converge_window": 2},
            {"stall_window": 3, "converge_window": 2},
        ]:
            assert call(legacy.evaluate, lh, **kw) == call(final.evaluate, fh, **kw)
        for ev in [
            {},
            {"empty_is_converged": False},
            {"stall_window": 0},
            {"converge_window": 0},
        ]:
            lv = call(lambda: legacy.ProgressEvaluator(**ev).evaluate(lh))
            fv = call(lambda: final.ProgressEvaluator(**ev).evaluate(fh))
            assert lv == fv
    assert norm(legacy.Round(1, 2)) == norm(final.Round(1, 2))
    assert final.Round(1, 2, total=5) == final.Round(1, 2)
    assert [v.value for v in legacy.Verdict] == [v.value for v in final.Verdict]
    assert isinstance(final.ProgressEvaluator(), final.ConvergenceGate)
    with pytest.raises(dataclasses.FrozenInstanceError):
        final.ProgressEvaluator().stall_window = 5


def test_cell_policy(mods):
    legacy, final = mods["pipeline.cell_policy"]

    def make(mod):
        table = {
            "o": mod.CellOutcome.OPEN,
            "l": mod.CellOutcome.LOCKED,
            "t": mod.CellOutcome.TERMINAL,
            "f": mod.CellOutcome.FAILED,
            "s": "locked",
        }

        class P:
            def outcome(self, cell):
                return table[cell]

        return P()

    for cells in ("oolltf", "", "lll", "ls", "x"):
        assert call(legacy.tally, cells, make(legacy)) == call(final.tally, cells, make(final))
    lm = legacy.measure_from(lambda s: s, make(legacy), lambda s: {"n": len(s)})
    fm = final.measure_from(lambda s: s, make(final), lambda s: {"n": len(s)})
    for store in ("oo", "ol", "llo", "", "lt"):
        assert norm(lm(store)) == norm(fm(store))
    t0 = legacy.Tally(4, 1, 1, 1, 1), final.Tally(4, 1, 1, 1, 1)
    t1 = legacy.Tally(4, 0, 3, 1, 0), final.Tally(4, 0, 3, 1, 0)
    assert norm(t1[0].to_round(t0[0])) == norm(t1[1].to_round(t0[1]))
    assert norm(t1[0].to_round()) == norm(t1[1].to_round())
    assert norm(t0[0].to_round(t1[0])) == norm(t0[1].to_round(t1[1]))


def test_workunit(mods):
    wl, wf = mods["pipeline.workunit"]

    def sel(s):
        return list(s.items())

    for size in (0, 1, 2, 5, -1):
        for store in ({}, {"a": 1}, {"a": 1, "b": 2, "c": 3}):
            assert call(lambda: wl.FlatChunkStrategy(sel, size).chunks(store)) == call(
                lambda: wf.FlatChunkStrategy(sel, size).chunks(store)
            )
            assert call(lambda: wl.FlatChunkStrategy(sel, size).units(store)) == call(
                lambda: wf.FlatChunkStrategy(sel, size).units(store)
            )

    def order(s):
        return s["order"]

    cases = [
        {},
        {"payload_of": lambda s, n: n.upper()},
        {"predecessors_of": lambda s, n: [x for x in s["order"] if str(x) < n]},
        {
            "context_of": lambda s, n, w: {"seen": [u.id for u in w]},
            "predecessors_of": lambda s, n: ["ignored"],
        },
    ]
    for store in ({"order": []}, {"order": ["a", 2, "c"]}, {}):
        for kw in cases:
            assert call(lambda: wl.GraphWalkStrategy(order, **kw).units(store)) == call(
                lambda: wf.GraphWalkStrategy(order, **kw).units(store)
            )


def test_gate_stage_single_pass(mods):
    wl, wf = mods["pipeline.workunit"]
    gl, gf = mods["pipeline.gate"]

    preds = [lambda u: None, lambda u: "bad" if u.id == "x" else None, lambda u: "late"]

    def gates(mod):
        return [
            mod.Gate("a", preds[0]),
            mod.Gate("b", preds[1], sticky=True),
            mod.Gate("c", preds[2]),
        ]

    for uid in ("x", "y"):
        assert call(gl.run_gates, gates(gl), wl.WorkUnit(uid)) == call(
            gf.run_gates, gates(gf), wf.WorkUnit(uid)
        )
    assert call(gl.run_gates, [], wl.WorkUnit("x")) == call(gf.run_gates, [], wf.WorkUnit("x"))

    def boom(u):
        return 1 / 0

    assert call(gl.run_gates, [gl.Gate("z", boom)], wl.WorkUnit("x")) == call(
        gf.run_gates, [gf.Gate("z", boom)], wf.WorkUnit("x")
    )

    sl, sf = mods["pipeline.stage"]
    stages = [lambda s, c: s + [c], lambda s, c: None, lambda s, c: s + ["z"]]
    for ctx in (None, 7):
        assert call(sl.compose, [], stages, ctx) == call(sf.compose, [], stages, ctx)
    assert call(sl.compose, 1, [boom]) == call(sf.compose, 1, [boom])

    pl, pf = mods["pipeline.single_pass"]
    for st in ([lambda s, c: s + [c]], 5):
        assert call(pl.run, [], st) == call(pf.run, [], st)
    assert pl.__all__ == pf.__all__
    assert pf.Gate is gf.Gate and pf.run_gates is gf.run_gates


def _loop_trace(mod_loop, mod_conv, gate_kind, script, max_cycles, fail_stage=None, **kw):
    events = []

    def observer(e):
        events.append(
            (
                e.kind.value,
                e.cycle,
                e.stage,
                norm(e.round),
                norm(e.verdict),
                None if e.error is None else (type(e.error).__name__, str(e.error)),
                norm(e.result),
            )
        )

    seq = iter(script)
    last = [None]

    def measure(store):
        last[0] = next(seq, last[0])
        v = last[0]
        return v if isinstance(v, tuple) else mod_conv.Round(**v)

    def stage(name):
        def fn(store, cycle):
            if name == fail_stage:
                raise RuntimeError(f"{name} failed at {cycle}")
            store = list(store)
            store.append((name, cycle))
            return store if name != "select" else None

        return fn

    gate = None
    if gate_kind == "strict":
        gate = mod_conv.ProgressEvaluator(stall_window=1, converge_window=2)
    try:
        res = mod_loop.run(
            [],
            grade=stage("grade"),
            select=stage("select"),
            apply=stage("apply"),
            fill=stage("fill"),
            measure=measure,
            max_cycles=max_cycles,
            gate=gate,
            observers=[observer],
            **kw,
        )
    except Exception as exc:  # noqa: BLE001
        return ("raised", type(exc).__name__, str(exc)), events
    return (
        norm(res.store),
        norm(res.verdict),
        norm(res.history),
        res.cycles_run,
        [(c.cycle, norm(c.verdict), norm(c.round), sorted(c.stage_seconds)) for c in res.cycles],
        res.converged,
        res.stalled,
        res.failed,
    ), events


def test_convergence_loop(mods):
    ll, lf = mods["pipeline.convergence_loop"]
    cl, cf = mods["llm.convergence"]
    scripts = {
        "converge": [(0, 2), (2, 1), (1, 0)],
        "stall": [(0, 3), (0, 3), (0, 3), (0, 3)],
        "already": [(0, 0)],
        "failed_pre": [{"produced": 0, "outstanding": 0, "failed": 2}],
        "round_objs": [
            {"produced": 1, "outstanding": 2, "total": 3},
            {"produced": 1, "outstanding": 0, "failed": 1},
        ],
        "slow": [(0, 5), (1, 4), (1, 3), (1, 2)],
    }
    for name, script in scripts.items():
        for gate_kind in ("default", "strict"):
            for mc in (0, 1, 3):
                for kw in ({}, {"start_cycle": 5}):
                    l = _loop_trace(ll, cl, gate_kind, script, mc, **kw)
                    f = _loop_trace(lf, cf, gate_kind, script, mc, **kw)
                    assert l == f, (name, gate_kind, mc, kw)
    for fs in ("grade", "select", "apply", "fill"):
        l = _loop_trace(ll, cl, "default", scripts["slow"], 3, fail_stage=fs)
        f = _loop_trace(lf, cf, "default", scripts["slow"], 3, fail_stage=fs)
        assert l == f
        assert l[0][0] == "raised" and l[1][-1][0] == "stage_failed"
    neg = dict(measure=lambda s: (0, 1), max_cycles=-1)
    assert call(ll.run, [], **neg) == call(lf.run, [], **neg)
    assert ll.STAGES == lf.STAGES

    def bad_obs(e):
        if e.kind.value == "stage_failed":
            raise KeyError("obs")

    outs = []
    for mod in (ll, lf):
        r = mod.run_cycle([], 3, grade=None, select=None, apply=None, fill=None,
                          measure=lambda s: (1, 2))
        outs.append((r.cycle, r.round.produced, r.round.outstanding, r.verdict.value))
        try:
            mod.run_cycle([], 1, grade=lambda s, c: 1 / 0, select=None, apply=None,
                          fill=None, measure=lambda s: (0, 1), observers=[bad_obs])
        except ZeroDivisionError as exc:
            outs.append((str(exc), type(exc.__cause__).__name__))
    assert outs[:2] == outs[2:]
    assert outs[1] == ("division by zero", "KeyError")


def test_contract_riders_floor_guard(mods):
    cl, cf = mods["validate.contract"]
    rl, rf = mods["validate.riders"]
    gl, gf = mods["validate.floor_guard"]

    def rejs(mod):
        S = mod.Severity
        return [
            mod.Rejection("b", S.SOFT, "soft b"),
            mod.Rejection("a", S.HARD, "hard a", rule_id="r1", payload={"w": 3}),
            mod.Rejection("a", S.ADVISORY, "adv a"),
            mod.Rejection("c"),
        ]

    lr, fr = rejs(cl), rejs(cf)
    assert [v.value for v in cl.Severity] == [v.value for v in cf.Severity]
    for kw in ({}, {"block_soft": False}):
        assert [cl.blocks(r, **kw) for r in lr] == [cf.blocks(r, **kw) for r in fr]
        assert cl.is_rejecting(lr, **kw) == cf.is_rejecting(fr, **kw)
        assert cl.is_rejecting([], **kw) == cf.is_rejecting([], **kw)
        assert call(cl.assert_valid, lr, **kw) == call(cf.assert_valid, fr, **kw)
        for sl_ in (slice(None), slice(2, 3), slice(0, 0)):
            assert call(cl.format_rejections, lr[sl_], **kw) == call(
                cf.format_rejections, fr[sl_], **kw
            )
    custom = dict(valid_token="OK", header="H")
    assert call(cl.format_rejections, [], **custom) == call(cf.format_rejections, [], **custom)
    assert call(cl.format_rejections, lr, **custom) == call(cf.format_rejections, fr, **custom)

    msgs = []
    for mod, rs in ((cl, lr), (cf, fr)):
        try:
            mod.assert_valid(rs)
        except mod.ValidationError as e:
            msgs.append((str(e), [r.kind for r in e.rejections]))
    assert len(msgs) == 2 and msgs[0] == msgs[1]

    def validators(mod):
        S = mod.Severity
        return [
            lambda c, x: [mod.Rejection("z", S.HARD, f"{c}-{x}")],
            lambda c, x: [],
            lambda c, x: [mod.Rejection("a", S.SOFT, "second"), mod.Rejection("a", S.SOFT, "first")],
        ]

    assert call(cl.run_rules, "cand", 1, validators(cl)) == call(
        cf.run_rules, "cand", 1, validators(cf)
    )
    assert call(cl.run_rules, "cand", 1, []) == call(cf.run_rules, "cand", 1, [])
    assert call(cl.run_rules, "c", 1, [lambda c, x: 1 / 0]) == call(
        cf.run_rules, "c", 1, [lambda c, x: 1 / 0]
    )

    riders = {"len": lambda v, c: len(v), "ctx": lambda v, c: c}
    assert call(rl.compute_riders, "abc", 9, riders) == call(rf.compute_riders, "abc", 9, riders)
    for kind in ("a", "b", "none"):
        assert call(rl.rider_from_kind, lr, kind) == call(rf.rider_from_kind, fr, kind)
    assert call(rl.facts_from_rejections, lr, ["a", "b", "q"]) == call(
        rf.facts_from_rejections, fr, ["a", "b", "q"]
    )

    @dataclasses.dataclass
    class Cand:
        text: str
        riders: dict = dataclasses.field(default_factory=dict)

    @dataclasses.dataclass
    class NoRiders:
        text: str

    for cand in (
        {"t": 1},
        {"t": 1, "riders": {"a": 1, "b": 2}},
        Cand("x"),
        Cand("x", {"a": 1}),
        NoRiders("x"),
        "str",
        None,
    ):
        assert call(rl.attach_riders, cand, {"b": 3}) == call(rf.attach_riders, cand, {"b": 3})
        assert call(rl.cached_riders, cand) == call(rf.cached_riders, cand)

    guards = {
        "even": lambda x: x % 2 == 0,
        "never": lambda x: False,
        "big": lambda x: x > 5,
        "boom": lambda x: 1 / 0,
    }
    for corpus in ([], [1], [1, 3, 5, 7, 9, 11, 13, 15, 17, 19], list(range(10)), [2] * 3):
        for g in guards.values():
            assert call(gl.corpus_flag_rate, g, corpus) == call(gf.corpus_flag_rate, g, corpus)
            for kw in ({}, {"name": "n", "threshold": 0.5}, {"threshold": 0.0}):
                assert call(gl.evaluate_guard, g, iter(corpus), **kw) == call(
                    gf.evaluate_guard, g, iter(corpus), **kw
                )
            assert call(gl.flag, g, corpus) == call(gf.flag, g, corpus)
        assert call(gl.evaluate_guards, guards, corpus) == call(gf.evaluate_guards, guards, corpus)
    assert gl.DEFAULT_THRESHOLD == gf.DEFAULT_THRESHOLD


def test_vcs_seam(mods):
    vl, vf = mods["vcs.seam"]

    def names(m):
        return sorted(n for n in vars(m.VcsBackend) if not n.startswith("_"))

    assert names(vl) == names(vf) == [
        "add",
        "delete_if_empty",
        "finalize_description",
        "make_changeset",
        "move_into",
        "open_for_edit",
        "revert",
    ]
