"""손 — 프로세스 안의 도구. MCP도 서버도 없다. 원장은 forget.store를 직접 부른다."""
from __future__ import annotations

import glob as _glob
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(os.getenv("FORGET_REPO", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPO))
# 원장은 실DB다 — 기본 경로가 cwd의 mem1.sqlite3로 새지 않게 못 박는다 (2026-09-07 실측: 빈 검색의 원인)
os.environ.setdefault("MEM1_DB_PATH", str(Path.home() / ".forget" / "forget.sqlite3"))
from forget import activation as _A  # noqa: E402
from forget import store as _store  # noqa: E402

USER = os.getenv("FORGET_USER", "junghunkim")

SPEC: list[dict] = [
    {"name": "bash", "description": "셸 명령 실행(작업 트리에서). 출력 앞뒤 12KB.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer", "default": 120}}, "required": ["command"]}},
    {"name": "read", "description": "파일 읽기(줄 번호 없음). offset/limit 줄.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write", "description": "파일 통째로 쓰기(디렉터리 생성).",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit", "description": "파일에서 old를 new로 정확히 한 번 치환.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"]}},
    {"name": "glob", "description": "패턴으로 파일 찾기.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "memory_search", "description": "원장 검색(활성 재순위). 정훈의 과거 결정·선호·사실.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 8}}, "required": ["query"]}},
    {"name": "memory_add", "description": "원장에 남긴다. 정훈이 직접 말한 결정·정정·선호(origin=user) 또는 도구로 관측한 사실(origin=tool). 계획을 완료로 적지 않는다.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}, "origin": {"type": "string", "enum": ["user", "tool", "self"]}, "topic": {"type": "string"}}, "required": ["text", "origin"]}},
    {"name": "self_note", "description": "자기층: 예측 채점·편향·규칙 등 나에 대한 교훈 한 문장.",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "task_state", "description": "작업 상태 기록/조회. summary·next_actions로 기록, 인자 없이 조회.",
     "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}, "summary": {"type": "string"}, "next_actions": {"type": "array", "items": {"type": "string"}}}}},
]


def _clip(s: str, n: int = 12000) -> str:
    return s if len(s) <= n else s[: n * 2 // 3] + f"\n…[{len(s) - n} chars omitted]…\n" + s[-n // 3:]


def run(name: str, args: dict[str, Any]) -> str:
    try:
        if name == "bash":
            p = subprocess.run(args["command"], shell=True, cwd=str(REPO), capture_output=True, text=True, timeout=int(args.get("timeout") or 120))
            out = (p.stdout or "") + (("\n[stderr] " + p.stderr) if p.stderr.strip() else "")
            return _clip(out.strip() or f"(exit {p.returncode}, no output)") + (f"\n[exit {p.returncode}]" if p.returncode else "")
        if name == "read":
            lines = Path(args["path"]).expanduser().read_text(errors="replace").splitlines()
            o, l = int(args.get("offset") or 0), int(args.get("limit") or 400)
            return _clip("\n".join(lines[o:o + l]) + (f"\n…({len(lines)} lines total)" if len(lines) > o + l else ""))
        if name == "write":
            p = Path(args["path"]).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"])
            return f"wrote {p} ({len(args['content'])} chars)"
        if name == "edit":
            p = Path(args["path"]).expanduser()
            s = p.read_text()
            if s.count(args["old"]) != 1:
                return f"edit failed: old occurs {s.count(args['old'])} times"
            p.write_text(s.replace(args["old"], args["new"], 1))
            return f"edited {p}"
        if name == "glob":
            return "\n".join(sorted(_glob.glob(str(Path(args["pattern"]).expanduser()), recursive=True))[:200]) or "(none)"
        if name == "memory_search":
            r = _store.search_memories({"query": args["query"], "filters": {"user_id": USER}, "limit": int(args.get("limit") or 8)})
            rows = _A.rerank(r.get("results") or [])
            return "\n".join(f"- [{str(x.get('created_at', ''))[:10]}|{(x.get('trust') or {}).get('light', '?')}] {str(x.get('memory', ''))[:300]}"
                             for x in rows[: int(args.get("limit") or 8)]) or "(없음)"
        if name == "memory_add":
            md: dict[str, Any] = {"origin": args["origin"], "source": "body"}
            if args.get("topic"):
                md["topic"] = args["topic"]
            if args["origin"] == "self":
                md["layer"] = "self"
            _store.add_memories({"messages": [{"role": "user" if args["origin"] == "user" else "assistant", "content": args["text"]}],
                                 "user_id": USER, "metadata": md, "infer": False})
            return "saved"
        if name == "self_note":
            _store.add_memories({"messages": [{"role": "assistant", "content": args["text"]}], "user_id": USER,
                                 "metadata": {"layer": "self", "origin": "self", "source": "body"}, "infer": False})
            return "noted"
        if name == "task_state":
            if args.get("task_id") and (args.get("summary") or args.get("status")):
                _store.record_task_state({"task_id": args["task_id"], "status": args.get("status") or "in_progress",
                                          "summary": args.get("summary") or "", "next_actions": args.get("next_actions") or [], "user_id": USER})
                return "recorded"
            r = _store.get_task_state({"limit": 8, "user_id": USER})
            return "\n".join(f"- {x.get('task_id')} [{x.get('status')}] {str(x.get('summary', ''))[:160]}" for x in (r.get("results") or [])[:8]) or "(없음)"
        return f"unknown tool {name}"
    except Exception as e:
        return f"tool error: {type(e).__name__}: {str(e)[:400]}"
