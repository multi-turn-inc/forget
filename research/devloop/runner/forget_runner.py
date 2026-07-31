#!/usr/bin/env python3
"""forget_runner — 컴팩션 없는 헤드리스 에이전트 러너 (롤링 응고 2단계 프로토타입).

claude -p 를 대체한다: 메시지 배열을 러너가 소유하므로, 컨텍스트가 임계에 닿으면
전체를 파국적으로 압축하는 대신 **오래된 턴만** 다이제스트 한 장으로 splice하고
최근 창은 원문 그대로 둔다. 다이제스트 원문은 forget에도 적립되어(무손실)
컨텍스트 밖에서도 회수 가능하다.

설계 명제 (LOOP.md 백로그 7, 정훈 2026-07-31):
  "중·장기 기억은 항상 재구성되지만, 전체가 재구성되지는 않는다.
   전체 컨텍스트가 흘러넘치지 않도록 하는 것. 더 이상의 컴팩션은 없다."

검증: predictions.md P5. 예산을 의도적으로 작게 잡아 응고를 강제 유발한다 —
응고가 일어나고도 사이클이 품질 저하 없이 완주하는가가 실험이다.

사용:
  ANTHROPIC_API_KEY=... .venv/bin/python research/devloop/runner/forget_runner.py \
      --prompt "devloop 사이클을 정확히 한 바퀴 실행하라..." --cwd <repo>

응고 로직(choose_cut_index / splice_consolidated)은 순수 함수 — API 없이 테스트된다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request

MODEL = os.environ.get("FORGET_RUNNER_MODEL", "claude-fable-5")
DIGEST_MODEL = os.environ.get("FORGET_RUNNER_DIGEST_MODEL", "claude-haiku-4-5-20251001")
CONTEXT_BUDGET = int(os.environ.get("FORGET_RUNNER_BUDGET_TOKENS", "60000"))
CONSOLIDATE_AT = float(os.environ.get("FORGET_RUNNER_CONSOLIDATE_AT", "0.7"))
KEEP_RECENT = int(os.environ.get("FORGET_RUNNER_KEEP_RECENT", "12"))  # 메시지 수(≈6턴)
MAX_TURNS = int(os.environ.get("FORGET_RUNNER_MAX_TURNS", "60"))
FORGET_URL = os.environ.get(
    "FORGET_MCP_URL", "http://127.0.0.1:8000/mcp/forget/http/junghunkim"
)

BASH_DENY = ("sudo", "launchctl", "rm -rf /", "git push --force", ":(){", "shutdown")

TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command in the working directory. No sudo/launchctl.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file (optionally offset/limit lines).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write full content to a file (creates parents).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Exact string replacement in a file (old must be unique).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string"},
                "new": {"type": "string"},
            },
            "required": ["path", "old", "new"],
        },
    },
    {
        "name": "forget",
        "description": "Call a forget MCP tool (get_task_state, record_task_state, "
        "add_memory, search_memories, ...) with a JSON arguments object.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["tool"],
        },
    },
]


# ---------------------------------------------------------------- 응고 (순수)


def choose_cut_index(messages: list[dict], keep_recent: int) -> int:
    """오래된 구간 [0:cut]을 응고할 수 있는 가장 큰 cut을 고른다.

    불변식: messages[cut]은 assistant여야 한다 — 그래야 tool_use/tool_result 쌍이
    경계에서 찢어지지 않고, [user(digest)] + messages[cut:]의 역할 교대가 성립한다.
    응고할 것이 2메시지 미만이면 0(응고 불가)을 돌려준다.
    """
    cut = max(0, len(messages) - keep_recent)
    while cut > 1 and messages[cut].get("role") != "assistant":
        cut -= 1
    if cut <= 1 or messages[cut].get("role") != "assistant":
        return 0
    return cut


def render_for_digest(messages: list[dict], limit_chars: int = 60_000) -> str:
    """응고 대상 구간을 다이제스트 모델 입력용 평문으로 렌더링."""
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content")
        if isinstance(content, str):
            lines.append(f"[{role}] {content}")
            continue
        for block in content or []:
            kind = block.get("type")
            if kind == "text":
                lines.append(f"[{role}] {block.get('text', '')}")
            elif kind == "tool_use":
                lines.append(
                    f"[{role} tool:{block.get('name')}] "
                    f"{json.dumps(block.get('input', {}), ensure_ascii=False)[:400]}"
                )
            elif kind == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(
                        b.get("text", "") for b in body if isinstance(b, dict)
                    )
                lines.append(f"[tool_result] {str(body)[:600]}")
    text = "\n".join(lines)
    return text[-limit_chars:]


def splice_consolidated(
    messages: list[dict], cut: int, digest: str, first_user_prompt: str
) -> list[dict]:
    """[0:cut]을 다이제스트 한 장으로 치환. 최근 창은 원문 유지."""
    header = (
        "[응고된 과거 — 이 세션의 오래된 턴들은 아래 다이제스트로 치환되었다. "
        "원문 손실분은 forget에 적립되어 search_memories로 회수 가능]\n"
        f"<원래 과업(원문 유지)>\n{first_user_prompt}\n</원래 과업>\n"
        f"<지금까지의 진행 다이제스트>\n{digest}\n</지금까지의 진행 다이제스트>"
    )
    return [{"role": "user", "content": header}] + messages[cut:]


# ---------------------------------------------------------------- 도구 실행


def _tool_bash(args: dict, cwd: str) -> str:
    cmd = str(args.get("command", ""))
    if any(bad in cmd for bad in BASH_DENY):
        return f"DENIED: command matches denylist ({cmd[:60]})"
    proc = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=300
    )
    out = (proc.stdout + proc.stderr)[-8_000:]
    return f"exit={proc.returncode}\n{out}"


def _tool_read(args: dict, cwd: str) -> str:
    path = os.path.join(cwd, os.path.expanduser(args["path"])) if not os.path.isabs(
        os.path.expanduser(args["path"])
    ) else os.path.expanduser(args["path"])
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    off = int(args.get("offset") or 0)
    lim = int(args.get("limit") or 2000)
    return "".join(lines[off : off + lim])[:80_000]


def _tool_write(args: dict, cwd: str) -> str:
    path = args["path"] if os.path.isabs(args["path"]) else os.path.join(cwd, args["path"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(args["content"])
    return f"wrote {len(args['content'])} chars to {path}"


def _tool_edit(args: dict, cwd: str) -> str:
    path = args["path"] if os.path.isabs(args["path"]) else os.path.join(cwd, args["path"])
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if text.count(args["old"]) != 1:
        return f"ERROR: old string occurs {text.count(args['old'])} times (need exactly 1)"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(args["old"], args["new"], 1))
    return "edited"


def _tool_forget(args: dict, _cwd: str) -> str:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": args["tool"], "arguments": args.get("arguments") or {}},
    }
    req = urllib.request.Request(
        FORGET_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return json.dumps(body.get("result", body), ensure_ascii=False)[:12_000]


TOOL_IMPL = {
    "bash": _tool_bash,
    "read_file": _tool_read,
    "write_file": _tool_write,
    "edit_file": _tool_edit,
    "forget": _tool_forget,
}


# ---------------------------------------------------------------- 러너


class ForgetRunner:
    def __init__(self, cwd: str, log_path: str):
        import anthropic  # lazy — 응고 로직 테스트는 SDK 없이 돈다

        self.client = anthropic.Anthropic()
        self.cwd = cwd
        self.log_path = log_path
        self.messages: list[dict] = []
        self.first_user_prompt = ""
        self.consolidations = 0
        self.total_in = 0
        self.total_out = 0

    def _log(self, kind: str, **fields):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": time.time(), "kind": kind, **fields},
                                ensure_ascii=False) + "\n")

    def _digest(self, old: list[dict]) -> str:
        resp = self.client.messages.create(
            model=DIGEST_MODEL,
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": (
                    "다음은 에이전트 세션의 오래된 구간이다. 이후 작업 계속에 필요한 "
                    "것만 남겨 응고하라: 내린 결정과 이유 / 확정된 사실·경로·숫자 / "
                    "미해결·실패와 원인 / 하지 말라고 판명난 것. 산문 불필요, 조밀한 "
                    "불릿. 이미 완료되어 다시 볼 일 없는 과정은 버려라.\n\n"
                    + render_for_digest(old)
                ),
            }],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    def _maybe_consolidate(self, last_input_tokens: int):
        if last_input_tokens < CONTEXT_BUDGET * CONSOLIDATE_AT:
            return
        cut = choose_cut_index(self.messages, KEEP_RECENT)
        if not cut:
            return
        old = self.messages[:cut]
        digest = self._digest(old)
        # 무손실: 다이제스트를 forget에도 적립 (컨텍스트 밖 회수 경로)
        try:
            _tool_forget({
                "tool": "add_memory",
                "arguments": {
                    "text": f"[runner-digest] {digest[:4000]}",
                    "metadata": {"source": "forget_runner", "cut_messages": cut},
                },
            }, self.cwd)
        except Exception as exc:  # 적립 실패가 응고를 막지는 않는다 — 로그만
            self._log("digest_store_failed", error=str(exc)[:200])
        self.messages = splice_consolidated(
            self.messages, cut, digest, self.first_user_prompt
        )
        self.consolidations += 1
        self._log("consolidated", cut=cut, input_tokens=last_input_tokens,
                  digest_chars=len(digest))

    def run(self, prompt: str, system: str) -> str:
        self.first_user_prompt = prompt
        self.messages.append({"role": "user", "content": prompt})
        final_text = ""
        for turn in range(MAX_TURNS):
            resp = self.client.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=system,
                tools=TOOLS,
                messages=self.messages,
            )
            self.total_in += resp.usage.input_tokens
            self.total_out += resp.usage.output_tokens
            self.messages.append(
                {"role": "assistant", "content": [b.model_dump() for b in resp.content]}
            )
            if resp.stop_reason != "tool_use":
                final_text = "".join(b.text for b in resp.content if b.type == "text")
                break
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                impl = TOOL_IMPL.get(block.name)
                try:
                    out = impl(block.input, self.cwd) if impl else f"unknown tool {block.name}"
                except Exception as exc:
                    out = f"TOOL ERROR: {exc}"
                results.append({
                    "type": "tool_result", "tool_use_id": block.id, "content": out,
                })
            self.messages.append({"role": "user", "content": results})
            self._maybe_consolidate(resp.usage.input_tokens)
        self._log("done", turns=turn + 1, consolidations=self.consolidations,
                  input_tokens=self.total_in, output_tokens=self.total_out)
        return final_text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--system", default=(
        "너는 forget 저장소에서 일하는 자율 개발 에이전트다. 도구로 실작업을 하고, "
        "결정은 forget 도구(add_memory/record_task_state)로 기록한다. 완료되면 "
        "도구 없이 최종 보고만 남긴다."
    ))
    ap.add_argument("--log", default=os.path.expanduser("~/.forget/runner/runs.jsonl"))
    args = ap.parse_args()
    runner = ForgetRunner(cwd=args.cwd, log_path=args.log)
    print(runner.run(args.prompt, args.system))
    print(
        f"\n--- runner: turns_in={runner.total_in} out={runner.total_out} "
        f"consolidations={runner.consolidations} (budget {CONTEXT_BUDGET}, "
        f"keep_recent {KEEP_RECENT})"
    )


if __name__ == "__main__":
    main()
