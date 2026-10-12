"""Per-chunk est_tokens: computation, bundle emission, and roster pins."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from bootstrap_lib.code_review import lane_prompts as lp
from bootstrap_lib.code_review import review_profiles as rp
from bootstrap_lib.code_review import token_estimate as te
from bootstrap_lib.code_review.pipeline import assemble_bundle


def _write(path: Path, n: int) -> str:
    path.write_text("x" * n, encoding="ascii")
    return str(path)


def _prompt_bytes(lane: str) -> int:
    p = lp.LANE_PROMPTS[lane]
    return len((p.system + p.user_preamble).encode("utf-8"))


# Shipped defaults, stated independently of the module under test.
SHIPPED = rp.ContextEstimate(bytes_per_token=2.5, lane_base_tokens=35000)
BASE = 35000


def _tokens(n_bytes: int) -> int:
    return math.ceil(n_bytes / 2.5) + BASE


def test_lane_names_cover_every_reviewer_and_validator() -> None:
    assert set(te.lane_names()) == {*lp.LANE_PROMPTS, "validator"}


def test_claude_md_union_counted_once(tmp_path: Path) -> None:
    md = _write(tmp_path / "CLAUDE.md", 3000)
    est = te.estimate_chunk_tokens(900, SHIPPED, [md, md, md], [])
    a = "reviewer_a_claude_md_compliance"
    assert est[a] == _tokens(900 + _prompt_bytes(a) + 3000)
    assert est["validator"] == _tokens(900 + 3000)
    # lanes that do not read the standards omit them
    assert est["reviewer_b_diff_only_bugs"] == _tokens(
        900 + _prompt_bytes("reviewer_b_diff_only_bugs")
    )


def test_reviewer_c_adds_post_images_only(tmp_path: Path) -> None:
    f1 = _write(tmp_path / "a.py", 600)
    f2 = _write(tmp_path / "b.py", 300)
    est = te.estimate_chunk_tokens(100, SHIPPED, [], [f1, f2, str(tmp_path / "deleted.py")])
    c = "reviewer_c_introduced_code"
    assert est[c] == _tokens(100 + _prompt_bytes(c) + 900)
    assert est["validator"] == _tokens(100)


def test_rounds_up() -> None:
    est = te.estimate_chunk_tokens(1, SHIPPED, [], [])
    assert est["validator"] == 1 + BASE


def test_bundle_carries_est_tokens_for_every_chunk(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    _write(root / "CLAUDE.md", 2000)
    a = _write(root / "pkg" / "a.py", 500)
    b = _write(root / "pkg" / "b.py", 700)
    sections = [
        {"identifier": "pkg/a.py", "text": "diff --git a/pkg/a.py b/pkg/a.py\n+aaa\n"},
        {"identifier": "pkg/b.py", "text": "diff --git a/pkg/b.py b/pkg/b.py\n+bbb\n"},
    ]
    core = assemble_bundle(
        preamble="",
        sections=sections,
        files=[
            {"identifier": "pkg/a.py", "local": a},
            {"identifier": "pkg/b.py", "local": b},
        ],
        bundle_dir=tmp_path / "bundle",
        max_chunk_bytes=60,  # forces one file per chunk
        workspace_root=root,
    )
    assert len(core["diff_chunks"]) == 2
    for chunk in core["diff_chunks"]:
        assert set(chunk["est_tokens"]) == set(te.lane_names())
    first = core["diff_chunks"][0]
    # CLAUDE.md governs both files; each chunk counts it once
    # root CLAUDE.md is both auto-loaded (every lane) and governing (validator)
    assert first["est_tokens"]["validator"] == _tokens(first["bytes"] + 2000 + 2000)
    posts = {"pkg/a.py": 500, "pkg/b.py": 700}[first["files"][0]]
    c = "reviewer_c_introduced_code"
    assert first["est_tokens"][c] == _tokens(
        first["bytes"] + _prompt_bytes(c) + posts + 2000
    )


def test_shipped_rosters_pin_haiku_first_for_standards_lanes(tmp_path: Path) -> None:
    config, _ = rp.resolve_config(tmp_path / "project", home=tmp_path / "home")
    config = rp.apply_model_priority(config)
    by_profile = {p["id"]: p for p in config["profiles"]}

    def ids(entries):
        return [(e["id"], e["effort"]) for e in entries]

    a = [("haiku", "low"), ("sonnet", "low"), ("luna", "high")]
    for pid in ("data_only", "code"):
        rev = {r["name"]: r["model"] for r in by_profile[pid]["reviewers"]}
        assert ids(rev["reviewer_a_claude_md_compliance"]) == a
        assert ids(by_profile[pid]["validator_models"]["claude_md"]) == [
            ("haiku", "low"),
            ("sonnet", "low"),
        ]
    do = {r["name"]: r["model"] for r in by_profile["data_only"]["reviewers"]}
    assert ids(do["reviewer_b_diff_only_bugs"]) == a
    assert ids(by_profile["data_only"]["validator_models"]["bug"]) == [
        ("haiku", "low"),
        ("sonnet", "low"),
    ]
    code = {r["name"]: r["model"] for r in by_profile["code"]["reviewers"]}
    assert ids(code["reviewer_b_diff_only_bugs"]) == [("opus", "medium"), ("sol", "medium")]
    assert ids(code["reviewer_c_introduced_code"]) == [("sol", "high"), ("opus", "high")]
    assert ids(by_profile["code"]["validator_models"]["bug"]) == [("opus", "medium")]


def test_measured_reference_lane_estimates_at_or_above_peak(tmp_path: Path) -> None:
    """A reviewer_a haiku lane peaked at 158k tokens for a 62 KB diff with the
    root (114485 B, auto-loaded) and plugins (66618 B) CLAUDE.md read in."""
    root = _write(tmp_path / "root.md", 114485)
    plugins = _write(tmp_path / "plugins.md", 66618)
    est = te.estimate_chunk_tokens(62000, SHIPPED, [root, plugins], [], [root])
    assert est["reviewer_a_claude_md_compliance"] >= 158000


def _bundle_chunk(tmp_path: Path, root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    a = _write(root / "a.py", 100)
    core = assemble_bundle(
        preamble="",
        sections=[{"identifier": "a.py", "text": "diff --git a/a.py b/a.py\n+aaa\n"}],
        files=[{"identifier": "a.py", "local": a}],
        bundle_dir=tmp_path / "bundle",
        max_chunk_bytes=10_000,
        workspace_root=root,
    )
    return core["diff_chunks"][0]


def test_shipped_defaults_used_when_no_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "nohome"))
    chunk = _bundle_chunk(tmp_path, tmp_path / "repo")
    assert chunk["est_tokens"]["validator"] == _tokens(chunk["bytes"])
    assert rp.resolve_context_estimate(tmp_path / "repo", home=tmp_path / "nohome") == SHIPPED


def test_project_layer_override_changes_est_tokens(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "nohome"))
    root = tmp_path / "repo"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "review_profiles.yaml").write_text(
        "context_estimate:\n  lane_base_tokens: 1000\n  bytes_per_token: 4\n",
        encoding="ascii",
    )
    chunk = _bundle_chunk(tmp_path, root)
    assert chunk["est_tokens"]["validator"] == math.ceil(chunk["bytes"] / 4) + 1000


def test_user_layer_override_changes_one_key(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".claude" / "config").mkdir(parents=True)
    (home / ".claude" / "config" / "review_profiles.yaml").write_text(
        "context_estimate:\n  lane_base_tokens: 2000\n", encoding="ascii"
    )
    got = rp.resolve_context_estimate(tmp_path / "repo", home=home)
    assert got == rp.ContextEstimate(bytes_per_token=2.5, lane_base_tokens=2000)


@pytest.mark.parametrize(
    "body",
    [
        "context_estimate:\n  lane_base_tokens: 0\n",
        "context_estimate:\n  bytes_per_token: -1\n",
        "context_estimate:\n  bytes_per_token: abc\n",
        "context_estimate:\n  bytes_per_token: true\n",
        "context_estimate:\n  bogus: 3\n",
        "context_estimate: 5\n",
    ],
)
def test_invalid_context_estimate_raises(tmp_path: Path, body: str) -> None:
    root = tmp_path / "repo"
    (root / ".claude").mkdir(parents=True)
    (root / ".claude" / "review_profiles.yaml").write_text(body, encoding="ascii")
    with pytest.raises(rp.ConfigError):
        rp.resolve_context_estimate(root, home=tmp_path / "home")


def test_render_shows_resolved_estimate_below_profiles(tmp_path: Path) -> None:
    config, prov = rp.resolve_config(tmp_path / "repo", home=tmp_path / "home")
    out = rp.render(rp.apply_model_priority(config), prov)
    table, _, _ = out.partition("\n---\n")
    assert table.rstrip().endswith("lane_base_tokens: 35000")
    assert "bytes_per_token: 2.5" in table
