"""기억 주의 프로세스 — 사이드카의 심장 (2026-09-07, goal:observe-junghun).

세 루프 중 «빠른»과 «중간»을 여기서 돈다. 느린 루프(응고)는 consolidation이 맡는다.
- 빠른: 전사 꼬리 → 상황 텍스트 → 검색(40) → 활성 재순위 → 후보 12. 모델 없음.
- 중간: ① 안다는 느낌 게이트(작고 빠른 모델, ~1s) ② 판정(큰 모델, ~8s, 비동기):
  블록 편집(add/keep/drop) · 빈틈 · 놀람 · **관찰**(정훈의 결정·거부·정정·선호 → 쓰기 제안).
상태는 ~/.forget/attention/{state.json, block.md, log.jsonl, proposals.jsonl}. 원장은 add_memory로만 쓴다.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import activation as A

ATTN_DIR = A.ATTN_DIR
MCP_URL = os.getenv("FORGET_MCP_URL", "http://localhost:8000/mcp/forget/http/junghunkim")
LLM_URL = os.getenv("FORGET_MID_URL", "http://127.0.0.1:18813")          # ollama (Spark 터널)
GATE_MODEL = os.getenv("FORGET_GATE_MODEL", "qwen3.5:27b")     # 5~10s · 35b-a3b는 18813에 없음(2026-09-10~20 404 원인)
JUDGE_MODEL = os.getenv("FORGET_JUDGE_MODEL", "qwen3.6:27b")              # ~8s
BLOCK_MAX = 8
TAIL_TURNS = 12
TAIL_CHARS = 4000
CANDIDATES = 12
GATE_TIMEOUT = 60
JUDGE_TIMEOUT = 120


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 원장 ────────────────────────────────────────────────────────────────
def mcp(name: str, args: dict[str, Any], timeout: int = 60) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}).encode()
    req = urllib.request.Request(MCP_URL, data=body, headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    d = json.load(urllib.request.urlopen(req, timeout=timeout))
    t = d["result"]["content"][0]["text"]
    try:
        return json.loads(t)
    except Exception:
        return t


def search(query: str, limit: int = 40) -> list[dict[str, Any]]:
    r = mcp("search_memories", {"query": query[:1500], "limit": limit})
    return r.get("results", []) if isinstance(r, dict) else []


# ── 모델 ────────────────────────────────────────────────────────────────
def llm(model: str, prompt: str, timeout: int, num_ctx: int = 8192) -> str:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
                       "options": {"num_ctx": num_ctx, "temperature": 0.1}, "think": False, "keep_alive": "30m"}).encode()
    req = urllib.request.Request(f"{LLM_URL}/api/chat", data=body, headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    return r["message"]["content"]


def parse_json(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


# ── 전사 읽기 (Claude Code jsonl · pi jsonl 둘 다) ─────────────────────
def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    out = []
    for p in content or []:
        if isinstance(p, dict) and p.get("type") == "text":
            out.append(str(p.get("text", "")))
        elif isinstance(p, dict) and p.get("type") in ("toolCall", "tool_use"):
            out.append(f"[도구 {p.get('name')}]")
    return "\n".join(out)


def read_turns(path: Path, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """offset 바이트부터 새 줄을 읽어 (role, text, ts) 턴으로. 도구 결과는 뺀다."""
    turns: list[dict[str, Any]] = []
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = offset + len(data)
    # 마지막 불완전 줄은 다음 틱으로
    if data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n") + 1
        end = offset + cut
        data = data[:cut]
    for line in data.decode("utf-8", "ignore").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message") if isinstance(d.get("message"), dict) else None
        if not m and d.get("type") == "response_item":            # Codex rollout(~/.codex/sessions)
            pl = d.get("payload") or {}
            if pl.get("type") == "message" and pl.get("role") in ("user", "assistant"):
                txt = "".join(str(c.get("text", "")) for c in pl.get("content", []) if isinstance(c, dict)).strip()
                if txt and not txt.startswith("<"):                 # <environment_context> 등 주입 블록 제외
                    turns.append({"role": pl["role"], "text": txt[:3000], "ts": d.get("timestamp") or now_iso()})
            elif pl.get("type") in ("custom_tool_call", "function_call"):
                turns.append({"role": "action", "text": f"[도구 {pl.get('name', '')}]", "ts": d.get("timestamp") or now_iso()})
            continue
        if not m:
            continue
        role = m.get("role")
        if d.get("type") not in ("user", "assistant", "message") or d.get("isSidechain"):
            continue
        if role == "toolResult":
            continue
        content = m.get("content")
        if content is None:
            continue
        if role == "user" and isinstance(content, list) and content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
            continue
        txt = _text(content).strip()
        if not txt or d.get("isCompactSummary") or txt.startswith("[Request interrupted"):
            continue
        if role == "user" and txt.startswith("<") and "system-reminder" in txt[:40]:
            continue
        if role == "assistant" and all(ln.startswith("[도구 ") for ln in txt.splitlines()):
            role = "action"                                   # 도구만 부른 턴 — 틱은 세되 문장은 아니다
        turns.append({"role": role, "text": txt[:3000], "ts": d.get("timestamp") or now_iso()})
    return turns, end


# ── 상태 ────────────────────────────────────────────────────────────────
def load_state() -> dict[str, Any]:
    ATTN_DIR.mkdir(parents=True, exist_ok=True)
    p = ATTN_DIR / "state.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"source": "", "offset": 0, "tail": [], "block": [], "seen": {}, "injected": [], "ticks": 0, "actions_since_judge": 0}


def save_state(st: dict[str, Any]) -> None:
    (ATTN_DIR / "state.json").write_text(json.dumps(st, ensure_ascii=False))
    st["updated_at"] = now_iso()
    (ATTN_DIR / "block.md").write_text(render_block(st["block"], st["updated_at"]))


def log(kind: str, **kw: Any) -> None:
    with open(ATTN_DIR / "log.jsonl", "a") as f:
        f.write(json.dumps({"at": now_iso(), "kind": kind, **kw}, ensure_ascii=False) + "\n")


LIGHT_GLYPH = {"green": "●", "yellow": "◐", "red": "○"}
_NOISE_PREFIX = re.compile(r"^(Task [^ ]+ is [a-z_]+\.\s*|\[관찰·[a-z]+\]\s*)")


def clean_text(text: str, limit: int = 160) -> str:
    """사람이 읽을 한 줄: 기계 접두어를 떼고 첫 문장 단위로 자른다."""
    t = _NOISE_PREFIX.sub("", str(text or "")).strip().replace("\n", " ")
    if len(t) > limit:
        cut = t[:limit]
        for sep in ("。", ". ", "다.", "다 —", " — ", "; "):
            i = cut.rfind(sep)
            if i > limit // 2:
                cut = cut[: i + len(sep.rstrip())]
                break
        t = cut.rstrip() + "…"
    return t


def render_block(block: list[dict[str, Any]], updated_at: str | None = None) -> str:
    """블록의 사람용 서식. 훅·pi 둘 다 이 파일(block.md)을 그대로 쓴다.
    ● green 행동 근거 / ◐ yellow 행동 전 확인 / ○ red 참고. 줄 끝 ⟨tag⟩는 피드백용 짧은 손잡이."""
    if not block:
        return ""
    when = f" · 갱신 {updated_at[11:16]}Z" if updated_at else ""
    lines = [f"[기억 블록 {len(block)}줄{when} — 사이드카가 대화를 보며 고른 것. ● 근거 ◐ 확인 ○ 참고]"]
    for b in block:
        g = LIGHT_GLYPH.get(str(b.get("light", "yellow")), "◐")
        lines.append(f"{g} {clean_text(b['text'])} ⟨{b['id'].split(':')[-1][:4]}⟩")
    return "\n".join(lines)


# ── 빠른 루프 ────────────────────────────────────────────────────────────
def situation(tail: list[dict[str, Any]]) -> str:
    users = [t["text"] for t in tail if t["role"] == "user"][-3:]
    last_a = [t["text"] for t in tail if t["role"] == "assistant"][-1:]
    s = "\n".join(users + [a[:600] for a in last_a])
    return s[-TAIL_CHARS:]


def candidates(tail: list[dict[str, Any]], st: dict[str, Any], stats: dict[str, Any]) -> list[dict[str, Any]]:
    users = [t["text"] for t in tail if t["role"] == "user"]
    if not users:
        return []
    seen_ids = set(st["seen"]) | {b["id"] for b in st["block"]}
    pool: dict[str, dict[str, Any]] = {}
    for q in {users[-1][:400], situation(tail)[:800]}:
        for r in search(q, 40):
            if r.get("id") and r["id"] not in seen_ids:
                pool.setdefault(r["id"], r)
    def _own(r: dict[str, Any]) -> bool:                 # 자기 메아리 차단: 사이드카가 쓴 관찰은 후보가 아니다
        md = r.get("metadata") or {}
        return (isinstance(md, dict) and md.get("source") == "attention-sidecar") or str(r.get("memory", "")).startswith("[관찰·")
    ranked = A.rerank([r for r in pool.values() if not _own(r)], stats, exclude_machine=True)
    return ranked[:CANDIDATES]


# ── 중간 루프 ────────────────────────────────────────────────────────────
def _tail_text(tail: list[dict[str, Any]]) -> str:
    out = []
    for t in tail[-TAIL_TURNS:]:
        who = "정훈" if t["role"] == "user" else "에이전트"
        out.append(f"- {who}: {t['text'][:500]}")
    return "\n".join(out)[-TAIL_CHARS:]


def _cands_text(cands: list[dict[str, Any]]) -> str:
    return "\n".join(f"{i + 1}. [{str(c.get('created_at', ''))[:10]}] {str(c.get('memory', ''))[:200]}" for i, c in enumerate(cands))


def gate(tail: list[dict[str, Any]], cands: list[dict[str, Any]]) -> dict[str, Any]:
    """안다는 느낌: 후보 중 지금 대화에 쓸 게 있나. 낮으면 침묵."""
    prompt = (
        "너는 에이전트의 메타기억이다. 대화 꼬리를 읽고 후보 기억 중 **지금 이 대화에 실제로 쓸 것**이 있는지만 판단하라. "
        "주제가 같아 보여도 이미 대화에 나온 내용이거나 뻔한 것이면 없다고 하라. JSON만: {\"has\": true|false, \"conf\": 0~1, \"why\": \"한 문장\"}\n\n"
        f"대화 꼬리:\n{_tail_text(tail)}\n\n후보 기억:\n{_cands_text(cands)}"
    )
    return parse_json(llm(GATE_MODEL, prompt, GATE_TIMEOUT))


def judge(tail: list[dict[str, Any]], block: list[dict[str, Any]], cands: list[dict[str, Any]]) -> dict[str, Any]:
    block_txt = "\n".join(f"B{i + 1}. {b['text'][:200]}" for i, b in enumerate(block)) or "(비어 있음)"
    prompt = (
        "너는 에이전트의 기억 주의 프로세스다. 목표는 **정훈을 관찰하는 것**이다. 대화 꼬리, 현재 작업 블록, 후보 기억을 읽고 JSON만 답하라.\n"
        "규칙: 블록은 8줄 상한. 이미 대화에 나온 것·뻔한 것은 넣지 않는다. 지어내지 않는다 — add는 후보 번호(n)로만, drop은 현재 블록의 B번호로만(후보 번호를 drop에 쓰지 마라; 후보는 add하지 않으면 자동으로 버려진다). "
        "observe는 정훈이 이번 꼬리에서 **직접 말한** 것만: decision(정훈이 정한 것), rejection(정훈이 거부한 것), correction(정훈이 **에이전트를** 고친 것 — 에이전트가 정훈 말을 고친 건 아니다), preference(반복될 지속적 선호 — 순간 반응·감탄·«엥» 같은 건 아니다), fact(정훈이 알려준 사실). 원문을 짧게 인용하고 맥락 한 줄. 이미 블록·후보에 같은 관찰이 있으면 다시 쓰지 않는다. 확신 없으면 비운다. "
        "제외: 영어 지시문·시스템/스킬 문구·에이전트가 인용한 문서(정훈 말이 아니다), «진행해줘»·«응»·«그렇게 하자» 같은 승인 한마디(무엇을 정했는지 내용이 없으면 decision이 아니다), 욕설·감탄 한마디.\n"
        "출력: {\"add\":[{\"n\":후보번호,\"why\":\"…\"}], \"drop\":[\"B번호\"], \"gap\":\"에이전트가 모르는데 알아야 할 것 한 문장 또는 빈 문자열\", "
        "\"surprise\":0~1, \"observe\":[{\"kind\":\"decision|rejection|correction|preference|fact\",\"text\":\"정훈 원문 인용 + 맥락 한 줄\",\"conf\":0~1}]}\n\n"
        f"대화 꼬리:\n{_tail_text(tail)}\n\n현재 블록:\n{block_txt}\n\n후보 기억:\n{_cands_text(cands)}"
    )
    return parse_json(llm(JUDGE_MODEL, prompt, JUDGE_TIMEOUT))


def apply_judgement(st: dict[str, Any], cands: list[dict[str, Any]], j: dict[str, Any]) -> dict[str, Any]:
    added, dropped = [], []
    drop_idx = set()
    for b in j.get("drop") or []:
        m = re.match(r"B?(\d+)", str(b))
        if m:
            drop_idx.add(int(m.group(1)) - 1)
    st["block"] = [b for i, b in enumerate(st["block"]) if i not in drop_idx or dropped.append(b) ]
    for a in j.get("add") or []:
        try:
            c = cands[int(a.get("n")) - 1]
        except Exception:
            continue
        tr = c.get("trust") or {}
        light = tr.get("light") if isinstance(tr, dict) else (tr or "yellow")
        st["block"].append({"id": c["id"], "text": str(c.get("memory", ""))[:400], "light": light or "yellow",
                            "why": str(a.get("why", ""))[:120], "added_at": now_iso()})
        added.append(c["id"])
    # 상한: 오래된 것부터 민다
    while len(st["block"]) > BLOCK_MAX:
        dropped.append(st["block"].pop(0))
    for c in cands:
        st["seen"][c["id"]] = now_iso()          # 한 세션에 한 번만 제안
    return {"added": added, "dropped": [d["id"] for d in dropped if isinstance(d, dict)]}


def _recent_proposal_quotes(hours: int = 24) -> set[str]:
    p = ATTN_DIR / "proposals.jsonl"
    if not p.exists():
        return set()
    cutoff = time.time() - hours * 3600
    out: set[str] = set()
    for line in p.read_text().splitlines()[-500:]:
        try:
            d = json.loads(line)
            at = datetime.fromisoformat(str(d.get("at", "")).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        if at >= cutoff:
            out.add(re.sub(r"\s+", "", str(d.get("text", "")).split("-")[0].split("—")[0])[:40])
    return out


def record_observations(j: dict[str, Any], min_conf: float = 0.85) -> list[str]:
    """정훈의 결정·거부·정정만 원장에 남긴다. 에이전트 추론이므로 시스템이 yellow를 붙인다."""
    saved = []
    for o in j.get("observe") or []:
        kind, text, conf = str(o.get("kind", "")), str(o.get("text", "")).strip(), float(o.get("conf") or 0)
        if kind not in ("decision", "rejection", "correction", "preference") or conf < min_conf or len(text) < 12:
            continue
        if kind == "preference" and conf < 0.9:          # 한마디 감상은 선호가 아니다
            continue
        # 중복: 거의 같은 기억이 이미 있거나(검색 0.92+), 최근 24h 제안과 인용부가 같으면 건너뛴다
        top = search(text[:300], 3)
        if top and float(top[0].get("score") or 0) >= 0.92:
            continue
        quote = re.sub(r"\s+", "", text.split("-")[0].split("—")[0])[:40]
        if quote and quote in _recent_proposal_quotes():
            continue
        with open(ATTN_DIR / "proposals.jsonl", "a") as f:
            f.write(json.dumps({"at": now_iso(), **o}, ensure_ascii=False) + "\n")
        try:
            mcp("add_memory", {"text": f"[관찰·{kind}] {text}", "metadata": {"origin": "observed", "source": "attention-sidecar",
                                                                       "kind": kind, "conf": conf, "observed_at": now_iso()}}, timeout=60)
            saved.append(text[:80])
        except Exception as e:
            log("observe_error", error=str(e)[:200])
    return saved


# ── 한 틱 ───────────────────────────────────────────────────────────────
def tick(st: dict[str, Any], source: Path, force: bool = False, k_actions: int = 3, dry: bool = False) -> dict[str, Any]:
    if st.get("source") != str(source):
        st.update({"source": str(source), "offset": 0, "tail": [], "seen": {}, "injected": [], "actions_since_judge": 0})
    new, st["offset"] = read_turns(source, int(st.get("offset", 0)))
    st["tail"] = (st["tail"] + [t for t in new if t["role"] != "action"])[-TAIL_TURNS * 2:]
    st["ticks"] = st.get("ticks", 0) + 1
    new_user = any(t["role"] == "user" for t in new)
    st["actions_since_judge"] += sum(1 for t in new if t["role"] in ("assistant", "action"))
    if not new and not force:
        return {"status": "idle"}
    if not (new_user or st["actions_since_judge"] >= k_actions or force):
        return {"status": "wait", "new": len(new)}
    t0 = time.time()
    stats = A.load_stats()
    cands = candidates(st["tail"], st, stats)
    res: dict[str, Any] = {"status": "ticked", "new_turns": len(new), "cands": len(cands), "fast_s": round(time.time() - t0, 2)}
    if not cands:
        log("silence", reason="no candidates", **res)
        return res
    t1 = time.time()
    g = gate(st["tail"], cands)
    res["gate"] = g
    res["gate_s"] = round(time.time() - t1, 2)
    if not g.get("has") or float(g.get("conf") or 0) < 0.5:
        for c in cands[:4]:                                  # 상위 넷은 본 것으로 — 같은 걸 매 틱 다시 묻지 않게
            st["seen"][c["id"]] = now_iso()
        log("silence", **res)
        st["actions_since_judge"] = 0
        return res
    t2 = time.time()
    j = judge(st["tail"], st["block"], cands)
    res["judge"] = {k: j.get(k) for k in ("add", "drop", "gap", "surprise")}
    res["judge_s"] = round(time.time() - t2, 2)
    if not dry:
        res["edit"] = apply_judgement(st, cands, j)
        res["observed"] = record_observations(j)
    else:
        res["observe_preview"] = j.get("observe")
    st["actions_since_judge"] = 0
    log("judge", block_ids=[b["id"] for b in st["block"]], **{k: v for k, v in res.items() if k != "gate"})
    return res
