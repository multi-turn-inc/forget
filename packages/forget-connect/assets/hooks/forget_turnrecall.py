#!/usr/bin/env python3
"""UserPromptSubmit hook: push-recall memories relevant to THIS turn.

The session-start capsule covers "where were we"; this covers "wait, we know
something about that" mid-session — the pull-only problem's other half. The
main context window is the scarcest resource, so the gate is strict:

- silence unless the top hit clears a relevance threshold
- a memory is offered at most once per session (repeat-suppression ledger)
- memories already offered in the session-start capsule are not re-offered
- the injection is an OFFER with trust lights; adoption stays the
  main-thread agent's judgment
- fail-open, hard 5s timeout: forget being down must never slow a turn

body A1+A2 (2026-08-06): per-turn traces landed server-side — the search
carries trace=turn_recall, the injection footer prints the trace_id, and
the agent's record_context_outcome habit finally has an address. The pick
gate also reads score_breakdown.vector: a hit that matches only lexically
("프로토타입" pulling three unrelated prototypes, measured today) is noise
the semantic floor now drops.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forget_project import layered_filter, project_key_for_path, scope_disabled, wants_cross_project  # noqa: E402

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
SCORE_THRESHOLD = float(os.environ.get("FORGET_TURNRECALL_THRESHOLD", "0.45"))
# 의미 바닥: 임베딩 성분의 절대 하한 (2차 가드 — 이 레짐에선 코사인이
# 0.87~0.91 띠에 포화돼 판별력이 약함을 실측으로 확인).
SEMANTIC_FLOOR = float(os.environ.get("FORGET_TURNRECALL_SEMANTIC_FLOOR", "0.30"))
# body A2의 실제 수술 (진단 정정 2026-08-06): 판별력은 절대값이 아니라
# 분포의 모양에 있다. 진짜 관련 질의는 봉우리를 만들고(top1-중앙값
# 0.054 실측), 소음 질의는 평지다(0.014 — "프로토타입" 3건 유출 사례).
# 평지면 이 턴은 기억을 고르지 못한 것 — 침묵이 정답.
FLATNESS_MARGIN = float(os.environ.get("FORGET_TURNRECALL_MARGIN", "0.03"))
# Conflict-zone members get a looser gate: missing a plain recall costs
# silence, but missing a corrected-zone alert is how incident #1 happened —
# and being part of a supersede pair is itself strong prior evidence the
# zone matters. Recalibrate both when the embedder switches to e5.
CONFLICT_THRESHOLD = float(os.environ.get("FORGET_CONFLICT_THRESHOLD", "0.32"))
MAX_RECALLS = 3
MEMORY_CHAR_LIMIT = 160
MIN_PROMPT_LEN = 8


def _rpc(name: str, arguments: dict, timeout: int = 5) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(
        FORGET_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(request, timeout=timeout).read())
    return json.loads(body["result"]["content"][0]["text"])


def _conflict_pair(item: dict) -> tuple[str, str] | None:
    """(old_id, new_id) if this memory sits in a supersede pair, else None.

    Retro-scoring incident #1 (2026-07-23) showed direction is not measurable
    in embedding space — old and corrected versions sit nearly parallel
    (negation-blindness). But *territory* separates perfectly (100% vs 3%
    false positives). So geometry only detects entry into a corrected zone;
    judging which version to act on is delegated to the reading LLM, which
    handles negation natively.
    """
    metadata = item.get("metadata") or {}
    memory_id = str(item.get("id") or "")
    successor = str(metadata.get("superseded_by") or "")
    if successor:
        return (memory_id, successor)
    supersedes = metadata.get("supersedes")
    if isinstance(supersedes, list) and supersedes:
        return (str(supersedes[0]), memory_id)
    return None


def _injection_eligible(item: dict) -> bool:
    """Could this candidate ever be offered as a plain turn recall?

    Mirrors the structural drops in main()'s pick loop — the ones that hold
    regardless of score: capture pointers, task_state ledger rows, and
    supersede pairs (which travel the conflict path instead). Only these
    candidates may shape the flatness distribution; letting an ineligible
    item be the peak means the peak-detector measures something it can
    never surface.
    """
    metadata = item.get("metadata") or {}
    if metadata.get("hook"):
        return False
    if metadata.get("assertion_kind") == "task_state":
        return False
    if _conflict_pair(item):
        return False
    return True


def _seen_ids(session_id: str) -> tuple[set[str], str]:
    seen: set[str] = set()
    offer_path = os.path.join(STATE_DIR, f"{session_id}.json")
    for candidate in (offer_path, offer_path + ".done"):
        if os.path.exists(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    seen.update(json.load(fh).get("memory_ids") or [])
            except Exception:
                pass
    turns_path = os.path.join(STATE_DIR, f"{session_id}.turns.json")
    if os.path.exists(turns_path):
        try:
            with open(turns_path, encoding="utf-8") as fh:
                seen.update(json.load(fh).get("injected") or [])
        except Exception:
            pass
    return seen, turns_path


def _remember_injected(turns_path: str, injected: list[str]) -> None:
    existing: list[str] = []
    if os.path.exists(turns_path):
        try:
            with open(turns_path, encoding="utf-8") as fh:
                existing = json.load(fh).get("injected") or []
        except Exception:
            pass
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(turns_path, "w", encoding="utf-8") as fh:
        json.dump({"injected": existing + injected}, fh, ensure_ascii=False)


def main() -> None:
    hook_input = json.load(sys.stdin)
    prompt = str(hook_input.get("prompt") or "").strip()
    session_id = str(hook_input.get("session_id") or "").strip()
    if len(prompt) < MIN_PROMPT_LEN or prompt.startswith(("/", "!", "<", "#")):
        return
    seen, turns_path = _seen_ids(session_id) if session_id else (set(), "")
    # Project boundary = privacy boundary: the other company's strategy must
    # not surface mid-session here just because the words rhyme. Crossing is
    # possible, but only when the user asks for it — and it says so when it does.
    project = None if scope_disabled() else project_key_for_path(hook_input.get("cwd") or os.getcwd())
    crossed = bool(project) and wants_cross_project(prompt)
    # Per-turn ambient recall stays on the instant path — the recall dial is
    # the user's explicit choice, not a tax on every keystroke.
    search_args: dict = {
        "query": prompt[:300],
        "top_k": MAX_RECALLS + 2,
        "recall": "low",
        "trace": "turn_recall",      # body A1: 피드백이 붙을 주소를 만든다
        "score_breakdown": True,     # body A2: 의미/어휘 성분 분리
    }
    if project and not crossed:
        search_args["filters"] = layered_filter(project)
    result = _rpc("search_memories", search_args)
    trace_id = str(result.get("trace_id") or "")
    # 평탄도는 **주입 자격이 있는 후보**에서만 재야 한다 (c62 실측 수리).
    # 이전 판본은 배제 이전의 전체 결과로 분포를 재서, 봉우리가 결코 주입될 수
    # 없는 항목(task_state claim·capture 포인터)일 수 있었다. 실측: 축자 동일한
    # 질의의 두 런이 하위 4개 점수는 완전히 같은데 top1(양쪽 다 task_state
    # claim)만 0.9172 vs 1.0000으로 갈려 주입 0 vs 3이 됐다 — 방금 쓴 claim은
    # 1.0으로 포화하므로 푸시 회상의 on/off가 장부 신선도에 결합돼 있었다.
    scores_all = sorted(
        (float(item.get("score") or 0.0)
         for item in result.get("results") or []
         if _injection_eligible(item)),
        reverse=True,
    )
    flat_distribution = (
        len(scores_all) >= 4
        and (scores_all[0] - scores_all[len(scores_all) // 2]) < FLATNESS_MARGIN
    )
    picks = []
    conflict_pairs: dict[tuple[str, str], None] = {}
    for item in result.get("results") or []:
        score = float(item.get("score") or 0.0)
        memory_id = str(item.get("id") or "")
        if not memory_id or memory_id in seen:
            continue
        metadata = item.get("metadata") or {}
        if metadata.get("hook"):
            continue  # session-capture pointers are for rehydration, not recall
        if metadata.get("assertion_kind") == "task_state":
            # Fluid-layer task ledger rows travel via get_task_state/capsule
            # only; surfacing them as turn recalls is friction F2's C2 cause
            # (long claim texts farm phrase_bonus regardless of topic).
            continue
        pair = _conflict_pair(item)
        if pair:
            if score >= CONFLICT_THRESHOLD:
                conflict_pairs.setdefault(pair)
            continue  # presented as a pair below, not as a plain recall
        if score < SCORE_THRESHOLD:
            continue
        if flat_distribution:
            continue  # 평지 분포 = 이 질의는 기억을 고르지 못함 (충돌지대는 별도 경로로 통과)
        breakdown = item.get("score_breakdown") or {}
        vector_score = breakdown.get("vector")
        if vector_score is not None and float(vector_score) < SEMANTIC_FLOOR:
            continue
        trust = item.get("trust") or {}
        light = str(trust.get("light") or "yellow")
        picks.append((memory_id, light, str(item.get("memory") or "")[:MEMORY_CHAR_LIMIT]))
        if len(picks) >= MAX_RECALLS:
            break

    conflicts = []
    for old_id, new_id in list(conflict_pairs)[:2]:
        if old_id in seen and new_id in seen:
            continue
        try:
            old = _rpc("get_memory", {"memory_id": old_id})
            new = _rpc("get_memory", {"memory_id": new_id})
        except Exception:
            continue
        conflicts.append((old_id, new_id, str(old.get("memory") or "")[:MEMORY_CHAR_LIMIT], str(new.get("memory") or "")[:MEMORY_CHAR_LIMIT]))

    if not picks and not conflicts:
        return  # below threshold or nothing new → silence
    lines = []
    if conflicts:
        lines.append("[forget 충돌지대 — 이 주제엔 정정 이력이 있음. 현재본 기준으로 행동하고, 구본 위에서 행동하지 말 것]")
        for _, _, old_text, new_text in conflicts:
            lines.append(f"- (현재) {new_text}")
            lines.append(f"- (red/구본) {old_text}")
    if picks:
        header = "[forget 회상 — 이 턴과 관련된 기억 제안. green=행동 근거 OK, yellow=행동 전 확인, red=참고만"
        header += " / 프로젝트 경계를 넘어 검색함]" if crossed else "]"
        lines.append(header)
        lines += [f"- ({light}) {memory}" for _, light, memory in picks]
    if trace_id:
        lines.append(
            f"[피드백 주소: 이 회상이 명확히 도움/소음이면 record_context_outcome(trace_id=\"{trace_id}\") 한 번]"
        )
    print("\n".join(lines))
    if session_id and turns_path:
        injected = [memory_id for memory_id, _, _ in picks]
        ledger_picks = list(picks)
        for old_id, new_id, old_text, new_text in conflicts:
            injected += [old_id, new_id]
            ledger_picks.append((new_id, "green", new_text))  # 메아리 측정은 현재본 기준
        _remember_injected(turns_path, injected)
        _extend_offer_ledger(session_id, ledger_picks)


def _extend_offer_ledger(session_id: str, picks: list) -> None:
    """Feed turn recalls into the outcome flywheel: append their probes and
    ids to the session's offer ledger so the capture hook measures them too.
    (Discovered gap 07-22: a session answered purely from a turn recall and
    the capsule-only labeler scored it "not used".)"""
    ledger_path = os.path.join(STATE_DIR, f"{session_id}.json")
    if not os.path.exists(ledger_path):
        return  # no capsule trace this session — nothing to record against
    try:
        with open(ledger_path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["memory_ids"] = list({*(state.get("memory_ids") or []), *(memory_id for memory_id, _, _ in picks)})
        state["capsule_lines"] = (state.get("capsule_lines") or []) + [memory[:80] for _, _, memory in picks]
        with open(ledger_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
