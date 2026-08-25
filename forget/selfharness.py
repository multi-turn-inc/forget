"""자기 하네스 H-0 — 골격: 기상 재수화 · 이력 소유 · 비용 가드 (헌장: docs/self-harness-design.md).

Tool Runner(client.beta.messages.tool_runner) 기반 자작 루프 — 개정 1의 채택안.
메시지 이력을 우리가 소유하므로(SQLite) 재시작은 죽음이 아니라 기상이다:
기상 절차 = forget 캡슐 + [전망] + 유언장(standing_hands) 재수화 → 직전
이력 복원 → 이어서 일한다. 연속성 충실도 계기(P-H-1)의 측정 지점은
wake_report가 만든다.

H-0 범위: 골격 + 수동 응고화 없음 + context_management 파라미터 배선만.
실행 비용 가드: 한 기상(run)당 상한 USD — 초과 시 루프를 정중히 끊는다.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import worldmodel

HARNESS_DB = os.environ.get(
    "MEM1_HARNESS_DB", str(Path.home() / ".forget" / "selfharness.sqlite3"))
FORGET_URL = os.environ.get("MEM1_HARNESS_FORGET_URL", "http://localhost:8000")
MODEL = os.environ.get("MEM1_HARNESS_MODEL", "claude-sonnet-5")
USER_ID = os.environ.get("MEM1_HARNESS_USER", "junghunkim")
COST_CAP_USD = float(os.environ.get("MEM1_HARNESS_COST_CAP", "2.0"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,              -- 'done' | 'cost_cap' | 'max_iterations' | 'killed'(무기록 사망)
    cost_usd REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS turns (
    run_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,   -- API 메시지 content 그대로 (이력 소유 = 재수화 자유)
    at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS wake_reports (
    run_id INTEGER NOT NULL,      -- 연속성 충실도 계기의 원자료: 기상마다 남긴다
    woke_at TEXT NOT NULL,
    resumed_run_id INTEGER,       -- 이어받은 직전 run (NULL = 신규)
    hands_inherited INTEGER NOT NULL,
    capsule_chars INTEGER NOT NULL,
    note TEXT
);
"""


def _open() -> sqlite3.Connection:
    Path(HARNESS_DB).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(HARNESS_DB)
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── 기상 재수화 ────────────────────────────────────────────────────────────

def fetch_capsule(query: str, budget_tokens: int = 900) -> str:
    """forget 캡슐 — 실패해도 기상은 계속된다 (fail-open, 밴드 규율과 동일)."""
    try:
        req = urllib.request.Request(
            f"{FORGET_URL}/v1/context/assemble/",
            data=json.dumps({
                "query": query, "filters": {"user_id": USER_ID},
                "budget_tokens": budget_tokens, "include_prospection": True,
                "record_trace": False, "disable_resume_workspace": True,
            }).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return str(json.loads(resp.read()).get("context") or "")
    except Exception:
        return ""


def build_wake_block(task: str, capsule: str, hands: list[dict[str, Any]],
                     resumed: bool) -> str:
    """기상 시스템 블록 — 힌트도 예산(L2-7): 캡슐+유언장+행동 규약만, 소량 고정."""
    lines = [
        "You are the forget self-harness agent — one continuous self whose canonical "
        "state lives OUTSIDE this context (forget ledger, world model, charter docs). "
        "This context window is an L1 cache: losing it loses performance, never identity.",
        f"\n## Current task\n{task}",
    ]
    if resumed:
        lines.append("\n(You are WAKING into an interrupted run — the prior turns "
                     "follow. Re-read them as your own; verify any standing intent "
                     "before acting on it.)")
    if capsule:
        lines.append(f"\n## State capsule (from forget)\n{capsule}")
    if hands:
        lines.append("\n## Standing hands (inherited intents — re-judge each: is its "
                     "'why' still true?)")
        for hand in hands:
            flag = " [EXPIRED — release or re-arm before relying on it]" if hand["expired"] else ""
            lines.append(f"- ({hand['kind']}) {hand['what']} — why: {hand['why']}{flag}")
    lines.append("\n## Discipline\n- Register adjudication lines before looking at "
                 "numbers.\n- Suspect the instrument first (raw responses, status "
                 "codes).\n- When done, call the `done` tool with a handover note "
                 "for the next wake.")
    return "\n".join(lines)


def wake(task: str, resume_run: int | None = None) -> dict[str, Any]:
    """기상 — 재수화 재료를 모으고 run 행을 연다. 반환물이 루프의 초기 상태."""
    conn = _open()
    try:
        prior_msgs: list[dict[str, Any]] = []
        if resume_run is not None:
            rows = conn.execute(
                "SELECT role, content_json FROM turns WHERE run_id=? ORDER BY seq",
                (resume_run,)).fetchall()
            prior_msgs = [{"role": r, "content": json.loads(c)} for r, c in rows]
        # 경로는 호출 시점 모듈 속성으로 — 기본 인자는 정의 시점 바인딩이라
        # 테스트 격리·런타임 교체가 안 먹는다 (전망 밴드에서 이미 밟은 함정).
        hands = worldmodel.standing_hands(worldmodel.DEFAULT_WORLD_DB)
        capsule = fetch_capsule(task)
        run_id = conn.execute(
            "INSERT INTO runs (task, started_at) VALUES (?, ?)",
            (task, _now())).lastrowid
        conn.execute(
            "INSERT INTO wake_reports (run_id, woke_at, resumed_run_id,"
            " hands_inherited, capsule_chars, note) VALUES (?,?,?,?,?,?)",
            (run_id, _now(), resume_run, len(hands), len(capsule),
             "resumed" if prior_msgs else "fresh"))
        conn.commit()
    finally:
        conn.close()
    return {
        "run_id": run_id,
        "system": build_wake_block(task, capsule, hands, resumed=bool(prior_msgs)),
        "messages": prior_msgs or [{"role": "user", "content": task}],
        "hands": hands,
    }


def record_turn(run_id: int, seq: int, role: str, content: Any) -> None:
    conn = _open()
    try:
        conn.execute("INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?)",
                     (run_id, seq, role, json.dumps(content, ensure_ascii=False), _now()))
        conn.commit()
    finally:
        conn.close()


def finish_run(run_id: int, reason: str, cost_usd: float) -> None:
    conn = _open()
    try:
        conn.execute("UPDATE runs SET ended_at=?, end_reason=?, cost_usd=? WHERE id=?",
                     (_now(), reason, round(cost_usd, 4), run_id))
        conn.commit()
    finally:
        conn.close()


def last_unfinished_run() -> int | None:
    """기상 시 이어받을 후보 — 끝맺음 없이 죽은 run (P-H-0의 강제 종료 시나리오)."""
    conn = _open()
    try:
        row = conn.execute(
            "SELECT id FROM runs WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# ── 비용 가드 ──────────────────────────────────────────────────────────────

# ── H-1 응고화: 증류 (헌장 개정 2, 대장 #20 구속) ─────────────────────────

# 경계는 ASCII 한정 — 유니코드 \b는 한글 조사에 붙은 핸들("4ba6a6f로",
# "2026-08-25에")을 놓친다. 핸들은 한국어 산문 속에 산다.
_HANDLE_RES = [
    ("url", r"https?://[^\s\"'\)\]]+"),
    ("path", r"(?:~|/|[A-Za-z_][\w.-]*/)[\w./\-]+\.\w{1,6}"),
    ("commit", r"(?<![0-9A-Za-z/])[0-9a-f]{7,10}(?![0-9A-Za-z/])"),
    ("date", r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)"),
    ("port_or_id", r"(?<![0-9A-Za-z])(?:run|task|loop|port)[- _:=]?[A-Za-z0-9]{2,12}"),
]


def extract_handles(text: str, cap: int = 40) -> list[dict[str, str]]:
    """행동 핸들 추출 — 결정론(정규식). 손실 응고는 집계 회상이 멀쩡한 채
    핸들을 지운다(대장 #20, 표본 1호=404 오염). 그래서 핸들은 LLM 요약이
    아니라 코드가 지킨다 — 구조는 코드, 내용은 LLM."""
    import re as _re
    out, seen = [], set()
    for kind, pattern in _HANDLE_RES:
        for m in _re.findall(pattern, text):
            val = m.rstrip(".,;")
            # 이미 잡힌 더 긴 핸들(URL 등)의 부분문자열은 파편 — 버린다
            if val in seen or any(val in h["value"] for h in out):
                continue
            seen.add(val)
            out.append({"kind": kind, "value": val})
            if len(out) >= cap:
                return out
    return out


def _local_distill_llm(prompt: str) -> str:
    """로컬 터널의 추론 서버로 증류 — E2EE 원칙(응고화도 로컬). 실패 시 빈 문자열."""
    url = os.environ.get("MEM1_HARNESS_DISTILL_URL",
                         "http://127.0.0.1:18812/v1/chat/completions")
    try:
        req = urllib.request.Request(url, data=json.dumps({
            "model": "qwen", "temperature": 0.0, "max_tokens": 700,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": prompt}],
        }).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            return str(json.loads(resp.read())["choices"][0]["message"]["content"] or "")
    except Exception:
        return ""


def distill_turns(turns: list[dict[str, Any]], llm=None) -> dict[str, Any]:
    """응고화 증류 v0 — 턴 묶음을 상태 레코드로 (잠들기 전의 소화).

    반환 스키마(헌장 개정 2): facts(판정·결정) · lessons(교훈) · intents
    (미완 의도 — 유언장 후보) · handles(결정론 추출, LLM 무관 항상 존재).
    LLM이 죽어도 핸들은 산다 — 그 역은 성립하지 않아도 된다.
    """
    raw = "\n".join(
        f"[{t.get('role')}] " + (t["content"] if isinstance(t.get("content"), str)
                                 else json.dumps(t.get("content"), ensure_ascii=False))
        for t in turns)[:24000]
    handles = extract_handles(raw)
    call = llm or _local_distill_llm
    text = call(
        "You are the consolidation organ of an agent's memory. From the transcript "
        "below, output ONLY a JSON object {\"facts\": [..], \"lessons\": [..], "
        "\"intents\": [..]} — facts = verdicts/decisions worth keeping (with their "
        "receipts inline), lessons = durable rules learned, intents = unfinished "
        "commitments the next wake must inherit. ≤6 items each, one sentence each. "
        "No prose outside JSON.\n\n<transcript>\n" + raw + "\n</transcript>")
    parsed: dict[str, Any] = {}
    if text:
        try:
            start, end = text.index("{"), text.rindex("}") + 1
            parsed = json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            parsed = {}
    return {
        "facts": [str(x) for x in (parsed.get("facts") or [])][:6],
        "lessons": [str(x) for x in (parsed.get("lessons") or [])][:6],
        "intents": [str(x) for x in (parsed.get("intents") or [])][:6],
        "handles": handles,
        "distilled_by": "llm" if parsed else ("none" if not text else "unparsed"),
    }


@dataclass
class CostGuard:
    """실행당 상한 — 초과 순간 루프를 정중히 끊는다 (상시 금지: 사이클 $2)."""
    cap_usd: float = COST_CAP_USD
    spent_usd: float = 0.0
    prices: dict[str, float] = field(default_factory=lambda: {
        # USD/M tok — Sonnet 5.1 프로모(~2026-08-31). 캐시 읽기 −90%.
        "in": 2.0, "out": 10.0, "cache_read": 0.2, "cache_write": 2.5,
    })

    def add_usage(self, usage: Any) -> float:
        get = (lambda k: float(getattr(usage, k, 0) or 0)) if not isinstance(usage, dict) \
            else (lambda k: float(usage.get(k) or 0))
        cost = (get("input_tokens") * self.prices["in"]
                + get("output_tokens") * self.prices["out"]
                + get("cache_read_input_tokens") * self.prices["cache_read"]
                + get("cache_creation_input_tokens") * self.prices["cache_write"]) / 1e6
        self.spent_usd += cost
        return cost

    @property
    def exceeded(self) -> bool:
        return self.spent_usd >= self.cap_usd
