#!/usr/bin/env python3
"""Claude Code 세션(jsonl) → pi 세션(v3 jsonl) 이식기 (2026-09-07, «이사 준비»).

정훈: «지금 세션을 새로운 하네스에 그대로 이식할 수 있어?» — 전사는 옮길 수 있다. 문맥은 아니다.
그래서 Claude의 압축 요약(isCompactSummary)을 pi의 `compaction` 항목으로 옮긴다. pi는 마지막 압축
이후만 문맥으로 싣고 그 앞은 파일에 남긴다 — 지금 이 세션이 살고 있는 모습과 같다.

  .venv/bin/python scripts/session_transplant.py <claude.jsonl> [-o out.jsonl] [--tail-only]
      [--tool-max-chars 12000] [--keep-thinking]

규칙
- assistant 레코드는 message.id가 같으면 한 AssistantMessage로 합친다(Claude는 블록마다 줄을 쪼갠다).
- thinking 블록은 기본 제외(서명 없는 thinking은 재생 시 프로바이더가 거부할 수 있다).
- 이미지는 «[image N bytes]» 텍스트로 대체(파일 크기·문맥 보호).
- 도구 결과는 --tool-max-chars에서 자른다(앞·뒤 보존, 중간 생략 표시).
- 도구 이름은 pi 기본 도구와 맞춘다(Bash→bash, Read→read, Edit→edit, Write→write). 나머지는 그대로.
- sidechain(서브에이전트) 레코드·시스템·첨부는 제외.
- 출력 첫 항목은 헤더, 다음은 custom(forget_transplant) 항목에 출처·통계, 이후 메시지 사슬.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

PI_TOOL_NAMES = {"Bash": "bash", "Read": "read", "Edit": "edit", "Write": "write", "Grep": "grep", "Glob": "glob"}


def _ts_ms(s: str | None) -> int:
    if not s:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return int(datetime.now(timezone.utc).timestamp() * 1000)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms % 1000:03d}Z"


def _sid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]


def _clip(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    head = max_chars * 2 // 3
    tail = max_chars - head
    return text[:head] + f"\n…[transplant: {len(text) - max_chars} chars omitted]…\n" + text[-tail:]


def _text_of(content, tool_max: int) -> list[dict]:
    out: list[dict] = []
    if isinstance(content, str):
        out.append({"type": "text", "text": _clip(content, tool_max)})
        return out
    if isinstance(content, list):
        for p in content:
            if not isinstance(p, dict):
                continue
            t = p.get("type")
            if t == "text":
                out.append({"type": "text", "text": _clip(str(p.get("text", "")), tool_max)})
            elif t == "image":
                src = p.get("source") or {}
                out.append({"type": "text", "text": f"[image {len(str(src.get('data', '')))} bytes, {src.get('media_type', '?')} — dropped by transplant]"})
    return out or [{"type": "text", "text": ""}]


def convert(src: str, tail_only: bool = False, tool_max: int = 12000, keep_thinking: bool = False) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    with open(src, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") in ("user", "assistant") and not d.get("isSidechain"):
                rows.append(d)

    # Claude 세션 정보
    first = rows[0] if rows else {}
    cwd = first.get("cwd") or os.getcwd()
    claude_sid = first.get("sessionId") or os.path.basename(src).split(".")[0]

    entries: list[dict] = []
    stats = {"user": 0, "assistant": 0, "toolResult": 0, "compaction": 0, "images_dropped": 0, "thinking_dropped": 0, "tool_clipped": 0}
    tool_names: dict[str, str] = {}
    parent: str | None = None
    pending_assistant: dict | None = None  # 같은 message.id 합치기
    last_compaction_idx = -1

    def push(entry: dict) -> None:
        nonlocal parent
        entry["parentId"] = parent
        entries.append(entry)
        parent = entry["id"]

    def flush_assistant() -> None:
        nonlocal pending_assistant
        if pending_assistant:
            push(pending_assistant)
            pending_assistant = None

    for i, d in enumerate(rows):
        m = d.get("message") or {}
        role = m.get("role")
        ts = _ts_ms(d.get("timestamp"))
        uuid = d.get("uuid") or _sid(src, str(i))
        if role == "user":
            flush_assistant()
            content = m.get("content")
            # 도구 결과?
            if isinstance(content, list) and content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                for p in content:
                    if not isinstance(p, dict) or p.get("type") != "tool_result":
                        continue
                    raw = p.get("content")
                    body = _text_of(raw, tool_max)
                    if any("chars omitted" in b.get("text", "") for b in body):
                        stats["tool_clipped"] += 1
                    call_id = str(p.get("tool_use_id", ""))
                    push({"type": "message", "id": _sid(uuid, call_id), "timestamp": _iso(ts),
                          "message": {"role": "toolResult", "toolCallId": call_id,
                                      "toolName": tool_names.get(call_id, "unknown"), "content": body,
                                      "isError": bool(p.get("is_error")), "timestamp": ts}})
                    stats["toolResult"] += 1
                continue
            if d.get("isCompactSummary"):
                text = content if isinstance(content, str) else "".join(p.get("text", "") for p in content if isinstance(p, dict))
                push({"type": "compaction", "id": _sid(uuid), "timestamp": _iso(ts), "summary": text,
                      "firstKeptEntryId": "", "tokensBefore": 0, "fromHook": False,
                      "details": {"source": "claude-code isCompactSummary", "transplant": True}})
                stats["compaction"] += 1
                last_compaction_idx = len(entries) - 1
                continue
            body = _text_of(content, 0)
            if isinstance(content, list):
                stats["images_dropped"] += sum(1 for p in content if isinstance(p, dict) and p.get("type") == "image")
            push({"type": "message", "id": _sid(uuid), "timestamp": _iso(ts),
                  "message": {"role": "user", "content": body, "timestamp": ts}})
            stats["user"] += 1
        elif role == "assistant":
            mid = m.get("id") or uuid
            blocks: list[dict] = []
            for p in m.get("content") or []:
                if not isinstance(p, dict):
                    continue
                t = p.get("type")
                if t == "text":
                    blocks.append({"type": "text", "text": p.get("text", "")})
                elif t == "thinking":
                    if keep_thinking:
                        blocks.append({"type": "thinking", "thinking": p.get("thinking", "")})
                    else:
                        stats["thinking_dropped"] += 1
                elif t == "tool_use":
                    name = PI_TOOL_NAMES.get(p.get("name", ""), p.get("name", "tool"))
                    tool_names[str(p.get("id"))] = name
                    blocks.append({"type": "toolCall", "id": str(p.get("id")), "name": name, "arguments": p.get("input") or {}})
            if pending_assistant and pending_assistant.get("_mid") == mid:
                pending_assistant["message"]["content"].extend(blocks)
            else:
                flush_assistant()
                pending_assistant = {"type": "message", "id": _sid(uuid, mid), "timestamp": _iso(ts), "_mid": mid,
                                     "message": {"role": "assistant", "content": blocks, "api": "anthropic-messages",
                                                 "provider": "anthropic", "model": m.get("model", "claude"),
                                                 "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0,
                                                           "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}},
                                                 "stopReason": "stop", "timestamp": ts}}
                stats["assistant"] += 1
            if any(b.get("type") == "toolCall" for b in pending_assistant["message"]["content"]):
                pending_assistant["message"]["stopReason"] = "toolUse"
    flush_assistant()
    for e in entries:
        e.pop("_mid", None)
    # 빈 assistant(thinking만 있던 메시지) 제거는 하지 않는다 — 사슬이 끊긴다. 대신 빈 텍스트 한 조각을 넣는다.
    for e in entries:
        if e.get("type") == "message" and e["message"]["role"] == "assistant" and not e["message"]["content"]:
            e["message"]["content"] = [{"type": "text", "text": ""}]
    # compaction.firstKeptEntryId = 바로 다음 항목
    for idx, e in enumerate(entries):
        if e.get("type") == "compaction":
            e["firstKeptEntryId"] = entries[idx + 1]["id"] if idx + 1 < len(entries) else e["id"]

    if tail_only and last_compaction_idx >= 0:
        kept = entries[last_compaction_idx:]
        kept[0] = dict(kept[0]); kept[0]["parentId"] = None
        # 사슬 재연결
        prev = None
        for e in kept:
            e["parentId"] = prev
            prev = e["id"]
        entries = kept

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    header = {"type": "session", "version": 3, "id": f"transplant-{claude_sid[:8]}-{now_ms // 1000}",
              "timestamp": _iso(now_ms), "cwd": cwd, "parentSession": f"claude-code:{claude_sid}"}
    meta = {"type": "custom", "id": _sid("meta", claude_sid, str(now_ms)), "parentId": None, "timestamp": _iso(now_ms),
            "customType": "forget_transplant",
            "data": {"source": src, "claude_session_id": claude_sid, "tail_only": tail_only, "stats": stats,
                     "note": "Claude Code 세션 이식. 압축 요약은 compaction 항목으로 옮겼다 — pi는 마지막 compaction 이후만 문맥에 싣는다."}}
    if entries:
        entries[0]["parentId"] = meta["id"]
    return [header, meta, *entries], stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out")
    ap.add_argument("--tail-only", action="store_true", help="마지막 압축 요약 이후만 (문맥에 실리는 부분)")
    ap.add_argument("--tool-max-chars", type=int, default=12000)
    ap.add_argument("--keep-thinking", action="store_true")
    a = ap.parse_args()
    out_entries, stats = convert(a.src, a.tail_only, a.tool_max_chars, a.keep_thinking)
    out = a.out or (os.path.splitext(os.path.basename(a.src))[0] + (".tail" if a.tail_only else "") + ".pi.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for e in out_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    size = os.path.getsize(out)
    print(json.dumps({"out": out, "bytes": size, "entries": len(out_entries) - 2, **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
