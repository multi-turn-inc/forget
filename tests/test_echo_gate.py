"""에코 차단기 계약 테스트 (컴파일러 헌장 4.4 — P-C-1b 레인 ②).

계약: ①컴파일된 문면의 에코는 저장 스킵 + gate_log에 compiled_echo 기록
②비-에코는 정상 저장 ③등록부 부재 시 게이트 무동작(순수 상위집합).
실측 병리(시각 규율 124행/5일 재저장)의 재발 방지 봉인.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-echo.sqlite3")

import pytest  # noqa: E402

from forget import compiler  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget.store import add_memories, list_gate_log, list_memory_dicts  # noqa: E402

RULE = ("Always compare full timestamps (YYYY-MM-DD HH:MM) rather than clock "
        "time alone to avoid misinterpreting file ages across days")


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "e.sqlite3"))
    monkeypatch.setattr(compiler, "COMPILED_FORMS_PATH", tmp_path / "compiled_forms.json")
    compiler._forms_cache.update(mtime=None, forms=[], vectors=None)
    init_db()


def _register_rule(tmp_path_forms):
    tmp_path_forms.write_text(json.dumps([
        {"id": "rule-timestamp-discipline", "text": RULE, "compiled_to": "wake-prompt"}
    ]))
    compiler._forms_cache.update(mtime=None, forms=[], vectors=None)


def test_echo_is_skipped_and_gate_logged():
    _register_rule(compiler.COMPILED_FORMS_PATH)
    out = add_memories({"messages": [{"role": "user", "content":
        "When comparing timestamps, always compare full dates (YYYY-MM-DD HH:MM), "
        "never clock time alone — a same-clock different-day file is not an anomaly."}],
        "user_id": "owner-a", "infer": False, "hebbian": False})
    rows = [m for m in list_memory_dicts() if "timestamp" in str(m.get("memory", "")).lower()
            or "compare" in str(m.get("memory", "")).lower()]
    assert rows == []                                   # 에코 저장 안 됨
    log = list_gate_log({"limit": 10})
    reasons = " ".join(str(e.get("reason")) for e in log.get("results", []))
    assert "compiled_echo:rule-timestamp-discipline" in reasons


def test_non_echo_passes():
    _register_rule(compiler.COMPILED_FORMS_PATH)
    add_memories({"messages": [{"role": "user", "content":
        "The team decided to defer billing and Paddle integration to the final stage."}],
        "user_id": "owner-a", "infer": False, "hebbian": False})
    rows = [m for m in list_memory_dicts() if "billing" in str(m.get("memory", "")).lower()
            or "정산" in str(m.get("memory", ""))]
    assert len(rows) >= 1                               # 정상 저장


def test_no_registry_no_gate():
    out = add_memories({"messages": [{"role": "user", "content": RULE}],
                        "user_id": "owner-a", "infer": False, "hebbian": False})
    rows = [m for m in list_memory_dicts()]
    assert len(rows) >= 1                               # 등록부 없으면 통과
