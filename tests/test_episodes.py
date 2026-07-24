"""Episodic recall — the bridge from doctrine back to the scene.

Assistant-authored (2026-07-25). Origin: the post-compaction hand
inherited "trust labels exist" but could not reach the morning the
system was deceived, the pet name the bug was given ("곰"), or the
stammering minute the surprise-recall idea was born. Scenes live in
transcripts; this recalls them with receipts.
"""

import json

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
