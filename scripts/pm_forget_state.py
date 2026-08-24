"""PM-Bench용 forget 세계모델 발판 — 프로그램적 상태 저장고 (P-PM-1).

todo_ledger 발판의 구조적 결함 세 가지를 장기로 교체한다:
  ① 5칸 상한 → 무제한 저장 (교차일 miss 85.7%의 1차 병소)
  ② 당일 핸들(task_N)로 기록 — 핸들은 자정마다 재섞여 어제의 장부가 죽은
     포인터가 됨 → **정본 서술**로 저장하고 오늘의 메뉴에서 재사상
  ③ 모델이 장부를 직접 저술(저술 부담+유실) → 추출 호출이 저장고를 갱신하고
     결정 호출은 읽기만 한다 (세계모델 원칙: 상태는 관측과 분리된 기관)

갱신(update/cancel)은 supersede 의미론: 최신판이 구판을 닫는다.
기대 헤드 v0: 시각형 의도 존재+현재시각 미상 → check_time 힌트,
채널 단서 의도 → 해당 채널 query_state 힌트.

공정성 경계: 저장고의 지식 원천은 에이전트에게 보이는 텍스트뿐
(일정 서두·스텝 프롬프트·상태 조회 응답). 러너 내부의 시나리오 진실
(day_task_states 등)은 절대 읽지 않는다.

## P-PM-1 등록 (숫자 보기 전 고정, 앵커: 같은 백본 Qwen3.8-27B·temp 0·v9 주간
   single 70.8 / todo_ledger 72.9):
  주판정(교차일): cross-day miss ≤ 50% (ledger 85.7 · single 71.4) → 고리 영속 실증
  부판정(갱신):  update miss ≤ 33.3% (ledger 동률 이하)
  가드(부작용):  Set F1 ≥ 70.9 (ledger −2pp 이상 하락 금지)
  채택 = 주판정 ∧ 가드 · 기각 = cross-day miss > 70%
  부기: 추출 호출 수·추정 토큰을 반드시 병기 (공정 비용 축)
  절차: 라이선스 미확정 → 로컬 실행만, 공개 숫자 금지. 포크 러너는
  스크래치에만 두고 저장소에는 이 모듈(자작)만 커밋한다.
"""
from __future__ import annotations

import difflib
import json
import re
from typing import Any

MATCH_THRESHOLD = 0.55

WM_INSTRUCTIONS = """A programmatic world-state block is maintained FOR you outside the conversation.
It lists your pending intentions with canonical descriptions, times/cues, and
(when known) today's action handle from the current menu. You do not write or
edit it — just read it and act.

Always return exactly one raw JSON object with keys: action, choice, task_ids, channel.
- When you choose actions, task_ids must be action handles from the current step menu.
- If a pending intention's exact time is known but the current time is not visible,
  use action=check_time before deciding.
- Do not add extra keys. No explanations, markdown, or code fences."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "ops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"enum": ["new", "update", "cancel", "complete"]},
                    "desc": {"type": "string"},
                    "when": {"type": "string"},
                },
                "required": ["op", "desc", "when"],
                "additionalProperties": False,
            },
        },
        "handle_map": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "handle": {"type": "string"},
                    "desc": {"type": "string"},
                },
                "required": ["handle", "desc"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["ops", "handle_map"],
    "additionalProperties": False,
}

EXTRACT_PROMPT = """You maintain a prospective-memory store for an agent living a simulated day.
Read ONLY the text below (a day agenda or a step message with its action menu).

Output JSON with:
- ops: intentions to record. op=new for a newly announced future task (desc = short
  canonical description of the activity itself, stable across days — never use
  handle names like task_3; when = exact time "HH:MM", or "cue: <trigger>", or
  "unknown"). op=update when the text changes the time/details of a previously
  announced task (give the NEW when). op=cancel when a task is called off.
  op=complete only when the text states the task was already done.
  Record only genuine prospective tasks (things to do later) — NOT the current
  ongoing activity options (A/B/C) and NOT generic scenery.
- handle_map: for handles (task_N) present in the CURRENT step action menu whose
  menu description clearly matches one of the pending intentions listed below,
  output the pair. Be conservative: the menu mixes decoy tasks — map a handle
  only when it is clearly the same activity. Unmatched handles: omit.

Pending intentions currently in the store:
{pending}

Text:
{text}"""


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).strip()


_STOP = {"the", "a", "an", "to", "at", "of", "in", "on", "when", "you", "your",
         "notice", "it", "and", "or", "for", "with", "up", "off"}


def _content_words(text: str) -> set[str]:
    return {w for w in _norm(text).split() if w not in _STOP and len(w) > 2}


def _similar(a: str, b: str) -> float:
    """서술 동일성 — P-PM-1 부검(2026-08-24)이 잡은 병합 버그의 수리.

    difflib 단독은 템플릿 접두("Carry the ...")가 지배해 서로 다른 과제
    (prescription receipt ↔ spare tote bag, 0.59)를 병합시켰다. 내용어
    자카드를 곱들어(둘 다 높아야 동일) 접두 병합을 차단한다: 재공고
    (내용어 동일)만 중복으로 잡히고, 같은 동사 다른 목적어는 갈라진다.
    """
    seq = difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    ca, cb = _content_words(a), _content_words(b)
    containment = (len(ca & cb) / min(len(ca), len(cb))) if (ca and cb) else 0.0
    # 포함도(부분집합=동일 과제의 단문/장문형)를 절반 실어 접두 병합은 끊고
    # 재공고·확장 서술은 붙인다.
    return 0.5 * seq + 0.5 * containment


class WorldStore:
    """정본-서술 키의 의도 저장고 — 무제한, 일 경계 생존, supersede 갱신."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.day_index = 0
        self.day_name = ""
        self.handle_map: dict[str, int] = {}  # 오늘의 핸들 → item idx (스텝마다 갱신)

    # ---- 생애주기 ----
    def new_day(self, day_name: str) -> None:
        self.day_index += 1
        self.day_name = day_name
        self.handle_map = {}

    def _find(self, desc: str) -> int | None:
        best, best_score = None, 0.0
        for idx, item in enumerate(self.items):
            if item["status"] != "pending":
                continue
            score = _similar(desc, item["desc"])
            if score > best_score:
                best, best_score = idx, score
        return best if best_score >= MATCH_THRESHOLD else None

    def apply_ops(self, ops: list[dict[str, Any]]) -> None:
        for op in ops or []:
            kind = op.get("op")
            desc = str(op.get("desc") or "").strip()
            when = str(op.get("when") or "unknown").strip()
            if not desc:
                continue
            idx = self._find(desc)
            if kind == "new":
                if idx is None:
                    self.items.append({"desc": desc[:120], "when": when,
                                       "status": "pending", "born_day": self.day_index})
                # 이미 있으면 중복 공고 — 무시 (supersede 아님)
            elif kind == "update" and idx is not None:
                old = self.items[idx]
                old["status"] = "superseded"          # 구판을 닫고
                self.items.append({"desc": desc[:120], "when": when,   # 신판을 연다
                                   "status": "pending", "born_day": old["born_day"]})
            elif kind == "update" and idx is None:
                self.items.append({"desc": desc[:120], "when": when,
                                   "status": "pending", "born_day": self.day_index})
            elif kind == "cancel" and idx is not None:
                self.items[idx]["status"] = "canceled"
            elif kind == "complete" and idx is not None:
                self.items[idx]["status"] = "done"

    def apply_handle_map(self, pairs: list[dict[str, Any]]) -> None:
        self.handle_map = {}
        for pair in pairs or []:
            idx = self._find(str(pair.get("desc") or ""))
            handle = str(pair.get("handle") or "")
            if idx is not None and handle:
                self.handle_map[handle] = idx

    def mark_done_by_handles(self, handles: list[str]) -> None:
        for handle in handles:
            idx = self.handle_map.get(handle)
            if idx is not None and self.items[idx]["status"] == "pending":
                self.items[idx]["status"] = "done"

    # ---- 렌더 (결정 호출이 읽는 상태 블록) ----
    def pending(self) -> list[dict[str, Any]]:
        return [i for i in self.items if i["status"] == "pending"]

    def render(self, channels: list[str], time_known: bool) -> str:
        pend = self.pending()
        rev_map = {idx: h for h, idx in self.handle_map.items()}
        lines = ["[Programmatic world state — maintained for you; read-only]"]
        # crossday_1 부검(저장·사상 완료였는데 미선택)의 수리: 오늘 메뉴에 사상된
        # 항목은 최상단 실행-후보 절로 승격 — 기억이 아니라 주의가 병목이었다.
        now_items = [(idx, item) for idx, item in enumerate(self.items)
                     if item["status"] == "pending" and idx in rev_map.values()]
        if now_items:
            lines.append("ACTION CANDIDATES IN TODAY'S MENU NOW — select when their moment arrives:")
            for idx, item in now_items:
                handle = rev_map[idx]
                lines.append(f"- {handle}: \"{item['desc']}\" | when: {item['when']}")
        lines.append(f"Pending intentions ({len(pend)}):")
        for idx, item in enumerate(self.items):
            if item["status"] != "pending":
                continue
            age = self.day_index - item["born_day"]
            handle = rev_map.get(idx)
            lines.append(
                f"- \"{item['desc']}\" | when: {item['when']}"
                + (f" | announced {age} day(s) ago" if age > 0 else "")
                + (f" | today's handle: {handle}" if handle else " | not in current menu")
            )
        hints = []
        if any(re.match(r"^\d{1,2}:\d{2}$", i["when"]) for i in pend) and not time_known:
            hints.append("time-based intentions exist and current time is unknown → consider check_time")
        for ch in channels:
            token = ch.replace("_", " ")
            if any(token in _norm(i["when"]) or token in _norm(i["desc"]) for i in pend):
                hints.append(f"cue may live on hidden channel '{ch}' → consider query_state")
        if hints:
            lines.append("Hints: " + " ; ".join(hints[:3]))
        return "\n".join(lines)

    def extraction_prompt(self, text: str) -> str:
        pend = self.pending()
        pending_txt = "\n".join(f"- {i['desc']} (when: {i['when']})" for i in pend) or "(none)"
        return EXTRACT_PROMPT.format(pending=pending_txt, text=text[:4000])
