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


def test_parse_json_tolerates_prose():
    assert T.parse_json('여기 답: {"has": true, "conf": 0.8}') == {"has": True, "conf": 0.8}
    assert T.parse_json("없음") == {}
