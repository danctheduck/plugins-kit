"""Tests for bootstrap_lib/plugin_tiers.py -- the pure tier resolver.

The inventory is plain data (a mapping or any object with ref / scope /
project_path / installed), so every case here is built inline: no registry, no
settings file, no subprocess.
"""

from collections import namedtuple

import pytest

from bootstrap_lib import plugin_tiers as tiers
from bootstrap_lib import profiles

REC = "mkt:rec"
NOT_REC = "mkt:norec"
REQ = "mkt:req"
PROJ = "D:/proj"

FakeInstall = namedtuple("FakeInstall", "ref scope project_path installed")


def entry(ref, tier, **extra):
    data = {"ref": ref, "tier": tier, "install": "manual"}
    if tier != "required":
        data["why_install"] = "You will want it for %s." % ref
        data["why_skip"] = "You may not need %s." % ref
    data.update(extra)
    return data


def inst(ref, scope="local", path=PROJ, installed=True):
    return {"ref": ref, "scope": scope, "project_path": path, "installed": installed}


def answer(want, scope=None):
    return {"want": want, "scope": scope}


def resolve(entries, answers=None, inventory=(), **kw):
    return tiers.resolve_plugin_tiers(entries, answers or {}, list(inventory), **kw)


def only(result, ref):
    return [a for a in result.actions if a.ref == ref]


def rewritten(result, ref):
    return next(p for p in result.plugins if p["ref"] == ref)


# ---------------------------------------------------------------------------
# required
# ---------------------------------------------------------------------------


class TestRequired:
    def test_not_installed_is_installed_at_local_scope(self):
        result = resolve([entry(REQ, "required")])
        assert [(a.action, a.scope) for a in only(result, REQ)] == [("install", "local")]
        assert rewritten(result, REQ)["install"] == "auto"
        assert rewritten(result, REQ)["scope"] == "local"
        assert result.questions == ()

    def test_installed_anywhere_is_kept_updated_only(self):
        result = resolve([entry(REQ, "required")], inventory=[inst(REQ, "user", None)])
        assert [a.action for a in only(result, REQ)] == ["none"]
        assert rewritten(result, REQ)["install"] == "manual"

    def test_a_dormant_record_does_not_count_as_installed(self):
        result = resolve([entry(REQ, "required")],
                         inventory=[inst(REQ, "project", PROJ, installed=False)])
        assert [a.action for a in only(result, REQ)] == ["install"]

    def test_enabled_false_is_never_installed(self):
        result = resolve([entry(REQ, "required", enabled=False)])
        action = only(result, REQ)[0]
        assert action.action == "none" and "enabled: false" in action.reason
        assert rewritten(result, REQ)["install"] == "manual"

    def test_the_authored_scope_is_overridden(self):
        result = resolve([entry(REQ, "required", scope="user")])
        assert rewritten(result, REQ)["scope"] == "local"


# ---------------------------------------------------------------------------
# recommended
# ---------------------------------------------------------------------------


class TestRecommended:
    def test_installed_is_kept_updated_and_never_asked(self):
        result = resolve([entry(REC, "recommended")], inventory=[inst(REC, "user", None)])
        assert [a.action for a in only(result, REC)] == ["none"]
        assert result.questions == ()
        assert rewritten(result, REC)["install"] == "manual"

    def test_not_installed_and_unanswered_asks(self):
        result = resolve([entry(REC, "recommended")])
        assert [a.action for a in only(result, REC)] == ["ask"]
        assert [q.ref for q in result.questions] == [REC]
        assert rewritten(result, REC)["install"] == "manual"

    def test_not_installed_and_wanted_installs_without_asking(self):
        result = resolve([entry(REC, "recommended")], {REC: answer(True)})
        assert [(a.action, a.scope) for a in only(result, REC)] == [("install", "local")]
        assert result.questions == ()
        assert rewritten(result, REC)["install"] == "auto"
        assert rewritten(result, REC)["scope"] == "local"

    def test_not_installed_and_declined_does_nothing(self):
        result = resolve([entry(REC, "recommended")], {REC: answer(False)})
        assert [a.action for a in only(result, REC)] == ["none"]
        assert result.questions == ()
        assert rewritten(result, REC)["install"] == "manual"

    def test_wanted_but_disabled_is_not_installed(self):
        result = resolve([entry(REC, "recommended", enabled=False)], {REC: answer(True)})
        assert [a.action for a in only(result, REC)] == ["none"]

    def test_a_hand_removed_wanted_plugin_is_reinstalled(self):
        # The answer survives; the inventory no longer shows an install.
        result = resolve([entry(REC, "recommended")], {REC: answer(True)}, inventory=[])
        assert result.installs and result.installs[0].ref == REC


# ---------------------------------------------------------------------------
# not recommended
# ---------------------------------------------------------------------------


class TestNotRecommended:
    def test_not_installed_does_nothing_and_is_never_asked(self):
        result = resolve([entry(NOT_REC, "not_recommended")])
        assert [a.action for a in only(result, NOT_REC)] == ["none"]
        assert result.questions == ()

    def test_not_installed_stays_quiet_even_with_a_no_answer(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)})
        assert [a.action for a in only(result, NOT_REC)] == ["none"]
        assert result.uninstalls == () and result.unsatisfied == ()

    def test_installed_and_unanswered_asks(self):
        result = resolve([entry(NOT_REC, "not_recommended")],
                         inventory=[inst(NOT_REC)])
        assert [a.action for a in only(result, NOT_REC)] == ["ask"]
        assert [q.ref for q in result.questions] == [NOT_REC]
        assert rewritten(result, NOT_REC)["install"] == "manual"

    def test_installed_and_kept_is_left_alone(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(True)},
                         inventory=[inst(NOT_REC)])
        assert [a.action for a in only(result, NOT_REC)] == ["none"]
        assert result.questions == ()

    def test_installed_and_unwanted_local_install_is_uninstalled(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=[inst(NOT_REC, "local", PROJ)])
        assert [(a.action, a.scope, a.project_path) for a in result.uninstalls] == [
            ("uninstall", "local", PROJ)]
        assert result.unsatisfied == ()
        assert result.questions == ()
        assert rewritten(result, NOT_REC)["install"] == "manual"

    def test_a_hand_reinstall_of_an_unwanted_plugin_is_uninstalled_again(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=[inst(NOT_REC)])
        assert len(result.uninstalls) == 1

    def test_two_local_records_make_one_uninstall(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=[inst(NOT_REC, "local", PROJ),
                                    inst(NOT_REC, "local", PROJ + "/")])
        assert len(result.uninstalls) == 1


class TestUnsatisfiedRemovals:
    def test_a_project_install_is_never_removed_and_never_ok(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=[inst(NOT_REC, "project", PROJ)])
        assert result.uninstalls == ()
        assert [(a.action, a.scope) for a in result.unsatisfied] == [
            ("unsatisfied", "project")]
        assert "shared settings.json" in result.unsatisfied[0].reason

    def test_a_project_install_stays_unsatisfied_even_with_a_user_confirmation(self):
        result = resolve([entry(NOT_REC, "not_recommended")],
                         {NOT_REC: answer(False, "user")},
                         inventory=[inst(NOT_REC, "project", PROJ)])
        assert result.uninstalls == ()
        assert len(result.unsatisfied) == 1

    def test_an_unconfirmed_user_install_is_unsatisfied(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=[inst(NOT_REC, "user", None)])
        assert result.uninstalls == ()
        assert [(a.action, a.scope) for a in result.unsatisfied] == [
            ("unsatisfied", "user")]
        assert "double-check" in result.unsatisfied[0].reason

    def test_a_confirmed_user_install_is_uninstalled(self):
        result = resolve([entry(NOT_REC, "not_recommended")],
                         {NOT_REC: answer(False, "user")},
                         inventory=[inst(NOT_REC, "user", None)])
        assert [(a.action, a.scope) for a in result.uninstalls] == [("uninstall", "user")]
        assert result.unsatisfied == ()

    def test_a_chimera_user_record_and_a_normal_one_make_one_user_uninstall(self):
        result = resolve([entry(NOT_REC, "not_recommended")],
                         {NOT_REC: answer(False, "user")},
                         inventory=[inst(NOT_REC, "user", PROJ),
                                    inst(NOT_REC, "user", None)])
        assert len(result.uninstalls) == 1

    def test_mixed_installs_report_each_target(self):
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=[inst(NOT_REC, "local", PROJ),
                                    inst(NOT_REC, "user", None),
                                    inst(NOT_REC, "project", PROJ)])
        assert [(a.action, a.scope) for a in only(result, NOT_REC)] == [
            ("uninstall", "local"), ("unsatisfied", "user"), ("unsatisfied", "project")]

    def test_the_unsatisfied_state_is_recomputed_not_remembered(self):
        # Same answer, inventory now clean: nothing outstanding.
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=[])
        assert result.unsatisfied == () and result.uninstalls == ()


# ---------------------------------------------------------------------------
# no profile selected, untiered entries
# ---------------------------------------------------------------------------


class TestNoProfile:
    def test_tiers_do_nothing_and_stay_manual(self):
        entries = [entry(REQ, "required"), entry(REC, "recommended"),
                   entry(NOT_REC, "not_recommended")]
        result = resolve(entries, {REC: answer(True), NOT_REC: answer(False)},
                         inventory=[inst(NOT_REC)], profile_active=False)
        assert all(a.action == "none" for a in result.actions)
        assert result.questions == () and result.uninstalls == ()
        assert all(p["install"] == "manual" for p in result.plugins)


class TestUntieredEntries:
    def test_they_pass_through_unchanged_and_in_place(self):
        base = {"ref": "mkt:base", "install": "auto", "scope": "user"}
        result = resolve([base, entry(REC, "recommended")])
        assert result.plugins[0] == base and result.plugins[0] is not base
        assert [a.ref for a in result.actions] == [REC]


# ---------------------------------------------------------------------------
# questions
# ---------------------------------------------------------------------------


class TestQuestions:
    def test_recommended_questions_come_first_then_not_recommended(self):
        entries = [entry(NOT_REC, "not_recommended"), entry(REC, "recommended"),
                   entry("mkt:rec2", "recommended")]
        result = resolve(entries, inventory=[inst(NOT_REC)])
        assert [q.ref for q in result.questions] == [REC, "mkt:rec2", NOT_REC]

    def test_recommended_shows_the_install_reason_first(self):
        q = resolve([entry(REC, "recommended")]).questions[0]
        assert [kind for kind, _ in q.why_lines] == ["why_install", "why_skip"]
        assert q.why_lines[0][1] == q.why_install

    def test_not_recommended_shows_the_skip_reason_first(self):
        q = resolve([entry(NOT_REC, "not_recommended")],
                    inventory=[inst(NOT_REC)]).questions[0]
        assert [kind for kind, _ in q.why_lines] == ["why_skip", "why_install"]
        assert q.why_lines[0][1] == q.why_skip

    def test_a_question_reports_scopes_and_whether_a_user_install_is_involved(self):
        q = resolve([entry(NOT_REC, "not_recommended")],
                    inventory=[inst(NOT_REC, "local"), inst(NOT_REC, "user", None),
                               inst(NOT_REC, "local", PROJ + "/")]).questions[0]
        assert q.scopes == ("local", "user")
        assert q.needs_user_scope_confirm is True

    def test_a_local_only_install_needs_no_user_scope_confirmation(self):
        q = resolve([entry(NOT_REC, "not_recommended")],
                    inventory=[inst(NOT_REC, "local")]).questions[0]
        assert q.needs_user_scope_confirm is False

    def test_a_recommended_question_has_no_scopes(self):
        q = resolve([entry(REC, "recommended")]).questions[0]
        assert q.scopes == () and q.needs_user_scope_confirm is False

    def test_why_lines_are_sanitized_like_descriptions(self):
        e = entry(REC, "recommended", why_install="Fast\n\tand\u2014useful",
                  why_skip="x" * 500)
        q = resolve([e]).questions[0]
        assert q.why_install == "Fast anduseful"
        assert len(q.why_skip) == profiles.WHY_LINE_MAX


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------


class TestInputs:
    def test_an_object_inventory_works_like_a_mapping(self):
        as_object = [FakeInstall(NOT_REC, "local", PROJ, True)]
        result = resolve([entry(NOT_REC, "not_recommended")], {NOT_REC: answer(False)},
                         inventory=as_object)
        assert len(result.uninstalls) == 1

    def test_answers_for_unlisted_plugins_are_ignored(self):
        result = resolve([entry(REC, "recommended")], {"mkt:other": answer(True)})
        assert [a.action for a in only(result, REC)] == ["ask"]

    def test_the_inputs_are_not_mutated(self):
        original = entry(REC, "recommended")
        snapshot = dict(original)
        resolve([original], {REC: answer(True)})
        assert original == snapshot

    @pytest.mark.parametrize("bad", [
        {"ref": REC, "tier": "mandatory", "install": "manual"},
        {"tier": "required", "install": "manual"},
        {"ref": REC, "tier": "recommended", "install": "manual", "why_skip": "s"},
        {"ref": REC, "tier": "not_recommended", "install": "manual",
         "why_install": "i", "why_skip": "\u2014"},
    ])
    def test_a_malformed_tiered_entry_raises(self, bad):
        with pytest.raises(tiers.PluginTierError):
            resolve([bad])

    @pytest.mark.parametrize("bad", [
        {"ref": REC, "scope": "global", "project_path": None, "installed": True},
        {"ref": REC, "scope": "user", "project_path": None, "installed": "yes"},
        {"scope": "user", "project_path": None, "installed": True},
        {"ref": REC, "scope": "user", "project_path": None},
    ])
    def test_a_malformed_inventory_record_raises(self, bad):
        with pytest.raises(tiers.PluginTierError):
            resolve([entry(REC, "recommended")], inventory=[bad])

    @pytest.mark.parametrize("bad", [
        {REC: {"want": "yes"}},
        {REC: {"want": False, "scope": "local"}},
        {REC: True},
    ])
    def test_a_malformed_answer_raises(self, bad):
        with pytest.raises(tiers.PluginTierError):
            resolve([entry(REC, "recommended")], bad)


# ---------------------------------------------------------------------------
# End to end with profiles.resolve_layers
# ---------------------------------------------------------------------------


def _layers(selected, bound):
    project = {
        "profiles": {
            "designer": {"plugins": [entry(REC, "recommended")]},
            "engineer": {"plugins": [entry(NOT_REC, "not_recommended")]},
        },
    }
    local = {"profile": selected}
    if bound:
        local["plugin_choices"] = {
            "profile": bound,
            "answers": {REC: {"want": True, "decided": "2026-10-16"}},
        }
    return [("p.json", "project", project), ("pl.json", "project_local", local)]


class TestWithProfileState:
    def test_bound_answers_drive_the_resolution(self):
        manifest, state = profiles.resolve_layers(_layers("designer", "designer"))
        result = resolve(manifest["plugins"], profiles.answers_by_ref(state),
                         profile_active=state.status == "selected")
        assert [a.action for a in only(result, REC)] == ["install"]

    def test_a_stale_binding_is_ignored_and_the_plugin_is_asked_about_again(self):
        manifest, state = profiles.resolve_layers(_layers("designer", "engineer"))
        assert state.answers_stale is True
        result = resolve(manifest["plugins"], profiles.answers_by_ref(state))
        assert [a.action for a in only(result, REC)] == ["ask"]

    def test_no_selected_profile_leaves_tiers_idle(self):
        manifest, state = profiles.resolve_layers(_layers("unset", "designer"))
        assert state.status == "unselected"
        result = resolve(manifest.get("plugins", []), profiles.answers_by_ref(state),
                         profile_active=state.status == "selected")
        assert result.actions == () and result.questions == ()
