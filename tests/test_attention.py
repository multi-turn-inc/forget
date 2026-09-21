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


def test_read_turns_drops_harness_injected_user_lines(tmp_path):
    # 2026-09-21 DILABv2 실측: Claude Code가 user role로 적는 기계 줄(<task-notification>·usage limit reset·
    # <local-command-*>·<bash-input>)이 «정훈의 마지막 말»로 읽혀 검색 질의가 됐다 — 주차 법인 기억 적중 0.
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join([
        _claude_line("user", "답글 왔나"),
        _claude_line("user", "<task-notification>\n<task-id>bpgvz5pmg</task-id>\n</task-notification>"),
        _claude_line("user", "Your claude.ai usage limit has reset. Continue the task you were working on."),
        _claude_line("user", "<local-command-stdout>Set model to opus</local-command-stdout>"),
        _claude_line("user", "<command-name>/model</command-name>"),
        _claude_line("user", "<bash-input>ls</bash-input>"),
        _claude_line("user", [{"type": "text", "text": "<system-reminder>x</system-reminder>"}]),
        _claude_line("user", "그건 내가 정하는거야. 일단 남주 주면 돼."),
    ]) + "\n")
    turns, _ = T.read_turns(p, 0)
    assert [t["text"] for t in turns] == ["답글 왔나", "그건 내가 정하는거야. 일단 남주 주면 돼."]
    # 사람 말이 태그처럼 보여도 등록된 하네스 태그가 아니면 남긴다
    assert not T._injected_user("<b>굵게</b> 이건 사람 말")


def test_load_state_scrubs_injected_lines_from_persisted_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ATTN_DIR", tmp_path)
    (tmp_path / "state.json").write_text(json.dumps({"source": "s", "offset": 9, "tail": [
        {"role": "user", "text": "답글 왔나", "ts": "t"},
        {"role": "user", "text": "Your claude.ai usage limit has reset. Continue", "ts": "t"},
        {"role": "assistant", "text": "초안입니다", "ts": "t"},
    ], "block": [], "seen": {}, "injected": [], "ticks": 0, "actions_since_judge": 0}, ensure_ascii=False))
    st = T.load_state()
    assert [t["text"] for t in st["tail"]] == ["답글 왔나", "초안입니다"]
    assert st["offset"] == 9


def test_entity_query_pulls_names_numbers_and_latin_tokens():
    # 2026-09-21 DILABv2 실측: 문장 질의 6종이 놓친 이명범·김남주 5080(9/3)·공단 VPN(9/17) green이 이 질의로 3/3 적중.
    tail = [
        {"role": "user", "text": "그건 내가 정하는거야. 한대만 온거야? 그러면 일단 남주 주면 돼."},
        {"role": "assistant", "text": "남주님, 5080은 남주님이 쓰시면 됩니다. CUDA 12.8 기준. 이명범 님 답글은 소장님이 직접. Your turn, KST 2026"},
    ]
    q = T.entity_query(tail)
    toks = q.split()
    assert "남주" in toks and "이명범" in toks and "5080" in toks and "CUDA" in toks
    assert toks[0] == "남주"                       # 빈도순
    for stop in ("Your", "KST", "2026"):
        assert stop not in toks
    assert T.entity_query([{"role": "user", "text": "응 보내줘"}]) == ""
    # 경로·URL 어절은 엔티티가 아니다(2026-09-21 06:19Z: Users Library Mobile Documents CloudDocs가 질의에 들어감)
    q2 = T.entity_query([{"role": "user", "text": "/Users/junghunkim/Library/Mobile\\ Documents/com\\~apple\\~CloudDocs/에이닷/01046776904_20260921_145045.txt 이것좀 처리해줘 https://forms.gle/Abc123 이명범 님"}])
    toks2 = q2.split()
    assert "이명범" in toks2
    for noise in ("Users", "Library", "Mobile", "Documents", "CloudDocs", "Abc123", "145045"):
        assert noise not in toks2


def test_candidates_adds_entity_query_when_present(monkeypatch):
    calls = []
    monkeypatch.setattr(T, "search", lambda q, limit=40: (calls.append(q), [])[1])
    monkeypatch.setattr(T.A, "rerank", lambda rs, stats, exclude_machine=False: list(rs))
    st = {"seen": {}, "block": []}
    tail = [{"role": "user", "text": "답글 왔나"}, {"role": "assistant", "text": "이명범 님 답글은 아직. 5080은 남주님 몫."}]
    timing: dict = {}
    T.candidates(tail, st, {}, timing)
    assert timing["queries"] == 3 and any("이명범" in q and "5080" in q for q in calls)


def test_silence_snooze_expires_but_judge_seen_is_permanent(monkeypatch):
    # 2026-09-21: 침묵 틱 seen이 영구라 ParkChain 365 green(8bc1e796)이 06:27Z 이후 영영 후보에서 빠졌다.
    import time as _t
    monkeypatch.setattr(T, "search", lambda q, limit=40: [{"id": "p", "memory": "ParkChain"}, {"id": "j", "memory": "judged"}])
    monkeypatch.setattr(T.A, "rerank", lambda rs, stats, exclude_machine=False: list(rs))
    st = {"seen": {"j": "t"}, "block": [], "snoozed": {"p": _t.time()}}
    tail = [{"role": "user", "text": "파크체인"}]
    assert [c["id"] for c in T.candidates(tail, st, {})] == []          # 둘 다 빠짐
    st["snoozed"]["p"] = _t.time() - T.SNOOZE_S - 1
    assert [c["id"] for c in T.candidates(tail, st, {})] == ["p"]       # 재운 건 되살아나고 판사 seen은 영구
    assert "p" not in st["snoozed"]                                      # 만료 항목은 지운다


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


def test_search_requests_raw_pool_without_server_gate(monkeypatch):
    """search()는 recall=low로 원장 게이트 LLM을 건너뛴다 — 사이드카가 rerank·게이트를 자체 수행하므로
    서버 gate-v2는 중복이고 질의당 7~22s였다(2026-09-21 실측)."""
    seen = {}
    monkeypatch.setattr(T, "mcp", lambda name, args, timeout=60: (seen.update({"name": name, "args": args}), {"results": [{"id": "a"}]})[1])
    assert T.search("x" * 2000, 40) == [{"id": "a"}]
    assert seen["name"] == "search_memories"
    assert seen["args"]["recall"] == "low"
    assert seen["args"]["limit"] == 40 and len(seen["args"]["query"]) == 1500


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
