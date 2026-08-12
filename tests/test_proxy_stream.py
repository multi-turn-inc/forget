"""proxy_stream contract tests — delta-diff session reconstruction.

Fixtures mimic what forget-proxy actually appends: one JSON line per
completed exchange, request_messages carrying the full resent history.
Everything runs against tmp_path — the live ~/.forget is never touched.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from forget.proxy_stream import iter_stream_rows, purge_expired, reconstruct, to_cc_rows

DAY = "2026-08-12"


def _row(ts: str, hint: str | None, messages: list, response: list | None) -> dict:
    return {
        "ts": ts,
        "session_hint": hint,
        "model": "claude-opus-5",
        "request_messages": messages,
        "response_content": response,
        "usage": {"input_tokens": 11, "output_tokens": 7},
        "latency_ms": 5,
    }


def _write_day(stream_dir, day: str, lines: list) -> None:
    stream_dir.mkdir(parents=True, exist_ok=True)
    with (stream_dir / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write((line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)) + "\n")


A1 = [
    {"type": "text", "text": "읽겠습니다"},
    {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "a.py"}},
]
TOOL_ERR = [{"type": "tool_result", "tool_use_id": "tu_1", "content": "ENOENT: a.py", "is_error": True}]
A2 = [{"type": "text", "text": "파일이 없네요"}]
A3 = [{"type": "text", "text": "천만에요"}]


def _linear_rows(hint: str = "sess-linear") -> list[dict]:
    """Three requests of one session: each resends the full history, the
    second carries a tool_result (is_error=True — the trap-arc signal)."""
    m1 = [{"role": "user", "content": "a.py 읽어줘"}]
    m2 = m1 + [{"role": "assistant", "content": A1}, {"role": "user", "content": TOOL_ERR}]
    m3 = m2 + [{"role": "assistant", "content": A2}, {"role": "user", "content": "고마워"}]
    return [
        _row(f"{DAY}T09:00:00Z", hint, m1, A1),
        _row(f"{DAY}T09:00:10Z", hint, m2, A2),
        _row(f"{DAY}T09:00:20Z", hint, m3, A3),
    ]


def test_linear_conversation_reconstructs_six_turns(tmp_path):
    _write_day(tmp_path, DAY, _linear_rows())
    result = reconstruct(tmp_path)

    assert result["stats"] == {"rows": 3, "threads": 1, "forks": 0, "broken": 0}
    (session,) = result["sessions"]
    assert session["key"] == "sess-linear"
    (segment,) = session["segments"]
    assert segment["fork_from"] is None

    turns = segment["turns"]
    assert [t["role"] for t in turns] == ["user", "assistant", "user", "assistant", "user", "assistant"]
    # Delta-diff: each turn appears exactly once despite triple resending.
    assert turns[0]["content"] == "a.py 읽어줘"
    assert turns[1]["content"] == A1 and turns[1]["source"] == "response"
    assert turns[2]["content"] == TOOL_ERR
    assert turns[3]["content"] == A2
    assert turns[4]["content"] == "고마워"
    assert turns[5]["content"] == A3
    assert turns[5]["ts"] == f"{DAY}T09:00:20Z"


def test_retry_opens_second_segment_with_fork_from(tmp_path):
    m1 = [{"role": "user", "content": "질문"}]
    _write_day(
        tmp_path,
        DAY,
        [
            _row(f"{DAY}T10:00:00Z", "sess-retry", m1, [{"type": "text", "text": "첫 답"}]),
            # Regenerate: same history resent, canonical assistant turn dropped.
            _row(f"{DAY}T10:00:30Z", "sess-retry", m1, [{"type": "text", "text": "다시 쓴 답"}]),
        ],
    )
    result = reconstruct(tmp_path)

    assert result["stats"]["threads"] == 1
    assert result["stats"]["forks"] == 1
    (session,) = result["sessions"]
    first, second = session["segments"]
    assert [t["content"] for t in first["turns"]] == ["질문", [{"type": "text", "text": "첫 답"}]]
    assert second["fork_from"] == 1  # branched right after the shared user turn
    assert [t["content"] for t in second["turns"]] == [[{"type": "text", "text": "다시 쓴 답"}]]


def test_same_system_different_hints_stay_separate_sessions(tmp_path):
    shared = [{"role": "user", "content": "안녕"}]
    _write_day(
        tmp_path,
        DAY,
        [
            _row(f"{DAY}T11:00:00Z", "sess-a", shared, [{"type": "text", "text": "A입니다"}]),
            _row(f"{DAY}T11:00:01Z", "sess-b", shared, [{"type": "text", "text": "B입니다"}]),
        ],
    )
    result = reconstruct(tmp_path)

    assert result["stats"]["threads"] == 2
    assert result["stats"]["forks"] == 0
    assert [s["key"] for s in result["sessions"]] == ["sess-a", "sess-b"]
    for session in result["sessions"]:
        (segment,) = session["segments"]
        assert len(segment["turns"]) == 2


def test_broken_rows_are_skipped_and_counted(tmp_path):
    good = _row(f"{DAY}T12:00:00Z", "sess-ok", [{"role": "user", "content": "정상"}], A3)
    _write_day(
        tmp_path,
        DAY,
        [
            good,
            "{not json at all",
            '"a bare string is not a capture row"',
            json.dumps({"ts": f"{DAY}T12:00:02Z", "request_messages": None}),
        ],
    )
    stats: dict[str, int] = {}
    rows = list(iter_stream_rows(tmp_path, stats=stats))
    assert len(rows) == 1 and rows[0]["session_hint"] == "sess-ok"
    assert stats == {"rows": 1, "broken": 3}

    result = reconstruct(tmp_path)
    assert result["stats"]["rows"] == 1
    assert result["stats"]["broken"] == 3
    assert len(result["sessions"]) == 1


def test_to_cc_rows_preserves_tool_result_is_error(tmp_path):
    _write_day(tmp_path, DAY, _linear_rows())
    (session,) = reconstruct(tmp_path)["sessions"]
    rows = to_cc_rows(session["segments"][0])

    assert [r["type"] for r in rows] == ["user", "assistant", "user", "assistant", "user", "assistant"]
    tool_row = rows[2]
    assert tool_row["type"] == "user"  # CC carries tool results inside user rows
    (block,) = tool_row["message"]["content"]
    assert block["type"] == "tool_result"
    assert block["is_error"] is True
    assert block["content"] == "ENOENT: a.py"
    assert all(r["timestamp"] for r in rows)
    assert rows[1]["message"]["role"] == "assistant"


def test_reconstruct_mixed_stream_stats(tmp_path):
    """Integration: linear session + retry session + singleton + broken line
    in one day file — the stats block is the miner-feeding contract."""
    rows: list = _linear_rows()
    m1 = [{"role": "user", "content": "질문"}]
    rows += [
        _row(f"{DAY}T10:00:00Z", "sess-retry", m1, [{"type": "text", "text": "첫 답"}]),
        _row(f"{DAY}T10:00:30Z", "sess-retry", m1, [{"type": "text", "text": "다시 쓴 답"}]),
        _row(f"{DAY}T11:00:00Z", "sess-b", [{"role": "user", "content": "안녕"}], A3),
    ]
    _write_day(tmp_path, DAY, rows + ["{broken line"])

    result = reconstruct(tmp_path)

    assert result["stats"] == {"rows": 6, "threads": 3, "forks": 1, "broken": 1}
    shapes = {
        s["key"]: [(len(seg["turns"]), seg["fork_from"]) for seg in s["segments"]]
        for s in result["sessions"]
    }
    assert shapes == {
        "sess-linear": [(6, None)],
        "sess-retry": [(2, None), (1, 1)],
        "sess-b": [(2, None)],
    }


def test_purge_expired_keeps_today_and_fresh_files(tmp_path):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    old_line = [_row("2026-07-01T00:00:00Z", "s", [{"role": "user", "content": "옛날"}], A3)]
    _write_day(tmp_path, "2026-07-01", old_line)
    _write_day(tmp_path, "2026-08-11", old_line)
    _write_day(tmp_path, today, old_line)

    month_ago = time.time() - 30 * 86400
    os.utime(tmp_path / "2026-07-01.jsonl", (month_ago, month_ago))
    # Today's file gets an ancient mtime too: the name guard alone must save it.
    os.utime(tmp_path / f"{today}.jsonl", (month_ago, month_ago))

    deleted = purge_expired(tmp_path, ttl_days=14)

    assert deleted == [tmp_path / "2026-07-01.jsonl"]
    assert not (tmp_path / "2026-07-01.jsonl").exists()
    assert (tmp_path / "2026-08-11.jsonl").exists()  # fresh mtime survives
    assert (tmp_path / f"{today}.jsonl").exists()  # today is untouchable
