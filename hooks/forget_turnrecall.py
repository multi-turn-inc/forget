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
- one more offer rides along (c79, rolling consolidation ③): when the digest
  hook estimates context usage near the compaction threshold, a single line
  suggests rebooting over compacting — once per episode, never forced
- 턴-유형 게이트 (2026-08-10): layer:self 격언은 구조적으로 제외하고,
  대화-국소 신호는 검색 전에 침묵하며, 기억-의존 신호는 recall 기어를
  low→high로 승격한다. 참조 대상이 세션 대화 꼬리에 이미 있으면 침묵
  (conversation-first). FORGET_TURNRECALL_GATE=off가 게이트·승격을 끄는
  대조 경로. 결정은 state/turnrecall_gate.jsonl에 남는다(주입률 분모).

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
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forget_project import layered_filter, project_key_for_path, scope_disabled, wants_cross_project  # noqa: E402

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
# 0.45 → 0.33 (2026-08-23, 다국어 mpnet 전환 실측): 새 공간의 합성 점수 대역이
# 내려앉았다 — 관련 질의 상위 0.40~0.46, 무관 바닥 0.28. 구 문턱 0.45는 구 공간
# (무관조차 0.51 바닥)에선 전부 통과시키는 장식이었지만 새 공간에선 관련 픽을
# 반쯤 자른다. 허브성 오탐(무관인데 벡터 0.8)은 이 문턱이 아니라 평탄도 게이트가
# 잡는다 — 실측: 스포츠 무관 질의 프로필 간격 0.02 < MARGIN 0.03 → 침묵.
SCORE_THRESHOLD = float(os.environ.get("FORGET_TURNRECALL_THRESHOLD", "0.33"))
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
# c63: 인출 깊이와 주입 후보 집합을 분리한다. 평탄도 분포를 **자격 후보에서만**
# 재기 때문에 최소 개수 조건도 자격 수로 세는데, 깊이가 5뿐이면 무자격 후보
# (task_state claim·capture 포인터·충돌쌍) 2개로 자격이 3개까지 떨어져 게이트가
# 한 마디 없이 전면 정지한다. 점수는 결과 집합 크기에 불변임을 실측 확인했으므로
# (실제 turn_recall 질의 20건, 깊이 5 대 10에서 상위 5개 (id,score) 20/20 동일,
# spread 변화 0건 — c63_depth_invariance.py) 깊이 인상은 자[尺]를 바꾸지 않는다.
CANDIDATE_TOP_K = MAX_RECALLS + 7   # 분포 표본용 여유분까지 인출
PICK_POOL = MAX_RECALLS + 2         # 주입·충돌 후보 집합은 종전과 동일 (입력 집합 불변)
FLATNESS_WINDOW = MAX_RECALLS + 2   # 창을 고정해 중앙값 위치를 보존 (len//2는 4·5 모두 2)
FLATNESS_MIN_SAMPLES = 4
MEMORY_CHAR_LIMIT = 160
MIN_PROMPT_LEN = 8

# ── 턴-유형 게이트 (2026-08-10, 3연속 소음 사건의 처치) ─────────────────────
# 소음 해부(트레이스 selection_failure 3건): 2/3은 layer:self 격언이 어휘
# 인접으로 유출(self는 캡슐 "자기:" 라인이라는 전용 채널이 이미 있다), 1/3은
# 대화 안에서 이미 충족되는 질문("계획이 뭐였더라")에 타 맥락 기억이 응답.
# 게이트는 검색 **전에** 턴의 유형을 읽는다:
#   기억-의존 신호("예전에"·"지난번"·세션에 없는 고유명 등) → 진행 +
#     recall low→high 승격 (적응형 기어 — 2026-08-10 정훈 승인 방향)
#   대화-국소 신호(지시대명사·절차 질문) → 검색 없이 침묵
#   참조 대상이 세션 대화 꼬리에 전부 있음 → 침묵 (conversation-first)
# FORGET_TURNRECALL_GATE=off 가 게이트·승격을 끈다 (전후 비교용 대조 경로).
# self 제외는 게이트가 아니라 설계 규칙이므로 대조 경로에서도 유지된다.
GATE_ENV = "FORGET_TURNRECALL_GATE"
TRANSCRIPT_TAIL_BYTES = 60_000  # 대화 꼬리 읽기 상한 — 세션이 커져도 상수 비용

_MEMORY_SIGNAL_RE = re.compile("|".join((
    r"예전",
    r"지난\s*번",
    r"저번",
    r"원래\s*(?:계획|하기로|하려|정했)",
    r"전에\s*(?:말했|얘기했|정했|결정했|했었|하기로|하던)",
    r"그때\s*(?:내가|우리가|정했|말했|했던|하던)",
    r"(?:내|제|우리)가\s*(?!아까|방금)[^\n.?!]{0,24}(?:라고\s*했|라고\s*말했|했다고|하자고\s*했|말했|정했|결정했|골랐|시켰)",
    r"(?:말했|정했|결정했|논의했|얘기했|합의했)던",
    r"기로\s*했",  # 결정-회상형: "…기로 했지/했잖아" — c104, 게이트가 핀 테스트 2건을 삼킨 수리
    r"기억\s*(?:나|안\s*나|하|해|있|남)",
    r"뭐라고\s*(?:했|말했|그랬)",
    r"\bremember\b|\brecall\b",
    r"\blast\s+(?:time|session|week)\b",
    r"\bpreviously\b|\bback\s+then\b",
    r"\bwe\s+(?:said|decided|agreed|discussed)\b",
    r"\b(?:i|you)\s+(?:told|asked|mentioned|said|decided)\b",
)), re.IGNORECASE)

_LOCAL_SIGNAL_RE = re.compile("|".join((
    r"이거|그거|저거|이것|그것|저것|이게|그게|저게|이건|그건|저건|이걸|그걸|저걸",
    r"(?:이|그|저)\s(?:코드|파일|함수|부분|줄|에러|오류|버그|테스트|결과|로그|출력|화면|문장|단락|목록|커밋|브랜치|폴더|디렉토리)",
    r"방금|아까|바로\s*(?:위|앞|전)|위에서|여기\s*(?:서|에)",
    # '어떻게'는 절차형만 국소다 — "어떻게 됐/되고 있"(결과 회상)은 게이트를 넘어
    # coverage/점수가 판단한다 (c104: bare '어떻게'가 "H100 어떻게 되고 있어?"를 침묵시킨 실측).
    r"어떻게\s*(?:하|해|할|합|사용|쓰|만드|만들|짜|고치|설치|실행|돌리|동작|작동)",
    r"설명\s*(?:해|좀|부탁)",
    r"뭐\s*(?:였|랬)?더라",
    r"무슨\s*(?:뜻|말|의미)",
    r"왜\s*안\s*(?:되|돼)",
    r"\bhow\s+(?:do|does|can|to)\b|\bexplain\b|\bwhat\s+does\b",
    r"\bthis\s+(?:code|file|function|error|line|test|output)\b",
)), re.IGNORECASE)

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]+|[가-힣]{2,}|[0-9]{2,}")

# 질문·요청의 뼈대 어휘 — 참조 **대상**이 아니므로 coverage 계산에서 뺀다.
_STOPWORDS = {
    "그리고", "그런데", "근데", "그래서", "하지만", "그럼", "그러면", "이제", "지금",
    "오늘", "내일", "어제", "우리", "내가", "제가", "네가", "니가",
    "이거", "그거", "저거", "이건", "그건", "저건", "이게", "그게", "저게",
    "이걸", "그걸", "저걸", "이것", "그것", "저것", "여기", "저기", "거기",
    "뭐야", "뭐지", "뭐냐", "뭐였지", "뭐였더라", "뭐더라", "무엇", "무슨",
    "어떤", "어떻게", "어디", "언제", "누가", "누구", "얼마나",
    "해줘", "해봐", "해라", "하자", "해주세요", "주세요", "부탁", "부탁해",
    "다시", "한번", "계속", "먼저", "같이", "말고", "말이야",
    "설명", "설명해", "설명해줘", "알려줘", "알려", "알아봐", "알아봐줘",
    "말해줘", "보여줘", "확인", "확인해", "확인해줘", "정리", "정리해", "정리해줘",
    "있어", "없어", "있는", "없는", "하는", "했던", "해서", "하면", "하고",
    "해도", "할까", "될까", "되나", "됐다", "됐어",
    "아니", "아니야", "맞아", "맞지", "그래", "그렇게", "이렇게", "저렇게",
    "the", "a", "an", "and", "or", "but", "for", "with", "from", "this", "that",
    "these", "those", "what", "which", "how", "why", "when", "where", "who",
    "please", "can", "could", "should", "would", "will", "do", "does", "did",
    "is", "are", "was", "were", "be", "been", "it", "its", "in", "on", "at",
    "to", "of", "my", "our", "your", "me", "we", "you", "not", "no", "yes",
    "ok", "okay", "let", "lets", "just", "now", "then", "explain", "show",
    "tell", "check", "fix", "run", "use", "make", "add", "update", "help",
}


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
    regardless of score: capture pointers, task_state ledger rows, self-layer
    maxims, and supersede pairs (which travel the conflict path instead). Only
    these candidates may shape the flatness distribution; letting an
    ineligible item be the peak means the peak-detector measures something it
    can never surface.
    """
    metadata = item.get("metadata") or {}
    if metadata.get("hook"):
        return False
    if metadata.get("assertion_kind") == "task_state":
        return False
    if str(metadata.get("layer") or "").lower() == "self":
        return False
    if _conflict_pair(item):
        return False
    return True


def _gate_off() -> bool:
    return str(os.environ.get(GATE_ENV, "")).strip().lower() in {"0", "off", "false"}


def _transcript_tail(path: str) -> str:
    """세션 대화 꼬리의 텍스트(소문자). 못 읽으면 "" — 게이트는 증거 없이 안 움직인다."""
    if not path:
        return ""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            offset = max(0, size - TRANSCRIPT_TAIL_BYTES)
            fh.seek(offset)
            blob = fh.read().decode("utf-8", "replace")
    except Exception:
        return ""
    lines = blob.splitlines()
    if offset and lines:
        lines = lines[1:]  # seek 절단으로 깨진 첫 줄은 버린다
    texts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        _collect_text(entry, texts)
    return "\n".join(texts).lower()


def _collect_text(node, out: list[str], depth: int = 0) -> None:
    """중첩 어디에 있든 "text" 값과 문자열 content를 긁는다 (tool_result 포함)."""
    if depth > 8:
        return
    if isinstance(node, dict):
        text = node.get("text")
        if isinstance(text, str):
            out.append(text)
        content = node.get("content")
        if isinstance(content, str):
            out.append(content)
        for value in node.values():
            if isinstance(value, (dict, list)):
                _collect_text(value, out, depth + 1)
    elif isinstance(node, list):
        for value in node:
            _collect_text(value, out, depth + 1)


def _salient_tokens(prompt: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(prompt[:400]):
        if token.lower() in _STOPWORDS or token in tokens:
            continue
        tokens.append(token)
        if len(tokens) >= 24:
            break
    return tokens


def _found_in_text(token: str, text: str) -> bool:
    """조사·어미가 붙은 한국어 토큰은 앞에서부터 줄여가며 어간 일치를 본다."""
    low = token.lower()
    if low in text:
        return True
    if re.fullmatch(r"[가-힣]+", token):
        for cut in range(len(token) - 1, 1, -1):
            if token[:cut] in text:
                return True
    return False


def _proper_like(token: str) -> bool:
    """세션에 없으면 기억-의존을 시사하는 고유명꼴: 대문자/숫자 섞인 라틴 토큰."""
    return bool(re.search(r"[A-Za-z]", token)) and bool(re.search(r"[A-Z0-9]", token))


def _classify_turn(prompt: str, transcript_path: str, crossed: bool) -> tuple[str, str | None]:
    """(gate, gear). gear None = 검색 없이 침묵.

    우선순위: 기억-의존 신호(명시적 과거 호출·프로젝트 경계 넘기 요청)가
    대화-국소 신호를 이긴다 — "지난번에 정한 거 설명해줘"는 기억 질문이다.
    꼬리를 못 읽으면(첫 턴·비표준 호출자) coverage/novelty는 판단하지 않는다
    — 증거 없는 침묵도, 증거 없는 승격도 하지 않는 fail-open.
    """
    if crossed or _MEMORY_SIGNAL_RE.search(prompt):
        return "memory", "high"
    tail = _transcript_tail(transcript_path)
    tokens = _salient_tokens(prompt)
    if tail and tokens:
        missing = [token for token in tokens if not _found_in_text(token, tail)]
        if not missing:
            return "covered", None  # 참조 대상이 전부 세션 안 — 대화가 답한다
        if any(_proper_like(token) for token in missing):
            return "novel", "high"  # 세션에 없는 고유명 = 기억-의존 신호
    if _LOCAL_SIGNAL_RE.search(prompt):
        return "local", None
    return "neutral", "low"


def _error_brief(exc: BaseException) -> str:
    """예외를 원장 1행 크기로 — 종류(클래스명)가 앞, 메시지는 꼬리 (관측 59:
    종류 없는 search_error 13건은 원인 귀속이 불가능했다)."""
    return f"{type(exc).__name__}: {exc}"[:160]


def _note_gate(session_id: str, gate: str, gear: str | None, action: str,
               n_picks: int, n_conflicts: int, prompt: str,
               error: str | None = None) -> None:
    """게이트 결정을 원장에 1행 남긴다 — 주입률(주입/턴)의 분모이자 전후 비교 자료.
    컨텍스트에는 한 글자도 쓰지 않는다. error는 실패 행에만 붙는다 —
    성공 행의 스키마는 기존 원장 파서와 그대로 호환."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        row = {
            "at": int(time.time()),
            "session": (session_id or "")[:8],
            "gate": gate,
            "gear": gear or "-",
            "action": action,
            "picks": n_picks,
            "conflicts": n_conflicts,
            "prompt_head": prompt[:80],
        }
        if error:
            row["error"] = error
        with open(os.path.join(STATE_DIR, "turnrecall_gate.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _threshold_notice(session_id: str) -> tuple[str, dict, str] | None:
    """③의 소비자 — forget_digest가 세운 near_threshold를 재부팅 권고 1줄로.

    에피소드당 한 번: advised 마커는 플래그가 내려갈 때만 forget_digest가
    지우므로, 임계 위에 머무는 동안 매 턴 잔소리하지 않는다. 문구는
    backlog_turns를 읽어 '소화 완료'를 과잉 주장하지 않고, 강제하지 않는다 —
    캡슐과 같은 제안 규약이다 (rolling-consolidation-stage1.md ③).
    """
    if not session_id:
        return None
    path = os.path.join(STATE_DIR, f"digest-{session_id}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
    except Exception:
        return None
    if not state.get("near_threshold") or state.get("near_threshold_advised"):
        return None
    backlog = int(state.get("backlog_turns") or 0)
    digested = (
        "활성 창 밖 구간은 forget에 소화 완료"
        if backlog == 0
        else f"활성 창 밖 {backlog}턴은 다음 Stop에서 소화 예정"
    )
    ratio = float(state.get("est_ratio") or 0.0)
    line = (
        f"[forget 임계 — 컨텍스트 사용 추정 ~{round(ratio * 100)}%. {digested}. "
        "컴팩션보다 재부팅(새 세션 + 캡슐 복원)이 낫다 — 제안이며 명령이 아님]"
    )
    return line, state, path


def _mark_threshold_advised(state: dict, path: str) -> None:
    try:
        state["near_threshold_advised"] = True
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception:
        pass


# ── 상황 좌석 (P-M-8, 2026-08-30) ──────────────────────────────────────────
# 실전 사고: «벤치마크로 증명할 수 있으려나»가 LME-V2 제출-대기 상태를 못
# 데려옴 — 개방 원장 랭킹도, 전용 풀 코사인도 미스(임베딩 과신 4연속 실측).
# 처방: 질문형 턴에서 서버 situation_recall(결정론 후보화+로컬 판독기)이
# 활성 트랙 1줄을 고른다. 픽이 없어도(침묵 턴) 이 줄은 나간다 — 그게 요점.
_SITUATION_Q_RE = re.compile(r"[??]\s*$|려나|을까\b|할까\b|되나\b|볼\s*수|을\s*수\s*있|어때|가능\s*(?:해|할|한)")


def _situation_seat(session_id: str, prompt: str) -> str | None:
    if str(os.environ.get("FORGET_SITUATION_SEAT", "")).strip().lower() in {"0", "off", "false"}:
        return None
    if not _SITUATION_Q_RE.search(prompt):
        return None
    state_path = os.path.join(STATE_DIR, f"{session_id}.situation.json") if session_id else ""
    seen_tasks: list[str] = []
    if state_path and os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as fh:
                seen_tasks = json.load(fh).get("tasks") or []
        except Exception:
            pass
    try:
        hit = (_rpc("situation_recall", {"query": prompt[:300]}, timeout=9) or {}).get("situation")
    except Exception:
        return None
    if not hit or hit.get("task_id") in seen_tasks:
        return None
    if state_path:
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as fh:
                json.dump({"tasks": seen_tasks + [hit["task_id"]]}, fh, ensure_ascii=False)
        except Exception:
            pass
    return (f"[forget 상황 — 이 질문이 가리키는 활성 트랙 '{hit['task_id']}': "
            f"{str(hit.get('line') or '')[:150]} / 답하기 전 이 트랙의 최신 상태를 근거로 삼을 것]")


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
    # 턴-유형 게이트: 검색 전에 이 턴이 기억을 원하는 턴인지 읽는다 (2026-08-10).
    if _gate_off():
        gate, gear = "off", "low"  # 대조 경로 — 게이트·승격 없이 종전 동작 그대로
    else:
        gate, gear = _classify_turn(prompt, str(hook_input.get("transcript_path") or ""), crossed)
    if gear is None:
        _note_gate(session_id, gate, gear,
                   "silent_covered" if gate == "covered" else "silent_gate", 0, 0, prompt)
        return
    # 기본은 instant 경로(low) — 회상 다이얼을 모든 타건에 물리지 않는다(950e77a).
    # 단 턴이 스스로 기억-의존을 선언하면("지난번…", 세션에 없는 고유명) 그 턴에
    # 한해 high로 승격한다 — 적응형 기어 (2026-08-10 정훈 승인 방향).
    search_args: dict = {
        "query": prompt[:300],
        "top_k": CANDIDATE_TOP_K,
        "recall": gear,
        "trace": "turn_recall",      # body A1: 피드백이 붙을 주소를 만든다
        "score_breakdown": True,     # body A2: 의미/어휘 성분 분리
    }
    if project and not crossed:
        search_args["filters"] = layered_filter(project)
    try:
        # 상한은 기어를 따른다: instant 경로(low)는 5s 원칙 유지, 턴이 스스로
        # 기억-의존을 선언한 high에서는 딥 리콜 실측 ~4.4s를 품도록 12s —
        # 그 턴에서 몇 초의 대기는 침묵보다 싸다 (2026-08-11, search_error 2/2 수리).
        result = _rpc("search_memories", search_args, timeout=7 if gear == "high" else 5)
    except Exception as exc:
        # 2026-08-12 실측: 콜드 딥리콜 11s > CC 훅 한도 → 회상 전량 폐기 사고.
        # 서버가 keep_alive 상주+기동 예열로 콜드를 없애지만, 남는 콜드 턴은
        # 침묵 대신 low로 강등한다 — 얕은 회상이 무회상보다 낫다는 게 c43의
        # 교훈(예산은 조건부 자산)의 역방향 적용이기도 하다.
        if gear == "high":
            try:
                search_args["recall"] = "low"
                result = _rpc("search_memories", search_args, timeout=2)
                _note_gate(session_id, gate, gear, "degraded_to_low", 0, 0, prompt,
                           error=_error_brief(exc))
            except Exception as exc2:
                _note_gate(session_id, gate, gear, "search_error", 0, 0, prompt,
                           error=_error_brief(exc2))
                return
        else:
            # fail-open은 유지하되 원장에는 남긴다 — 원인 종류 동봉 (관측 59 ②).
            _note_gate(session_id, gate, gear, "search_error", 0, 0, prompt,
                       error=_error_brief(exc))
            return
    trace_id = str(result.get("trace_id") or "")
    # 평탄도는 **주입 자격이 있는 후보**에서만 재야 한다 (c62 실측 수리).
    # 이전 판본은 배제 이전의 전체 결과로 분포를 재서, 봉우리가 결코 주입될 수
    # 없는 항목(task_state claim·capture 포인터)일 수 있었다. 실측: 축자 동일한
    # 질의의 두 런이 하위 4개 점수는 완전히 같은데 top1(양쪽 다 task_state
    # claim)만 0.9172 vs 1.0000으로 갈려 주입 0 vs 3이 됐다 — 방금 쓴 claim은
    # 1.0으로 포화하므로 푸시 회상의 on/off가 장부 신선도에 결합돼 있었다.
    results = result.get("results") or []
    # 창은 자격 후보 상위 FLATNESS_WINDOW개 — 인출을 깊게 해도 자[尺]는 그대로다
    # (c63: 자격 4개였던 질의의 spread 0.0454가 창 5에서도 0.0454, 중앙값 위치 보존).
    scores_all = sorted(
        (float(item.get("score") or 0.0) for item in results if _injection_eligible(item)),
        reverse=True,
    )[:FLATNESS_WINDOW]
    measurable = len(scores_all) >= FLATNESS_MIN_SAMPLES
    flat_distribution = (
        measurable
        and (scores_all[0] - scores_all[len(scores_all) // 2]) < FLATNESS_MARGIN
    )
    picks = []
    # P4 v1 (2026-08-12, ARB-C evidence_status 이식): 신뢰등(출처 축)과 별개로
    # 이 턴 질문에 대한 증거 강도 축을 분리 보고한다. 절대 임계는 못 쓴다 —
    # 실측(p4_probe): 무관 질의도 합성 점수 0.51 바닥, 관련 질의 0.55~0.66으로
    # 압축돼 있어 턴-상대(상단 밴드)로만 가른다. c40 벤치의 spread 신호와 동형.
    pick_scores: dict[str, float] = {}
    # 시간 이웃은 서버가 목록 '끝'에 붙인다 — PICK_POOL 절단 전에 전체에서 수집.
    neighbor_pool: list[dict] = [item for item in results if item.get("temporal_neighbor_of")]
    conflict_pairs: dict[tuple[str, str], None] = {}
    for item in results[:PICK_POOL]:
        if item.get("temporal_neighbor_of"):
            continue  # 이웃은 별도 경로 — 정규 임계를 안 거친다
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
        if str(metadata.get("layer") or "").lower() == "self":
            # self 격언은 캡슐 "자기:" 라인 전용 채널로만 나간다 — ambient 회상에
            # 어휘 인접으로 새면 소음 (2026-08-10 실측: 소음 3건 중 2건). 충돌쌍
            # 경로보다 먼저 잘라 self 정정 이력도 턴 회상으로는 안 나간다.
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
        pick_scores[memory_id] = score
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

    if picks and not measurable:
        # 표본이 창의 최소 개수에 못 미쳐 평탄도를 **재지 못한 채** 통과시킨 턴.
        # c62가 이 상태를 "무공지 전면 정지"로 등재했다 — 깊은 인출로 빈도를 0으로
        # 밀었지만(c63 실측 0/20), 남는 경우엔 최소한 흔적을 남긴다. 컨텍스트에는
        # 한 글자도 쓰지 않는다: 이 원장은 감사가 읽는 자리다.
        _note_unmeasured_flatness(prompt, len(results), len(scores_all), len(picks))
    notice = _threshold_notice(session_id)
    situation = _situation_seat(session_id, prompt)
    if not picks and not conflicts and notice is None and situation is None:
        _note_gate(session_id, gate, gear, "silent_scores", 0, 0, prompt)
        return  # below threshold or nothing new → silence
    lines = []
    if situation:
        lines.append(situation)
    if conflicts:
        lines.append("[forget 충돌지대 — 이 주제엔 정정 이력이 있음. 현재본 기준으로 행동하고, 구본 위에서 행동하지 말 것]")
        for _, _, old_text, new_text in conflicts:
            lines.append(f"- (현재) {new_text}")
            lines.append(f"- (red/구본) {old_text}")
    if picks:
        # 전제-검증 조항 (2026-08-10, LME-V2 정합 3쌍 전승 실증의 제품 역이식):
        # 기억과 어긋나는 전제 위에서 답하지 말 것 — 각서의 나머지 절반.
        header = "[forget 회상 — 이 턴과 관련된 기억 제안. green=행동 근거 OK, yellow=행동 전 확인, red=참고만"
        header += " / 직접=이 턴의 근거 후보, 참고=관련 단서일 뿐 답의 근거 아님"
        header += " / 질문의 전제가 기억과 어긋나면 전제를 따르지 말고 기억을 인용해 짚을 것"
        header += " / 프로젝트 경계를 넘어 검색함]" if crossed else "]"
        lines.append(header)
        # 증거 태그: 평탄도를 잰 턴에서만 '직접'을 허용 — 못 잰 턴은 전원 '참고'
        # (근거 표기는 과장보다 누락이 싸다). 밴드는 턴 최고점 기준 상대치.
        evidence_band = float(os.environ.get("FORGET_EVIDENCE_BAND", "0.02"))
        top_score = max(pick_scores.values()) if pick_scores else 0.0
        def _etag(mid: str) -> str:
            if not measurable or mid not in pick_scores:
                return "참고"
            return "직접" if pick_scores[mid] >= top_score - evidence_band else "참고"
        lines += [f"- ({light}·{_etag(mid)}) {memory}" for mid, light, memory in picks]
        # EM-LLM 이식(2026-08-11): 채택된 앵커의 시간 이웃 1건 — "회상은 장면을 데려온다".
        if neighbor_pool and os.environ.get("FORGET_RECALL_TEMPORAL", "1").strip().lower() not in {"0", "off", "false"}:
            picked_ids = {memory_id for memory_id, _, _ in picks}
            nb = next((n for n in neighbor_pool
                       if str(n.get("temporal_neighbor_of")) in picked_ids
                       and str(n.get("id") or "") and str(n.get("id")) not in seen), None)
            if nb is not None:
                gap = (nb.get("score_breakdown") or {}).get("temporal_gap_minutes")
                nb_text = str(nb.get("memory") or "")[:MEMORY_CHAR_LIMIT]
                lines.append(f"- (yellow·같은 장면 ±{gap}분) {nb_text}")
                picks.append((str(nb.get("id")), "yellow", nb_text))  # 원장·반복억제 합류
    if notice is not None:
        lines.append(notice[0])
    if trace_id and (picks or conflicts):
        lines.append(
            f"[피드백 주소: 이 회상이 명확히 도움/소음이면 record_context_outcome(trace_id=\"{trace_id}\") 한 번]"
        )
    print("\n".join(lines))
    _note_gate(session_id, gate, gear,
               "injected" if (picks or conflicts)
               else ("situation_only" if situation else "notice_only"),
               len(picks), len(conflicts), prompt)
    if notice is not None:
        _mark_threshold_advised(notice[1], notice[2])
    if session_id and turns_path and (picks or conflicts):
        injected = [memory_id for memory_id, _, _ in picks]
        ledger_picks = list(picks)
        for old_id, new_id, old_text, new_text in conflicts:
            injected += [old_id, new_id]
            ledger_picks.append((new_id, "green", new_text))  # 메아리 측정은 현재본 기준
        _remember_injected(turns_path, injected)
        _extend_offer_ledger(session_id, ledger_picks, trace_id)


def _note_unmeasured_flatness(prompt: str, candidates: int, eligible: int, injected: int) -> None:
    """평탄도를 재지 못하고 통과시킨 턴을 원장에 1행 남긴다 (감사용, 컨텍스트 비용 0)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "flatness_unmeasured.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": int(time.time()),
                "candidates": candidates,
                "eligible": eligible,
                "min_samples": FLATNESS_MIN_SAMPLES,
                "injected": injected,
                "prompt_head": prompt[:80],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _extend_offer_ledger(session_id: str, picks: list, trace_id: str = "") -> None:
    """Feed turn recalls into the outcome flywheel as *aligned* offers.

    (Discovered gap 07-22: a session answered purely from a turn recall and the
    capsule-only labeler scored it "not used".)

    Rewritten 2026-08-23 after measuring what the old shape could express. It
    appended ids into one set and probes into another list — two containers with
    no correspondence — so the capture hook could only say "something echoed"
    and then credit *every* offered memory (it labelled itself all-or-none).
    Worse, the credit landed on the session capsule's trace_id, so a memory
    pulled by a turn recall was recorded against the query
    "session startup — active tasks, open loops". Measured consequence: 784
    turn_recall traces, **zero** with used_memory_ids, while the 28 that had
    gold all wore the session-startup query. The pairing was wrong, so the
    mined training pairs were wrong too.

    `offers` fixes both: each entry keeps its own probe next to its own id and
    the trace that offered it, which is exactly what `picks` already held.
    """
    ledger_path = os.path.join(STATE_DIR, f"{session_id}.json")
    try:
        state = {}
        if os.path.exists(ledger_path):
            with open(ledger_path, encoding="utf-8") as fh:
                state = json.load(fh)
        elif not trace_id:
            return  # nothing to record against: no capsule trace, no turn trace
        if not trace_id:
            # 주소 없는 서버(배포 전 사본)에서는 정렬 제안을 만들 수 없다. 새 경로가
            # 조용히 턴 픽을 버리면 측정이 구본보다 나빠지므로 레거시 병합으로 되돌린다:
            # 거친 all-or-none이지만 0보다는 낫다. 서버가 trace_id를 돌려주기 시작하면
            # 이 분기는 저절로 죽는다.
            state["memory_ids"] = list({*(state.get("memory_ids") or []),
                                        *(memory_id for memory_id, _, _ in picks)})
            state["capsule_lines"] = (state.get("capsule_lines") or []) + [m[:80] for _, _, m in picks]
            state["legacy_merge_reason"] = "no trace_id from server"
            with open(ledger_path, "w", encoding="utf-8") as fh:
                json.dump(state, fh, ensure_ascii=False)
            return
        offers = state.get("offers") or []
        known = {(o.get("id"), o.get("trace")) for o in offers if isinstance(o, dict)}
        for memory_id, _light, memory in picks:
            key = (memory_id, trace_id)
            if memory_id and key not in known:
                # 320자: 의미 판정(v3)의 문턱이 전문(60~320자) 기억으로 보정됐다.
                # 문면 판정(6그램)은 capture 쪽에서 여전히 앞 80자만 쓴다 — 의미 불변.
                offers.append({"id": memory_id, "probe": memory[:320], "trace": trace_id})
                known.add(key)
        state["offers"] = offers
        # 레거시 필드는 세션 캡슐(합성이라 줄↔기억 대응이 없다)의 몫으로 남긴다 —
        # 여기에 턴 픽을 섞던 것이 위양성과 오귀속의 원천이었다.
        with open(ledger_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 검색 이후의 크래시는 원장에도 없는 완전 침묵이었다 (관측 59 삼킴 지점 ③).
        # fail-open은 유지하되 흔적은 남긴다 — 세션·프롬프트는 이 지점에선 모른다.
        _note_gate("", "-", None, "hook_error", 0, 0, "", error=_error_brief(exc))
    sys.exit(0)
