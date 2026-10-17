"""llm-kit's custom bootstrap script: the OpenRouter credential check.

``plugins/llm-kit/custom_bootstrap.py`` carries the credential check of the
plugin llm-kit was migrated from (resolve the key, validate it against
``GET /auth/key`` with a hash-and-age cache, report an unmet or rejected key as a
DEFERRED REQUIREMENT, never as a fix-all entry). It deliberately does NOT carry
the legacy ``.env`` migration (the loc-ops key) or the pre-rename data-directory
move: under decision 7 the legacy credential and config locations are the
shared ones, so llm-kit reads them and writes none of them.

Every test runs under a temporary HOME and a fake network. ``USER_ENV_FILE`` is
computed from ``Path.home()`` at import time, so the fixture re-points it in the
three modules that hold it and asserts it landed under ``tmp_path`` before any
test body runs; the transport seam (``llm_kit.adapters.account._get``) is
replaced, and a second guard fails any real ``urlopen``. Each behavior test was
shown to fail with its behavior removed (see the final test class and the
recorded revert checks in the unit report).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import repoint

REPO = repoint.REPO
PLUGIN = REPO / "plugins" / "llm-kit"
SCRIPT = PLUGIN / "custom_bootstrap.py"


def _load_script():
    """The script, loaded by path under a name no other suite uses."""
    spec = importlib.util.spec_from_file_location("llm_kit_custom_bootstrap_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cb = _load_script()

from llm_kit.adapters import account as account_mod  # noqa: E402
from llm_kit.adapters.account import AccountCheckError, AccountStatus  # noqa: E402
from llm_kit.registry import api_key as api_key_mod  # noqa: E402
from llm_kit.registry import constants  # noqa: E402
from llm_kit.registry.env_file import read_env_file, write_env_file  # noqa: E402


class FakeContext:
    """Minimal stand-in for the bootstrap engine's script context."""

    def __init__(self, data_dir, project_dir):
        self.data_dir = str(data_dir)
        self.project_dir = str(project_dir)
        self.failures = []
        self.deferred = []
        self.actions = []
        self.oks = []

    def add_failure(self, failure_type, **kwargs):
        self.failures.append({"type": failure_type, **kwargs})

    def add_deferred_requirement(self, name, **kwargs):
        self.deferred.append({"name": name, **kwargs})

    def log(self, msg):
        self.actions.append(msg)

    def log_ok(self, msg):
        self.oks.append(msg)


class FakeNetwork:
    """The ``_get`` transport seam: canned replies, and a record of every request."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.reply = (json.dumps({"data": {"label": "fake-label"}}).encode("utf-8"), None)

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers)))
        return self.reply

    def http_error(self, code):
        self.reply = (b"", urllib.error.HTTPError("u", code, "x", {}, None))

    def offline(self):
        self.reply = (b"", urllib.error.URLError("offline"))


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A temporary HOME, a redirected user .env, a clean key variable and a fake network."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_BOOTSTRAP_DATA_ROOT", raising=False)
    user_env = home / ".claude" / "plugins" / "data" / "plugins-kit" / "llm-scripting-kit" / ".env"
    monkeypatch.setattr(constants, "USER_ENV_FILE", user_env)
    monkeypatch.setattr(api_key_mod, "USER_ENV_FILE", user_env)
    monkeypatch.setattr(cb, "USER_ENV_FILE", user_env)
    # the fixture's own safety: nothing below may resolve to the real home
    assert str(cb.USER_ENV_FILE).startswith(str(tmp_path))
    assert Path.home() == home

    network = FakeNetwork()
    monkeypatch.setattr(account_mod, "_get", network)

    def real_urlopen(*_a, **_k):
        raise AssertionError("a real network call was attempted")

    monkeypatch.setattr(urllib.request, "urlopen", real_urlopen)

    data_dir = tmp_path / "data"
    project_dir = tmp_path / "project"
    data_dir.mkdir()
    project_dir.mkdir()
    return {
        "user_env": user_env,
        "data_dir": data_dir,
        "project_dir": project_dir,
        "home": home,
        "tmp": tmp_path,
        "network": network,
    }


def _ctx(env):
    return FakeContext(env["data_dir"], env["project_dir"])


def _write_cache_file(data_dir, key, epoch=None):
    """The validation cache: hash line, plus an epoch line unless it is hash-only."""
    cache_file = data_dir / "last_validated.sha256"
    content = hashlib.sha256(key.encode("utf-8")).hexdigest() + "\n"
    if epoch is not None:
        content += f"{int(epoch)}\n"
    cache_file.write_text(content)
    return cache_file


def _ok_status(label="test"):
    return AccountStatus(
        ok=True, label=label, usage=0.0, limit=None, is_free_tier=False,
        rate_limit=None, failure_reason=None, raw=None,
    )


def _fail_status(reason):
    return AccountStatus(
        ok=False, label=None, usage=None, limit=None, is_free_tier=None,
        rate_limit=None, failure_reason=reason, raw=None,
    )


class TestMissingKey:
    def test_no_key_defers_without_escalating(self, env):
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        # The load-bearing assertion: a missing key produces NO fix-all entry,
        # so a session that never calls the API is never prompted about it.
        assert ctx.failures == []
        assert len(ctx.deferred) == 1
        entry = ctx.deferred[0]
        assert entry["name"] == "openrouter_credential"
        set_key = f"{constants.cli_command()} account set-key"
        assert entry["satisfied_by"] == set_key
        assert "fix-all" not in entry["user_msg"]
        assert f"{set_key} --key <THE_KEY>" in entry["agent_msg"]
        assert "openrouter.ai/keys" in entry["agent_msg"]
        assert env["network"].calls == []

    def test_the_ask_names_llm_kit_and_no_legacy_command(self, env):
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        # the credential file keeps its legacy location (decision 7); nothing else may name it
        text = json.dumps(ctx.deferred).replace(json.dumps(str(env["user_env"]))[1:-1], "")
        assert "llm-kit" in text
        assert "llm-scripting-kit" not in text and "llm_scripting_kit" not in text
        # the production venv command, when no data root is redirected
        assert constants.CLI_COMMAND in ctx.deferred[0]["satisfied_by"]

    def test_redirected_session_names_the_redirected_console_script(self, env, monkeypatch):
        monkeypatch.setenv("CLAUDE_BOOTSTRAP_DATA_ROOT", str(env["tmp"] / "data-dev"))
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        entry = ctx.deferred[0]
        redirected = constants.REDIRECTED_CLI_COMMAND
        assert entry["satisfied_by"] == f"{redirected} account set-key"
        assert f"{redirected} account set-key --key <THE_KEY>" in entry["agent_msg"]
        assert constants.CLI_COMMAND not in entry["agent_msg"]

    def test_a_missing_key_is_not_announced_to_the_user(self, env):
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert ctx.actions == []
        assert any("deferred" in m for m in ctx.oks)

    def test_an_engine_without_the_api_stays_silent(self, env):
        """A bootstrap predating add_deferred_requirement must not fall back to add_failure."""
        ctx = _ctx(env)
        ctx.add_deferred_requirement = None
        cb.bootstrap(ctx)
        assert ctx.failures == []


class TestValidKey:
    def test_valid_key_logs_success_and_writes_the_cache(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-good"})
        ctx = _ctx(env)
        cb.bootstrap(ctx)

        assert ctx.failures == [] and ctx.deferred == []
        assert any("fake-label" in m for m in ctx.actions)
        (url, headers), = env["network"].calls
        assert url == f"{constants.BASE_URL}/auth/key"
        assert headers == {"Authorization": "Bearer sk-or-v1-good"}
        lines = (env["data_dir"] / "last_validated.sha256").read_text().split()
        assert len(lines) == 2 and len(lines[0]) == 64 and lines[1].isdigit()
        assert lines[0] == hashlib.sha256(b"sk-or-v1-good").hexdigest()

    def test_the_key_is_read_from_the_project_env_over_the_user_env(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-user"})
        project_env = constants.project_env_file(env["project_dir"])
        write_env_file(project_env, {"OPENROUTER_API_KEY": "sk-or-v1-project"})
        cb.bootstrap(_ctx(env))
        (_, headers), = env["network"].calls
        assert headers["Authorization"] == "Bearer sk-or-v1-project"

    def test_the_key_is_read_from_the_environment_variable(self, env, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-from-env")
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        (_, headers), = env["network"].calls
        assert headers["Authorization"] == "Bearer sk-or-v1-from-env"
        assert any("source=env" in m for m in ctx.actions)

    def test_a_fresh_cache_skips_the_network(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-cached"})
        _write_cache_file(env["data_dir"], "sk-or-v1-cached", epoch=time.time())
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert env["network"].calls == []
        assert ctx.failures == [] and ctx.deferred == []
        assert any("cached" in m for m in ctx.oks)

    def test_a_cache_for_another_key_does_not_skip_the_network(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-new"})
        _write_cache_file(env["data_dir"], "sk-or-v1-old", epoch=time.time())
        cb.bootstrap(_ctx(env))
        assert len(env["network"].calls) == 1


class TestCacheExpiry:
    """A hash-matching cache skips /auth/key only while fresh (about 7 days)."""

    def test_a_stale_cache_revalidates_and_refreshes_the_timestamp(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-old"})
        stale = time.time() - (cb._REVALIDATE_AFTER_SECONDS + 60)
        cache_file = _write_cache_file(env["data_dir"], "sk-or-v1-old", epoch=stale)
        cb.bootstrap(_ctx(env))
        assert len(env["network"].calls) == 1
        assert int(cache_file.read_text().split()[1]) > stale + cb._REVALIDATE_AFTER_SECONDS - 120

    def test_a_stale_cache_redetects_revocation(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-revoked"})
        stale = time.time() - (cb._REVALIDATE_AFTER_SECONDS + 60)
        _write_cache_file(env["data_dir"], "sk-or-v1-revoked", epoch=stale)
        env["network"].http_error(401)
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert len(env["network"].calls) == 1
        assert ctx.failures == [] and len(ctx.deferred) == 1

    def test_a_hash_only_cache_revalidates(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-hashonly"})
        _write_cache_file(env["data_dir"], "sk-or-v1-hashonly", epoch=None)
        cb.bootstrap(_ctx(env))
        assert len(env["network"].calls) == 1

    def test_the_revalidation_age_is_about_seven_days(self):
        assert cb._REVALIDATE_AFTER_SECONDS == 7 * 24 * 60 * 60


class TestRejectedKey:
    def test_401_defers_a_rotation_hint(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-bad"})
        env["network"].http_error(401)
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert ctx.failures == []
        (entry,) = ctx.deferred
        assert "401" in entry["user_msg"] and "rejected" in entry["user_msg"].lower()
        assert f"{constants.cli_command()} account set-key" in entry["agent_msg"]
        assert str(env["user_env"]) in entry["agent_msg"]
        assert not (env["data_dir"] / "last_validated.sha256").exists()

    def test_402_defers_a_credit_hint(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-broke"})
        env["network"].http_error(402)
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert ctx.failures == []
        (entry,) = ctx.deferred
        assert "credit" in entry["user_msg"].lower()
        assert "openrouter.ai/credits" in entry["agent_msg"]
        assert not (env["data_dir"] / "last_validated.sha256").exists()

    def test_an_unreachable_endpoint_does_not_block_and_writes_no_cache(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-ok"})
        env["network"].offline()
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert ctx.failures == [] and ctx.deferred == []
        assert any("validation skipped" in m for m in ctx.actions)
        assert not (env["data_dir"] / "last_validated.sha256").exists()

    def test_an_unexpected_status_does_not_block(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-ok"})
        env["network"].http_error(500)
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert ctx.failures == [] and ctx.deferred == []
        assert any("validation skipped" in m for m in ctx.actions)

    def test_the_status_seam_is_the_module_name(self, env, monkeypatch):
        """The script calls check_account through its own module name (patchable seam)."""
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-x"})
        monkeypatch.setattr(cb, "check_account", lambda key: _fail_status("no_credit"))
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert len(ctx.deferred) == 1 and env["network"].calls == []

    def test_a_transport_error_from_the_seam_is_reported_not_raised(self, env, monkeypatch):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-x"})

        def boom(key):
            raise AccountCheckError("offline")

        monkeypatch.setattr(cb, "check_account", boom)
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert any("validation skipped (offline)" in m for m in ctx.actions)

    def test_an_unwritable_cache_is_logged_not_swallowed(self, env, monkeypatch):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-good"})

        def refuse(self, *a, **k):
            raise OSError("read-only")

        monkeypatch.setattr(Path, "write_text", refuse)
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert any("validation cache not written (read-only)" in m for m in ctx.actions)


class TestNothingIsMigratedOrSeeded:
    """Decision 7: the legacy locations are the shared ones, so llm-kit moves and seeds none."""

    def test_a_loc_ops_env_is_not_migrated(self, env):
        legacy = env["project_dir"] / ".local-data" / "loc" / ".env"
        write_env_file(legacy, {"OPENROUTER_API_KEY": "sk-or-v1-legacy"})
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert not env["user_env"].exists()
        assert read_env_file(legacy) == {"OPENROUTER_API_KEY": "sk-or-v1-legacy"}
        assert len(ctx.deferred) == 1  # no key resolved: the ask is recorded instead
        assert not any("migrated" in m for m in ctx.actions)

    def test_a_pre_rename_data_directory_is_not_moved(self, env):
        old = env["user_env"].parent.parent / "openrouter-kit"
        write_env_file(old / ".env", {"OPENROUTER_API_KEY": "sk-or-v1-old"})
        ctx = _ctx(env)
        cb.bootstrap(ctx)
        assert (old / ".env").is_file()
        assert not env["user_env"].parent.exists()
        assert not any("migrated" in m for m in ctx.actions)

    def test_the_script_writes_only_its_own_cache(self, env):
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-good"})
        before = sorted(p.relative_to(env["tmp"]).as_posix() for p in env["tmp"].rglob("*"))
        cb.bootstrap(_ctx(env))
        after = sorted(p.relative_to(env["tmp"]).as_posix() for p in env["tmp"].rglob("*"))
        assert sorted(set(after) - set(before)) == ["data/last_validated.sha256"]
        assert read_env_file(env["user_env"]) == {"OPENROUTER_API_KEY": "sk-or-v1-good"}

    def test_the_script_source_has_no_migration_or_writer(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for needle in ("write_env_file", "read_env_file", "rename(", "openrouter-kit", ".local-data"):
            assert needle not in source, needle


class TestEngineWiring:
    """The manifest hook loads the script through the engine's own runner."""

    def test_the_manifest_declares_the_script(self):
        manifest = json.loads((PLUGIN / "bootstrap.json").read_text(encoding="utf-8"))
        assert manifest["script"] == {"path": "custom_bootstrap.py", "entry_point": "bootstrap"}
        assert "config" not in manifest, "llm-kit seeds no config layer"
        assert (PLUGIN / manifest["script"]["path"]).is_file()

    def test_the_engine_runs_the_hook_and_publishes_the_deferred_requirement(self, env):
        from bootstrap_lib import engine

        manifest = json.loads((PLUGIN / "bootstrap.json").read_text(encoding="utf-8"))
        actions: list[str] = []
        oks: list[str] = []
        failures = engine._run_script_phase(
            manifest["script"], str(PLUGIN), str(env["data_dir"]), {}, actions, oks,
            "", "llm-kit", str(env["project_dir"]),
        )
        assert failures == []
        assert not any("FAILED" in a for a in actions), actions
        published = json.loads((env["data_dir"] / engine.DEFERRED_REQUIREMENTS_FILENAME).read_text())
        assert published["plugin"] == "llm-kit"
        (entry,) = published["requirements"]
        assert entry["name"] == "openrouter_credential"
        assert entry["satisfied_by"].endswith("account set-key")

    def test_a_satisfied_requirement_stops_being_published(self, env):
        from bootstrap_lib import engine

        manifest = json.loads((PLUGIN / "bootstrap.json").read_text(encoding="utf-8"))
        path = env["data_dir"] / engine.DEFERRED_REQUIREMENTS_FILENAME
        engine._run_script_phase(manifest["script"], str(PLUGIN), str(env["data_dir"]), {}, [], [],
                                 "", "llm-kit", str(env["project_dir"]))
        assert path.is_file()
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-good"})
        engine._run_script_phase(manifest["script"], str(PLUGIN), str(env["data_dir"]), {}, [], [],
                                 "", "llm-kit", str(env["project_dir"]))
        assert not path.exists()


class TestSkillReadsWhereTheEngineWrites:
    """openrouter-account preflights the files bootstrap writes for THIS plugin.

    The engine keys a plugin's data directory by marketplace and plugin name
    (``engine._plugin_data_dir``), so llm-kit's two state files land under
    ``plugins-kit/llm-kit/``. The skill must name those paths, not the legacy
    plugin's data directory, which is shared only for the credential, config,
    verdict and access-log files.
    """

    SKILL = PLUGIN / "skills" / "openrouter-account" / "SKILL.md"
    PREFLIGHT = re.compile(
        r"\$\{CLAUDE_BOOTSTRAP_DATA_ROOT:-\$HOME/\.claude/plugins/data\}/(\S+?/deferred_requirements\.json)"
    )

    def _engine_data_dir(self, env):
        from types import SimpleNamespace

        from bootstrap_lib import engine

        root = env["tmp"] / "plugin-data-root"
        engine_dir = root / "plugins-kit" / "bootstrap"
        engine_dir.mkdir(parents=True)
        info = SimpleNamespace(name="llm-kit", marketplace="plugins-kit")
        return root, Path(engine._plugin_data_dir(str(engine_dir), info))

    def _run(self, env, data_dir):
        from bootstrap_lib import engine

        manifest = json.loads((PLUGIN / "bootstrap.json").read_text(encoding="utf-8"))
        failures = engine._run_script_phase(
            manifest["script"], str(PLUGIN), str(data_dir), {}, [], [],
            "", "llm-kit", str(env["project_dir"]),
        )
        assert failures == []

    def test_the_preflight_path_is_where_the_deferred_requirement_lands(self, env):
        from bootstrap_lib import engine

        root, data_dir = self._engine_data_dir(env)
        self._run(env, data_dir)  # no key -> deferred requirement
        written = data_dir / engine.DEFERRED_REQUIREMENTS_FILENAME
        assert written.is_file()
        named = self.PREFLIGHT.findall(self.SKILL.read_text(encoding="utf-8"))
        assert named, "the skill's preflight step names no deferred_requirements.json path"
        for rel_path in named:
            assert (root / rel_path).resolve() == written.resolve(), rel_path

    def test_the_documented_cache_path_is_where_the_cache_lands(self, env):
        root, data_dir = self._engine_data_dir(env)
        write_env_file(env["user_env"], {"OPENROUTER_API_KEY": "sk-or-v1-good"})
        self._run(env, data_dir)
        written = data_dir / "last_validated.sha256"
        assert written.is_file()
        rel_path = written.relative_to(root).as_posix()
        text = self.SKILL.read_text(encoding="utf-8")
        assert f"~/.claude/plugins/data/{rel_path}`" in text

    def test_the_skill_does_not_send_the_preflight_to_the_legacy_data_dir(self):
        text = self.SKILL.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "deferred_requirements.json" in line or "last_validated.sha256" in line:
                assert "llm-scripting-kit" not in line, line


class TestTheTestsCanFail:
    """The harness itself: a real network call or a real home is refused, not tolerated."""

    def test_a_real_urlopen_is_refused(self, env):
        with pytest.raises(AssertionError, match="real network call"):
            urllib.request.urlopen("http://example.invalid/")

    def test_the_user_env_is_under_the_temporary_home(self, env):
        assert str(env["user_env"]).startswith(str(env["tmp"]))
        assert Path.home() == env["home"]
