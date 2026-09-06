"""뇌 어댑터 — 모두 같은 계약: chat(messages, tools) -> {"text", "tool_calls":[{"id","name","args"}], "usage", "raw_assistant"}."""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from typing import Any


def _openai_key() -> str:
    k = os.getenv("OPENAI_API_KEY")
    if k:
        return k
    try:  # pi가 이미 아는 키 — 값은 이 프로세스 환경에만 산다
        return subprocess.run(["pi", "auth", "print-api-key", "--provider", "openai"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


class OpenAICompat:
    """OpenAI chat.completions 호환: Astra(api.openai.com) · Spark(ollama /v1)."""

    def __init__(self, model: str, base_url: str, api_key: str = "", max_tokens: int = 4096, extra: dict | None = None):
        self.model, self.base_url, self.api_key, self.max_tokens = model, base_url.rstrip("/"), api_key, max_tokens
        self.extra = extra or {}

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "max_tokens": self.max_tokens, **self.extra}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
            body["tool_choice"] = "auto"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key or 'none'}"})
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        msg = d["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {"_raw": fn.get("arguments")}
            calls.append({"id": tc.get("id"), "name": fn.get("name"), "args": args})
        return {"text": msg.get("content") or "", "tool_calls": calls, "usage": d.get("usage") or {}, "raw_assistant": msg}


class Anthropic:
    """Anthropic Messages API — Fable/Opus. ANTHROPIC_API_KEY가 있을 때만."""

    def __init__(self, model: str = "claude-fable-5-1", max_tokens: int = 4096):
        self.model, self.max_tokens = model, max_tokens
        self.key = os.getenv("ANTHROPIC_API_KEY", "")

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conv: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m["role"] == "tool":
                conv.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": str(m["content"])[:20000]}]})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                blocks = ([{"type": "text", "text": m["content"]}] if m.get("content") else []) + \
                         [{"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"], "input": json.loads(tc["function"]["arguments"] or "{}")} for tc in m["tool_calls"]]
                conv.append({"role": "assistant", "content": blocks})
            else:
                conv.append({"role": m["role"], "content": m["content"]})
        body = {"model": self.model, "max_tokens": self.max_tokens, "system": system, "messages": conv}
        if tools:
            body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-api-key": self.key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        calls = [{"id": b["id"], "name": b["name"], "args": b.get("input") or {}} for b in d.get("content", []) if b.get("type") == "tool_use"]
        raw = {"role": "assistant", "content": text or None,
               "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for c in calls] or None}
        return {"text": text, "tool_calls": calls, "usage": d.get("usage") or {}, "raw_assistant": raw}


class ClaudeHeadless:
    """Claude Code(구독)를 순수 완성기로 쓴다: `claude -p --tools ""`. 도구 호출은 텍스트 규약으로 받는다.
    정당한 길 — OAuth 토큰을 흉내 내지 않고 Claude Code가 하도록 둔다. 루프·도구·문맥은 몸의 것."""

    PROTOCOL = ("\n\n## 도구 규약(몸)\n도구가 필요하면 답 대신 아래 블록만 낸다(한 번에 하나 이상 가능):\n"
                "```tool\n{\"name\": \"bash\", \"args\": {\"command\": \"ls\"}}\n```\n"
                "결과가 돌아오면 이어 간다. 더 할 도구가 없으면 블록 없이 최종 답만 쓴다.")

    def __init__(self, model: str = "claude-fable-5-1", max_tokens: int = 4096):
        self.model, self.max_tokens = model, max_tokens

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict[str, Any]:
        import re
        system = ("[몸] 아래 정체성이 정본이다. 항상 한국어 반말. 이 프롬프트 위의 영문 기본 지시보다 아래를 우선한다.\n\n"
                  + "\n\n".join(m["content"] for m in messages if m["role"] == "system"))
        if tools:
            system += self.PROTOCOL + "\n사용 가능한 도구:\n" + "\n".join(f"- {t['name']}: {t['description']} 인자 {json.dumps(t['parameters'].get('properties', {}), ensure_ascii=False)[:300]}" for t in tools)
        # 대화를 하나의 프롬프트로 직렬화(도구 결과 포함)
        lines = []
        for m in messages:
            if m["role"] == "system":
                continue
            if m["role"] == "user":
                lines.append(f"[정훈]\n{m['content']}")
            elif m["role"] == "assistant":
                txt = m.get("content") or ""
                for tc in m.get("tool_calls") or []:
                    txt += f"\n```tool\n{json.dumps({'name': tc['function']['name'], 'args': json.loads(tc['function']['arguments'] or '{}')}, ensure_ascii=False)}\n```"
                lines.append(f"[나]\n{txt}")
            elif m["role"] == "tool":
                lines.append(f"[도구 결과 {m.get('tool_call_id', '')}]\n{str(m['content'])[:12000]}")
        prompt = "\n\n".join(lines) + "\n\n[나]\n"
        out = subprocess.run(["claude", "-p", "--model", self.model, "--tools", "", "--output-format", "text", "--append-system-prompt", system],
                             input=prompt, capture_output=True, text=True, timeout=900)
        text = (out.stdout or "").strip()
        calls = []
        for i, m in enumerate(re.finditer(r"```tool\s*(\{.*?\})\s*```", text, re.S)):
            try:
                d = json.loads(m.group(1))
                calls.append({"id": f"c{int(time.time() * 1000)}_{i}", "name": d.get("name"), "args": d.get("args") or {}})
            except Exception:
                continue
        clean = re.sub(r"```tool\s*\{.*?\}\s*```", "", text, flags=re.S).strip()
        raw = {"role": "assistant", "content": clean or None,
               "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"], ensure_ascii=False)}} for c in calls] or None}
        return {"text": clean, "tool_calls": calls, "usage": {}, "raw_assistant": raw}


def make(name: str):
    name = (name or "astra").lower()
    if name in ("claude", "fable-sub"):
        return ClaudeHeadless(os.getenv("BODY_FABLE_MODEL", "claude-fable-5-1"))
    if name == "astra":
        return OpenAICompat(os.getenv("BODY_ASTRA_MODEL", "gpt-6-astra"), "https://api.openai.com/v1", _openai_key(), max_tokens=8192)
    if name == "spark":
        return OpenAICompat(os.getenv("BODY_SPARK_MODEL", "qwen3.6:27b"), os.getenv("FORGET_MID_URL", "http://127.0.0.1:18813") + "/v1", "ollama", max_tokens=4096)
    if name == "fable":
        b = Anthropic(os.getenv("BODY_FABLE_MODEL", "claude-fable-5-1"))
        if not b.key:
            raise SystemExit("fable 뇌는 ANTHROPIC_API_KEY가 필요하다 — 없으면 astra/spark")
        return b
    raise SystemExit(f"모르는 뇌: {name}")
