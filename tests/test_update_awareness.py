"""Update awareness: stale installs must not suffer silently.

The 0.3.7/0.5.0 mismatch shipped the bug class this guards against: newer
hooks sent `project`, the older server ate it without a word, and the
project layer looked broken for a day. Three layers, tested here:
mismatch canary (no network), TTL-cached update check (one request per day,
opt-out), and in-band warnings for unknown write arguments.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from pathlib import Path

from forget import updatecheck

HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"


def _load(name: str):
    sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(name, HOOKS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- updatecheck: cache, TTL, opt-out ----------------------------------------

def test_fetch_latest_caches_for_a_day(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGET_HOME", str(tmp_path))
    monkeypatch.delenv("FORGET_UPDATE_CHECK", raising=False)
    calls = []

    class FakeResponse:
        def __enter__(self):
            return io.StringIO(json.dumps({"info": {"version": "0.9.9"}}))

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=0):
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr(updatecheck.urllib.request, "urlopen", fake_urlopen)
    assert updatecheck.fetch_latest() == "0.9.9"
    assert updatecheck.fetch_latest() == "0.9.9"  # served from cache
    assert len(calls) == 1, "second call within the TTL must not hit the network"
    assert updatecheck.read_cached_latest() == "0.9.9"


def test_stale_cache_refreshes_and_optout_blocks(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGET_HOME", str(tmp_path))
    monkeypatch.delenv("FORGET_UPDATE_CHECK", raising=False)
    (tmp_path / "update-check.json").write_text(
        json.dumps({"latest": "0.1.0", "checked_at": time.time() - 90_000}), encoding="utf-8"
    )
    monkeypatch.setattr(
        updatecheck.urllib.request, "urlopen",
        lambda url, timeout=0: (_ for _ in ()).throw(OSError("offline")),
    )
    assert updatecheck.fetch_latest() == ""  # stale + offline → fail-open, no crash
    monkeypatch.setenv("FORGET_UPDATE_CHECK", "off")
    assert updatecheck.fetch_latest() == ""


def test_version_compare_and_line():
    assert updatecheck.is_older("0.3.7", "0.3.8")
    assert not updatecheck.is_older("0.3.10", "0.3.9")  # numeric, not lexicographic
    assert "upgrade" in updatecheck.update_line("0.3.7", "0.3.8")
    assert "(latest)" in updatecheck.update_line("0.3.8", "0.3.8")


# --- hook canary --------------------------------------------------------------

def _capsule_output(monkeypatch, tmp_path, capsys, result_payload: dict) -> str:
    module = _load("forget_sessionstart")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "project_key_for_path", lambda path: None)

    class FakeResponse:
        def read(self):
            return json.dumps({"result": {"content": [{"text": json.dumps(result_payload)}]}}).encode()

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda req, timeout=8: FakeResponse())
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": "/x", "source": "startup", "session_id": "s"})))
    module.main()
    return capsys.readouterr().out


def test_versionless_server_earns_a_warning(monkeypatch, tmp_path, capsys):
    out = _capsule_output(monkeypatch, tmp_path, capsys, {"capsule_text": "현재 목표: x"})
    assert "⚠ 서버가 버전을 안 밝힘" in out and "forget-server upgrade" in out


def test_current_server_is_quiet(monkeypatch, tmp_path, capsys):
    module = _load("forget_sessionstart")
    out = _capsule_output(
        monkeypatch, tmp_path, capsys,
        {"capsule_text": "현재 목표: x", "server_version": module.REQUIRED_SERVER_VERSION},
    )
    assert "⚠" not in out and "[forget 버전]" not in out


def test_version_nag_never_earns_a_lone_injection(monkeypatch, tmp_path, capsys):
    out = _capsule_output(monkeypatch, tmp_path, capsys, {"capsule_text": ""})
    assert out.strip() == ""  # empty capsule stays silent even with a versionless server


# --- in-band warnings for unknown write args ----------------------------------

def test_record_task_state_warns_on_unknown_argument(monkeypatch, tmp_path):
    import os

    from forget import db as app_db
    from forget.db import init_db
    from forget.mcp import call_tool

    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    path = tmp_path / "warn.sqlite3"
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    response = call_tool(
        "record_task_state",
        {"task_id": "t", "status": "in_progress", "summary": "s", "prjoect": "typo"},
        context={"user_id": "u", "client_name": "forget"},
    )
    body = json.loads(response["content"][0]["text"])
    warnings = " ".join(body.get("warnings") or [])
    assert "prjoect" in warnings and "project" in warnings  # named, with the near-miss suggestion
