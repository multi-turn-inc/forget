"""B층 훅 고정 — 캡처·파싱·폴백·원자성·주입 렌더 (P39 처분의 구현).

훅 파일은 패키지 밖이라 경로 직접 적재. LLM은 건드리지 않는다 —
여기서 고정하는 것은 판단 없는 기계 부품들이다.
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))

spec = importlib.util.spec_from_file_location("forget_bstate", ROOT / "hooks" / "forget_bstate.py")
bstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bstate)


def _transcript(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    return str(p)


def test_extract_dialogue_filters_noise_and_tool_results(tmp_path):
    rows = [
        {"type": "user", "message": {"content": "B층 정식 구현 ㄱㄱ"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "설계부터 간다."}]}},
        {"type": "user", "message": {"content": "[{\"tool_use_id\": \"x\"}]"}},          # 도구 결과
        {"type": "user", "message": {"content": "[SYSTEM NOTIFICATION - NOT USER INPUT] 자동 알림"}},  # 오염
        {"type": "user", "message": {"content": "결과 몇분남았어?\n[forget 회상 — 힌트]"}},   # 꼬리 절단
    ]
    turns = bstate.extract_dialogue(_transcript(tmp_path, rows))
    assert ("user", "B층 정식 구현 ㄱㄱ") in turns
    assert ("assistant", "설계부터 간다.") in turns
    assert ("user", "결과 몇분남았어?") in turns
    assert all("SYSTEM NOTIFICATION" not in t for _, t in turns)
    assert all(not t.startswith("[{") for _, t in turns)


def test_parse_chunks_lenient():
    out = bstate.parse_chunks("목표: B층 구현\n직전 사건: P39 지지\n미결: persona 재판정\n다음 손: 훅 등록")
    assert out["목표"] == "B층 구현"
    assert out["다음 손"] == "훅 등록"
    assert len(bstate.parse_chunks("아무 형식 없음")) == 0


def test_structural_fallback_never_empty():
    turns = [("assistant", "게이트 판정 보고"), ("user", "재실험 돌려줘")]
    chunks = bstate.structural_state(turns)
    assert chunks["목표"] == "재실험 돌려줘"
    assert chunks["_engine"] == "structural-fallback"
    assert all(chunks[k] for k in bstate.CHUNK_KEYS)


def test_write_load_render_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(bstate, "BSTATE_DIR", str(tmp_path))
    bstate.write_state("proj-x", {"목표": "A", "직전 사건": "B", "미결": "C", "다음 손": "D",
                                  "_engine": "test"}, "/tmp/t.jsonl", "SessionEnd")
    state = bstate.load_state("proj-x")
    assert state["chunks"]["목표"] == "A" and state["engine"] == "test"
    block = bstate.render_block(state)
    assert block.startswith("[B층 — 마지막 작업 상태")
    assert "목표: A" in block and "다음 손: D" in block
    assert "⚠오래됨" not in block  # 방금 캡처 — 신선
    # 이력 append 확인
    hist = (tmp_path / "proj-x.history.jsonl").read_text().strip().splitlines()
    assert len(hist) == 1


def test_render_marks_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(bstate, "BSTATE_DIR", str(tmp_path))
    old = time.strftime("%FT%T%z", time.localtime(time.time() - 3 * 24 * 3600))
    state = {"captured_at": old, "event": "Stop",
             "chunks": {"목표": "x", "직전 사건": "", "미결": "", "다음 손": ""}}
    assert "⚠오래됨" in bstate.render_block(state)


def test_atomic_write_leaves_no_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(bstate, "BSTATE_DIR", str(tmp_path))
    bstate.write_state("p", {"목표": "a", "_engine": "t"}, "/tmp/t.jsonl", "Stop")
    assert not list(tmp_path.glob("*.tmp"))
