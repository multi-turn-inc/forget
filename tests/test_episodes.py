"""Episodic recall — the bridge from doctrine back to the scene.

Assistant-authored (2026-07-25). Origin: the post-compaction hand
inherited "trust labels exist" but could not reach the morning the
system was deceived, the pet name the bug was given ("곰"), or the
stammering minute the surprise-recall idea was born. Scenes live in
transcripts; this recalls them with receipts.
"""

import json
from pathlib import Path

from forget.episodes import recall_episodes


def _write_transcript(path, events):
    with open(path, "w") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def test_recall_finds_scene_with_receipt(tmp_path):
    transcript = tmp_path / "session-abc.jsonl"
    _write_transcript(transcript, [
        {"timestamp": "2026-07-22T09:00:00Z", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "비서가 사장 서명을 쓰고 있었어 — 문이 모든 저장에 사용자 도장을 찍었다."}]}},
        {"timestamp": "2026-07-22T10:00:00Z", "message": {"role": "user", "content": "곰 고쳐졌어?"}},
        {"timestamp": "2026-07-22T11:00:00Z", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "unrelated line about deployment"}]}},
    ])
    hits = recall_episodes("곰", roots=[tmp_path])
    assert len(hits) == 1
    assert "곰 고쳐졌어" in hits[0]["excerpt"]
    assert hits[0]["receipt"] == f"{transcript}:2"
    assert hits[0]["role"] == "user"


def test_all_terms_must_match_and_newest_first(tmp_path):
    old = tmp_path / "old.jsonl"
    new = tmp_path / "new.jsonl"
    _write_transcript(old, [
        {"timestamp": "2026-07-20T09:00:00Z", "message": {"role": "user", "content": "사장 서명 이야기의 첫 등장"}},
    ])
    _write_transcript(new, [
        {"timestamp": "2026-07-24T09:00:00Z", "message": {"role": "user", "content": "사장 서명 이야기가 다시 나옴"}},
    ])
    hits = recall_episodes("사장 서명", roots=[tmp_path])
    assert [h["timestamp"][:10] for h in hits] == ["2026-07-24", "2026-07-20"]
    assert recall_episodes("사장 없는단어", roots=[tmp_path]) == []


def test_mcp_tool_is_wired():
    from forget.mcp import TOOLS, _dispatch_tool
    assert any(tool["name"] == "recall_episode" for tool in TOOLS)
    result = _dispatch_tool("recall_episode", {"query": "definitely-not-present-xyz"})
    payload = json.loads(result["content"][0]["text"])
    assert payload["results"] == []


# --- harness-agnostic: Codex rollout transcripts (issue #9) ------------------

def test_codex_response_item_and_event_msg_are_read(tmp_path):
    # Codex writes rollout JSONL: content under `payload`, blocks typed
    # input_text/output_text, plus event_msg records carrying a plain string.
    transcript = tmp_path / "rollout-2026-07-25.jsonl"
    _write_transcript(transcript, [
        {"timestamp": "2026-07-25T01:00:00Z", "type": "session_meta",
         "payload": {"id": "s-1", "cwd": "/tmp"}},
        {"timestamp": "2026-07-25T01:01:00Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "왜 Paddle로 정했지?"}]}},
        {"timestamp": "2026-07-25T01:02:00Z", "type": "event_msg",
         "payload": {"type": "agent_message", "message": "Paddle은 merchant of record라서."}},
        {"timestamp": "2026-07-25T01:03:00Z", "type": "event_msg",
         "payload": {"type": "token_count", "message": "Paddle 노이즈 레코드"}},
    ])
    user_hits = recall_episodes("Paddle로", roots=[tmp_path])
    assert len(user_hits) == 1 and user_hits[0]["role"] == "user"
    assert "왜 Paddle로 정했지?" in user_hits[0]["excerpt"]

    agent_hits = recall_episodes("merchant of record", roots=[tmp_path])
    assert len(agent_hits) == 1 and agent_hits[0]["role"] == "assistant"

    # token_count carries a string but no utterance role — must stay out
    assert recall_episodes("노이즈 레코드", roots=[tmp_path]) == []


def test_duplicated_codex_utterance_yields_one_hit(tmp_path):
    # Codex records assistant text twice (event_msg + response_item); one
    # utterance must not become two search results.
    line = "지정된 한 사이클만 수행하겠습니다."
    _write_transcript(tmp_path / "dup.jsonl", [
        {"timestamp": "2026-07-25T02:00:00Z", "type": "event_msg",
         "payload": {"type": "agent_message", "message": line}},
        {"timestamp": "2026-07-25T02:00:00Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": line}]}},
    ])
    hits = recall_episodes("한 사이클만", roots=[tmp_path])
    assert len(hits) == 1, hits


def test_default_roots_cover_both_harnesses(monkeypatch):
    from forget.episodes import transcript_roots

    monkeypatch.delenv("MEM1_EPISODE_ROOTS", raising=False)
    monkeypatch.setenv("CODEX_HOME", "/custom/codex-home")
    roots = [str(path) for path in transcript_roots()]
    assert any(root.endswith("/.claude/projects") for root in roots)
    assert any(root.endswith("/.codex/sessions") for root in roots)
    assert "/custom/codex-home/sessions" in roots

    # an explicit override still wins outright
    monkeypatch.setenv("MEM1_EPISODE_ROOTS", "/only/here")
    assert [str(p) for p in transcript_roots()] == ["/only/here"]

    # CODEX_HOME pointing at the default must not double-scan
    monkeypatch.delenv("MEM1_EPISODE_ROOTS", raising=False)
    monkeypatch.setenv("CODEX_HOME", str(Path("~/.codex").expanduser()))
    resolved = [str(p) for p in transcript_roots()]
    assert len(resolved) == len(set(resolved))
