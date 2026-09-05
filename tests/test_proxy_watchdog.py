"""Proxy health watchdog contract tests (proxy-native redesign §1, defense ③).

The watchdog is a standalone stdlib-only script shipped inside
forget-connect (assets/proxy/), so it loads via importlib like the hook
scripts do. Everything filesystem-shaped runs against tmp_path fixtures —
the real ~/.claude/settings.json and ~/.forget are never read or written.

The two contracts under test:
  * withdraw — N consecutive probe failures remove the settings.json
    override, but only when the current value is the one we wrote, and the
    user's original base URL comes back.
  * rewire — recovery re-installs the override, but only onto the exact
    state the withdrawal left behind; a user-changed value always wins.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

WATCHDOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "packages"
    / "forget-connect"
    / "assets"
    / "proxy"
    / "forget_proxy_watchdog.py"
)

PROXY_URL = "http://127.0.0.1:8377"
GATEWAY = "https://gateway.corp.example/v1"


def _load():
    spec = importlib.util.spec_from_file_location("forget_proxy_watchdog", WATCHDOG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(monkeypatch, tmp_path, *, original=None, settings=None):
    """A wired home: wiring.json present, settings.json carrying our value."""
    forget_home = tmp_path / ".forget"
    (forget_home / "proxy").mkdir(parents=True)
    settings_file = tmp_path / ".claude" / "settings.json"
    settings_file.parent.mkdir(parents=True)
    monkeypatch.setenv("FORGET_HOME", str(forget_home))
    monkeypatch.setenv("FORGET_CLAUDE_SETTINGS", str(settings_file))

    (forget_home / "proxy" / "wiring.json").write_text(
        json.dumps(
            {
                "proxy_url": PROXY_URL,
                "original_base_url": original,
                "upstream": original,
            }
        ),
        encoding="utf-8",
    )
    if settings is None:
        settings = {"env": {"ANTHROPIC_BASE_URL": PROXY_URL, "KEEP": "1"}}
    settings_file.write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )
    return forget_home, settings_file


def _run_ticks(module, monkeypatch, healthy_sequence):
    for healthy in healthy_sequence:
        monkeypatch.setattr(module, "probe", lambda url, timeout=3.0, h=healthy: h)
        assert module.main() == 0


def _settings(settings_file):
    return json.loads(settings_file.read_text(encoding="utf-8"))


def _state(forget_home):
    return json.loads(
        (forget_home / "proxy" / "watchdog-state.json").read_text(encoding="utf-8")
    )


def test_three_consecutive_failures_withdraw_and_restore_the_gateway(monkeypatch, tmp_path):
    module = _load()
    forget_home, settings_file = _fixture(monkeypatch, tmp_path, original=GATEWAY)

    # Two failures: below the threshold, the override must not move.
    _run_ticks(module, monkeypatch, [False, False])
    assert _settings(settings_file)["env"]["ANTHROPIC_BASE_URL"] == PROXY_URL
    assert _state(forget_home)["consecutive_failures"] == 2
    assert not _state(forget_home).get("withdrawn")

    # The third failure withdraws — and restores the chained original.
    _run_ticks(module, monkeypatch, [False])
    settings = _settings(settings_file)
    assert settings["env"]["ANTHROPIC_BASE_URL"] == GATEWAY
    assert settings["env"]["KEEP"] == "1"
    state = _state(forget_home)
    assert state["withdrawn"] is True
    assert state["last_transition"]["action"] == "withdraw"
    assert state["last_transition"]["outcome"] == "withdrawn"


def test_withdraw_without_an_original_removes_key_and_empty_env(monkeypatch, tmp_path):
    module = _load()
    _forget_home, settings_file = _fixture(
        monkeypatch,
        tmp_path,
        original=None,
        settings={"env": {"ANTHROPIC_BASE_URL": PROXY_URL}, "theme": "dark"},
    )
    _run_ticks(module, monkeypatch, [False, False, False])
    settings = _settings(settings_file)
    assert "env" not in settings  # emptied env object disappears entirely
    assert settings["theme"] == "dark"


def test_a_healthy_success_resets_the_failure_counter(monkeypatch, tmp_path):
    module = _load()
    forget_home, settings_file = _fixture(monkeypatch, tmp_path, original=None)
    _run_ticks(module, monkeypatch, [False, False, True, False, False])
    # Never three in a row — the override stays.
    assert _settings(settings_file)["env"]["ANTHROPIC_BASE_URL"] == PROXY_URL
    assert _state(forget_home)["consecutive_failures"] == 2


def test_watchdog_never_touches_a_value_that_is_not_ours(monkeypatch, tmp_path):
    module = _load()
    forget_home, settings_file = _fixture(
        monkeypatch,
        tmp_path,
        original=None,
        settings={"env": {"ANTHROPIC_BASE_URL": "https://their.gateway/v1"}},
    )
    before = settings_file.read_text(encoding="utf-8")
    _run_ticks(module, monkeypatch, [False, False, False])
    assert settings_file.read_text(encoding="utf-8") == before
    assert _state(forget_home)["last_transition"]["outcome"] == "not_ours"


def test_recovery_rewires_exactly_the_state_withdraw_left(monkeypatch, tmp_path):
    module = _load()
    forget_home, settings_file = _fixture(monkeypatch, tmp_path, original=GATEWAY)
    _run_ticks(module, monkeypatch, [False, False, False])
    assert _settings(settings_file)["env"]["ANTHROPIC_BASE_URL"] == GATEWAY

    # The proxy comes back: the override returns, withdrawn clears.
    _run_ticks(module, monkeypatch, [True])
    assert _settings(settings_file)["env"]["ANTHROPIC_BASE_URL"] == PROXY_URL
    state = _state(forget_home)
    assert state["withdrawn"] is False
    assert state["last_transition"]["outcome"] == "rewired"
    assert state["consecutive_failures"] == 0


def test_recovery_defers_to_a_user_changed_value(monkeypatch, tmp_path):
    module = _load()
    forget_home, settings_file = _fixture(monkeypatch, tmp_path, original=GATEWAY)
    _run_ticks(module, monkeypatch, [False, False, False])

    # While the proxy was down the user pointed at their own endpoint.
    settings = _settings(settings_file)
    settings["env"]["ANTHROPIC_BASE_URL"] = "https://users.own.choice/v2"
    settings_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    _run_ticks(module, monkeypatch, [True])
    assert _settings(settings_file)["env"]["ANTHROPIC_BASE_URL"] == "https://users.own.choice/v2"
    assert _state(forget_home)["last_transition"]["outcome"] == "user_changed"


def test_broken_settings_json_is_never_written(monkeypatch, tmp_path):
    module = _load()
    forget_home, settings_file = _fixture(monkeypatch, tmp_path, original=None)
    broken = '{"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8377"'  # truncated
    settings_file.write_text(broken, encoding="utf-8")
    _run_ticks(module, monkeypatch, [False, False, False])
    assert settings_file.read_text(encoding="utf-8") == broken
    state = _state(forget_home)
    assert state["last_transition"]["outcome"] == "broken"
    # A broken file is retried, not abandoned: withdrawn stays false.
    assert not state.get("withdrawn")


def test_unwired_machine_exits_quietly_without_state(monkeypatch, tmp_path):
    module = _load()
    forget_home = tmp_path / ".forget"
    forget_home.mkdir()
    monkeypatch.setenv("FORGET_HOME", str(forget_home))
    monkeypatch.setenv(
        "FORGET_CLAUDE_SETTINGS", str(tmp_path / ".claude" / "settings.json")
    )
    monkeypatch.setattr(
        module, "probe", lambda url, timeout=3.0: (_ for _ in ()).throw(AssertionError)
    )
    assert module.main() == 0
    assert not (forget_home / "proxy" / "watchdog-state.json").exists()


def test_watchdog_asset_carries_no_personal_scope_or_dependencies(monkeypatch):
    content = WATCHDOG_PATH.read_text(encoding="utf-8")
    assert "junghunkim" not in content
    # stdlib-only by contract — a dependency here breaks zero-config installs.
    for forbidden in ("import requests", "import httpx", "import fastapi"):
        assert forbidden not in content
