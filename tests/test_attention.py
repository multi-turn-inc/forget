"""attention — 전사 읽기·블록 편집·JSON 파싱 계약 (2026-09-07). 모델·원장 호출 없음."""
from __future__ import annotations
import json
from forget import attention as T


def _claude_line(role, content, **kw):
    return json.dumps({"type": role, "message": {"role": role, "content": content}, "timestamp": "2026-09-07T00:00:00Z", **kw}, ensure_ascii=False)


def test_read_turns_skips_tool_results_and_marks_tool_only_turns(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join([
        _claude_line("user", "하네스를 직접 만들자"),
        _claude_line("assistant", [{"type": "tool_use", "name": "Bash", "input": {}}]),
        _claude_line("user", [{"type": "tool_result", "tool_use_id": "x", "content": "ok"}]),
        _claude_line("assistant", [{"type": "text", "text": "알았다."}]),
        _claude_line("user", "요약", isCompactSummary=True),
    ]) + "\n")
    turns, off = T.read_turns(p, 0)
    assert [t["role"] for t in turns] == ["user", "action", "assistant"]
    assert off == p.stat().st_size
    # 이어 읽기: 새 줄만
    with open(p, "a") as f:
        f.write(_claude_line("user", "그래") + "\n")
    more, off2 = T.read_turns(p, off)
    assert [t["text"] for t in more] == ["그래"] and off2 > off


def test_apply_judgement_edits_block_and_caps():
    st = {"block": [{"id": "old", "text": "o", "light": "green"}], "seen": {}}
    cands = [{"id": f"c{i}", "memory": f"m{i}", "trust": {"light": "green"}} for i in range(10)]
    j = {"add": [{"n": i + 1, "why": "w"} for i in range(9)], "drop": ["B1"]}
    r = T.apply_judgement(st, cands, j)
    assert "old" in r["dropped"] and len(st["block"]) == T.BLOCK_MAX
    assert all(c["id"] in st["seen"] for c in cands)


def test_candidates_fills_timing_breakdown(monkeypatch):
    """fast_s 분해: search_s·rerank_s·queries·pool이 timing에 남는다(2026-09-21 · 원장 검색 비용 특정)."""
    calls = []
    monkeypatch.setattr(T, "search", lambda q, limit=40: (calls.append(q), [{"id": "a", "memory": "x"}, {"id": "b", "memory": "y"}])[1])
    monkeypatch.setattr(T.A, "rerank", lambda rs, stats, exclude_machine=False: list(rs))
    st = {"seen": {"b": "t"}, "block": []}
    tail = [{"role": "user", "text": "하네스"}, {"role": "assistant", "text": "응"}]
    timing: dict = {}
    out = T.candidates(tail, st, {}, timing)
    assert [c["id"] for c in out] == ["a"]
    assert set(timing) == {"search_s", "rerank_s", "queries", "pool"}
    assert timing["queries"] == len(calls) and timing["pool"] == 1
    assert timing["search_s"] >= 0 and timing["rerank_s"] >= 0
    # timing 없이도 동작
    assert [c["id"] for c in T.candidates(tail, st, {})] == ["a"]


def test_parse_json_tolerates_prose():
    assert T.parse_json('여기 답: {"has": true, "conf": 0.8}') == {"has": True, "conf": 0.8}
    assert T.parse_json("없음") == {}


def test_tail_offset_starts_at_line_boundary_near_end(tmp_path):
    """소스 전환 시 큰 파일은 끝 tail_bytes 안쪽의 줄 경계부터 읽는다(2026-09-21 · resident.jsonl 480MB 통째 파싱의 처치)."""
    p = tmp_path / "big.jsonl"
    lines = [_claude_line("user", f"m{i}") for i in range(50)]
    p.write_text("\n".join(lines) + "\n")
    size = p.stat().st_size
    # 작은 파일: 처음부터
    assert T.tail_offset(p, tail_bytes=size + 1) == 0
    # 큰 파일: 끝에서 tail_bytes 안쪽, 줄 경계 정렬, 그 뒤 read_turns는 완전한 줄만 낸다
    off = T.tail_offset(p, tail_bytes=300)
    assert 0 < off < size and off >= size - 300
    turns, end = T.read_turns(p, off)
    assert end == size and turns and turns[-1]["text"] == "m49"
    assert all(t["text"].startswith("m") for t in turns)
    # 기본 인자는 호출 시점의 모듈 상수를 본다(tick이 tail_offset(source)로 부르므로)
    saved = T.SWITCH_TAIL_BYTES
    T.SWITCH_TAIL_BYTES = 300
    try:
        assert T.tail_offset(p) == off
    finally:
        T.SWITCH_TAIL_BYTES = saved
    # 없는 파일은 0
    assert T.tail_offset(tmp_path / "nope.jsonl") == 0
