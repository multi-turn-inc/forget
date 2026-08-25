"""LME L2 구성 A/B — 덤프 vs 조립 vs 조립+접지. (2026-08-24, 정훈 승인 "등록하고 걸자")

L1 교정판이 밝힌 것: 바늘@84 = 1.00 — 검색 도달은 이 벤치마크에서 만점이다.
공표 81.8%와의 ~18pp 격차는 하류(구성·독해)에 산다. 그러므로 이 실험은 검색이
아니라 **리더가 읽는 것**을 팔로 가른다 — 우리 제품 명제("조립이 곧 제품",
"2천 토큰이 11.5만을 이긴다")의 84턴 스케일 외부 실측이다.

팔 (문항마다 동일 인게스트, 동일 리더·판정 — 다른 것은 컨텍스트뿐):
  A 덤프   top-84 검색 턴을 날짜와 함께 나열 (Tier-0 재현 · ~9천 토큰대)
  B 조립   assemble_context 예산 2,000 토큰 (신뢰 랭킹·중복 제거·기아 방지·앵커 렌더)
  C 접지   B + 질의 확장 — 로컬 LLM이 질문을 검색어로 재작성하며 상대 날짜를
           절대 날짜로 해소 ("two months ago Wednesday" → 2023-02-01). 시뮬레이션
           밴드의 최소형이며 1차 표적은 temporal·multi-session.

리더·판정: Qwen3.8-27B @ 4090 (터널 18812), temp 0. 판정 프롬프트는 하네스
JUDGE_TEMPLATES 문면 그대로 — 판정자 편향은 팔 간 상쇄된다 (공표 숫자와의
절대 비교는 불가하며 주장하지 않는다. 그것은 L3 게이트의 몫).

## 사전 등록 판정 (숫자를 보기 전에 고정)

  P-L2-A (조립 대 덤프): B − A ≥ +3pp → 조립 우위 실증.
      |B − A| < 3pp → 동급 — 토큰 1/4~1/5로 같은 정확도면 실질 승리로 기록하되
      "우위"라 부르지 않는다. B − A ≤ −3pp → 조립이 정보를 잃는다: 문항별
      덤프-정답·조립-오답 사례를 해부해 병소(선별/예산/렌더)를 특정한다.
  P-L2-B (접지): temporal+multi-session 부분집합에서 C − B ≥ +5pp → 접지 채택.
      +2pp 미만 → 기각. 타 유형에서 C − B ≤ −3pp면 부작용으로 채택 불가.
  부기: 팔별 평균 컨텍스트 토큰을 반드시 병기한다 — 효율 축이 주장의 절반이다.

## 추기 (2026-08-24 새벽 — 계기 고장 4호 공시와 교정 등록, 숫자 보기 전 고정)

  P-L2-C(예산 무릎 스윕)는 설계 그대로 **불활성**이었다: assemble_context 내부
  검색이 top_k 기본 10이라 후보 풀이 수도꼭지에서 이미 좁혀져(문항당 ~7건 ·
  1.1k tok), 예산 2k/4k/8k는 하류 노브였다. 두 스윕 런이 바이트 동일 — 부산물로
  파이프라인 결정론(temp 0)은 검증됐다. 원장 정정: B의 −23pp는 "예산 2k의 조립"이
  아니라 "**후보 10건**의 조립"의 성적이다.

  P-L2-C′ (교정 스윕): LME_B_TOPK=84로 A와 동일한 후보 풀을 주고 예산 {2k,4k,8k}.
      무릎 규칙 동일 — B84(b) ≥ A−2pp인 최소 b* = "조립 등가점", 절감비(17.3k/b*)
      병기. 8k에서도 A−5pp 미달이면 이 리더·이 세분성에서 단발 조립 열세 확정.
  P-L2-D (더듬기 — 정훈 발의 "기억을 한 턴만에 끝내야 되는 건가. 사람은 부족한
      기억을 더듬어가며 길게 끄집어낸다"): D = 실제 캡슐(top_k 10 · 예산 2k, B와
      같은 출발선) + SEARCH 루프 ≤5회(회당 top_k 10, 기수번 기억 중복 제거).
      리더가 "SEARCH: <검색어>" 한 줄을 내면 추가 회수해 이어붙이고 다시 읽는다.
      채택: D ≥ A−5pp 그리고 평균 누적 토큰 ≤ 6k → "작은 캡슐 + 더듬기" 제품 경로.
      부분 지지: D ≥ B+10pp → 더듬기 유효, 상한은 리더 역량.
      기각: D < B+5pp → 이 리더에서 더듬기 무효 (도구 규약·리더 교체로 이월).

## 추기 2 (2026-08-24 오후 — D2 절제 등록, 정훈 발의 "메타인지를 단순히
   명시화한다고 해결이 될까?" — 그 회의 자체를 절제 실험으로)

  팔 E (D2a, 언어화 단독): 더듬기 앞에 리더가 증거 체크리스트를 먼저 쓰고
      (계획 호출 1회) 그 목록을 시스템에 얹은 뒤 D와 동일 루프.
  팔 G (D2b, 외부화 게이트): 체크리스트 없음. 발판이 잰 신호를 주입 —
      ①증거 스팬 계수(컨텍스트의 서로 다른 날짜 수) ②직전 회수 강도
      (검색 최고 점수, 약함 표시) ③다중증거 휴리스틱(how many/compare/
      total/order 등 — gold 유형 아님, 질문 문면만) 해당 시 0라운드
      즉답을 1회 반려하고 최소 1회 탐침 강제.
  판정 (숫자 보기 전 고정, D0=0.660 · n=100 동일 표본):
      E − D < +3pp 그리고 G − E ≥ +5pp → "메타인지는 언어화가 아니라
      외부화" 테제 채택 (정훈 회의의 실증).
      E − D ≥ +5pp → 언어화도 유효 — 테제 기각, 회의가 틀림으로 판정.
      G − D < +3pp → 외부화도 무효 — 0층 신호로는 부족, 1층(세계모델
      기대)으로 병소 이월.

## 추기 3 (2026-08-24 저녁 — E∧G 결합, P-D2 완결이 발견한 상보성의 검증)

  팔 H = 체크리스트(E) ∧ 외부 게이트(G) 동시. 유형별 최강이 갈렸으므로
  (체크리스트=knowledge-update 0.87 · 게이트=multi-session 0.65) 결합이
  양쪽 최선을 합성하는지 검증한다.
  판정 (숫자 보기 전 고정, 참조 D 0.660 · E 0.720 · G 0.730):
      채택: H ≥ 0.75 (G+2pp — 상보 조합 실재)
      기각: H ≤ 0.730 (겹침 상쇄 — 결합 무익)
      사이: 회색 — 중복 우세, 유형별 스위칭(질문 유형에 따라 E/G 선택)을
      차기 등록 후보로 이월.

## 추기 4 (2026-08-24 밤 — 유형별 라우팅, H 기각["개입을 쌓으면 간섭"]의 수확)

  팔 R = 질문 문면 라우팅: MULTI_EVIDENCE_RE(세기·비교·정렬 어휘) 매치 →
  G(외부 게이트, multi-session 최강 0.65), 비매치 → E(체크리스트,
  knowledge-update 최강 0.87). 개입은 하나만 — 지시 과적 회피가 설계 논지.
  판정 (숫자 보기 전 고정, 참조 E 0.720 · G 0.730 · H 0.680):
      채택: R ≥ 0.75 (라우팅이 상보성을 실수확)
      기각: R ≤ 0.730 (라우팅 무익 — 단일 최강 팔 G로 확정)
      사이: 회색. 부기: 라우팅 분기 수(G행/E행) 병기.

## 추기 5 (2026-08-25 — P-WM-2: 1층 조준. L2 종결 판정의 이월["0층 프롬프트 수확
   종료, 다음 레버는 1층(세계모델 기대 조준)"]을 실행한다. 정훈 "착수". 타산지석
   #9(구조 먼저, RL 마지막)·#16(빌린 세계모델은 1-2스텝 조준만 — 다단 시뮬 주장
   없음) 준수 확인 완료.)

  팔 W = G(외부 게이트 전 계기 동일) + 세계모델 시간 색인 주입: 문항 스코프
  원장에서 사건 기관을 파생(worldmodel.rebuild + user_id 필터. 벤치 파생 공시:
  사건 1건 = 대화 턴 1건, 제목 = 턴 문면[:90], t = 세션 날짜 — 키워드 매치는
  그 90자 창 안에서만 되므로 과소계수 경향이 있고, 조직 v0을 지어진 그대로
  잰다)하고, 매 라운드 다음을 주입한다:
    ① 지평 1줄 — [world] memory spans <min> → <max> (<N> distinct days)
    ② 질문 내용어(불용어 제거 · 3자 이상 · 긴 것 우선 ≤6개 시도) 중 고유
       날짜 수 1~15에 드는 상위 2개의 날짜 색인 — [world] '<kw>' appears
       on N date(s): d1, …
  구조(날짜·계수)만 주입하고 제목은 주입하지 않는다 — 내용 누수 차단이
  "조준" 주장의 전제다. 색인 0건이면 W = G + 지평 1줄.
  판정 (숫자 보기 전 고정, 참조 G 0.730 · 동일 n=100 표본·리더·판정.
  G행은 lme_L2_G_rows.jsonl과 qid로 짝지어 계산):
      채택: event-군(감사 event 유형의 LME 대응 = temporal-reasoning +
            multi-session)에서 W − G ≥ +8pp
      기각: 동 부분집합에서 W − G < +3pp (사이 회색)
      부작용 가드: 타 유형 합산 W − G ≤ −3pp면 결과 불문 채택 불가 (P-L2-B 준용)
      부기 의무: 키워드 색인 주입률·부분집합 n 병기. 색인 0건 문항은 실효
      대조가 아니므로 색인 주입 문항만의 W−G도 병기한다.

## 추기 6 (2026-08-25 — P-WM-2b: W 기각 부검의 수리 재등록. W 판정 실측:
   event-군 W−G = −11.3pp(n=53) → **기각**. 병소 3(모두 실측): M1 빈곤 전이 —
   붕괴 스코프(고유 1일, 18/100 전부 event-군)에서 지평 1줄이 세계의 빈곤으로
   오독돼 텍스트 내 상대날짜 증거를 두고도 후퇴(붕괴군 Δ−16.7pp). M2 앵커
   치환 — 색인 날짜가 질문일 산술을 대체(b46e15ee: 3/19 정답 대신 색인의
   2/14 선택). M3 조기 종결 — 색인 권위가 더듬기를 생략시킴: 검색 0회 전락
   11문항 Δ−36.4pp(0.909→0.545), 평균 검색 3.12→2.78회. 공통 뿌리: 리더가
   상태 계층을 **지도가 아니라 증거로** 취급.)

  팔 V = W의 단일 재규정 "지도이지 증거가 아니다" (한 원리의 세 발현 수리):
    ① 붕괴 게이트(M1): 지평 고유 날짜 < 3이면 아무것도 주입 않음 — 파생
       무신호는 침묵이 거짓 빈곤보다 낫다. 그 문항은 V ≡ G.
    ② 인식 재프레임(M2): 색인 문구를 힌트로 강등 — mention-index이며 ground
       truth가 아님, 계수는 턴 앞 90자의 어휘 언급일 뿐, 검색 조준에만 쓰라.
    ③ 검증 의무(M3): 색인이 주입됐는데 검색 0회면 즉답을 1회 반려 (G의
       강제 최소 탐침을 색인 존재로 일반화).
  판정 (숫자 보기 전 고정, 동일 n=100 표본·G행 qid 짝):
      채택: event-군 V − G ≥ +5pp (1층 색인 조준 유효)
      기각·종결: V − G < +3pp → 1층 색인 접근 종결, 병소를 리더 상향(L3)과
                파생 v1(사건 추출 상향)로 이월
      사이(+3~+5): 회색 — 붕괴 게이트(①)만 분리 재론 후보
      가드: 타유형 합산 V − G ≤ −3pp면 결과 불문 채택 불가
      부기 의무: 검색 0회 문항 수(M3 지표)·주입률 병기.

## 추기 7 (2026-08-25 오후 — P-PF-1: 추천 탐침. preference 부검의 집행)

  부검(G팔 preference 6문항, 3승 3패): 패배 2/3의 공통 병소 = **검색 0회
  조기 종결** — "추천해줘/제안해줘" 질문에서 리더가 '추천 대상 정보가
  기억에 없다'로 판단, 사용자 선호 탐색을 아예 안 함 (35a27287·8a2466db).
  G의 강제 탐침은 세기·비교·순서 어휘만 커버 — 추천성 질문은 구멍.
  진단: 선호 질문의 절반은 성향 기관 없이도 "선호를 검색하라"는 의무
  하나로 풀린다 (외과 체크리스트 원리의 확장).

  팔 P = G + RECOMMEND_RE 매치 시 0-탐침 즉답 1회 반려 (선호·취향 검색
  의무 문구). 판정 (숫자 보기 전 고정, n=6이라 통계 불가 — 기전 검증):
      채택: preference 문항의 검색 0회 조기 종결 0건 그리고 정답 ≥ G+1건
      기각: 검색은 강제됐는데 정답 불변 → 병소는 회수 밖(성향 기관 필요
            근거 강화, P-PF-2로 이월)
      부기: 타 유형 부작용은 P 팔이 preference 전용 조건이라 구조적 0.

## 추기 8 (2026-08-25 오후 — P-PF-3: 성향 카드 소비. P-PF-1 잔여 실패 2건
   [검색해도 못 푸는 회수/활용 병소]의 집행. 카드는 문항 스코프 벤치 원장에서
   파생 — 실원장 카드 아님)

  팔 Q = P(추천 탐침) + 성향 카드 블록: dispositions(벤치DB, user_id=스코프,
  llm_gate)로 파생한 카드 ≤8을 [user-tastes] 블록으로 매 라운드 주입
  (world_block 주입구 재사용 — 더듬기 코드 무변경).
  판정 (숫자 보기 전 고정, n=6 기전 검증):
      채택: Q ≥ P+1건 (5/6) — 성향 카드가 회수 병소를 실제로 메움
      기각: Q = P (카드 무익 — 병소는 활용/리더 쪽으로 이월)
      채택 불가: Q < P (카드가 오히려 간섭 — 힌트도 예산의 재확인)
      부기: 문항별 카드 수·잔여 실패 2건(35a27287·32260d93)의 개별 서사 의무.

사용: MEM1_DB_PATH=<벤치DB> .venv/bin/python scripts/lme_l2_ab.py [--n 100] [--arms ABCDEGHRWVPQ]
      (이어달리기: 출력 JSONL의 완료 문항은 건너뛴다. W/V: LME_WM_DIR로 파생 DB 위치 지정 가능)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "research/longmemeval-data/longmemeval_s_cleaned.json"
LLM = os.environ.get("LME_LLM_URL", "http://127.0.0.1:18812/v1/chat/completions")
OUT = os.environ.get("LME_L2_OUT", str(REPO / "research/eval/lme_L2_ab_rows.jsonl"))

JUDGE = {
    "default": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "temporal-reasoning": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "single-session-preference": "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: {q}\n\nRubric: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
}


def llm(system: str, user: str, max_tokens: int = 256) -> str:
    body = {"model": "qwen", "temperature": 0.0, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request(LLM, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(4 * (attempt + 1))
    return ""


def token_est(text: str) -> int:
    return max(1, len(text) // 4)


def read_answer(question: str, qdate: str, context: str) -> str:
    system = ("You answer questions about the user based ONLY on the provided memory excerpts. "
              f"The question is asked on {qdate}. Use the memory dates to resolve any relative "
              "time references. If the needed information is not in the excerpts, say you don't know.")
    user = f"<memories>\n{context}\n</memories>\n\nQuestion: {question}\nAnswer concisely."
    return llm(system, user)


def judge(qtype: str, question: str, answer: str, hyp: str) -> bool:
    template = JUDGE.get(qtype, JUDGE["default"])
    out = llm("You are a strict grader.",
              template.format(q=question, a=answer, r=hyp), max_tokens=8)
    return out.strip().lower().startswith("yes")


MULTI_EVIDENCE_RE = re.compile(
    r"how many|how much (more|less)|total|compare|first|last|order|difference|"
    r"between|each time|every time|all the|몇 |비교|순서|총 |차이", re.I)

RECOMMEND_RE = re.compile(
    r"recommend|suggest|any (good |interesting |new )?(idea|tip|resource|show|"
    r"movie|event|recipe|book|documentar)|what should i|추천|제안", re.I)


def evidence_checklist(question: str, qdate: str) -> str:
    """팔 E(D2a)의 계획 호출 — 언어화 메타인지 단독의 효과를 절제한다."""
    return llm("You plan evidence retrieval for a memory system. List the distinct "
               "pieces of evidence (facts, dates, sessions) needed to answer the "
               "question. 3-6 short bullet lines. Do NOT answer the question.",
               f"Question (asked on {qdate}): {question}", max_tokens=180).strip()[:600]


def read_groping(question: str, qdate: str, context: str, searcher, max_rounds: int = 5,
                 checklist: str | None = None, external_gates: bool = False,
                 world_block: str | None = None, preference_probe: bool = False):
    """팔 D/E/G — 더듬기(strategic recall). 사람의 인출은 한 턴이 아니다: 단서를
    만들고(생성), 맞는지 보고(재인), 다시 더듬는다. 그 최소 기계화 — 도구 호출
    규약이 없는 로컬 리더로도 돌게, SEARCH: 한 줄 규약으로 루프를 돈다.

    checklist(팔 E): 리더가 스스로 쓴 증거 목록을 시스템에 얹음 — 언어화 단독.
    external_gates(팔 G): 발판이 잰 신호를 주입 — 증거 스팬 계수·직전 회수
    강도, 그리고 다중증거 휴리스틱 문항의 0-탐침 즉답을 1회 반려(강제 최소
    탐침 — 외과 체크리스트 원리: 내성이 아니라 의무라서 작동한다).

    반환 (답, 누적 컨텍스트 토큰, 검색 횟수, 최종 컨텍스트 토큰).
    """
    shown = context
    total_tok = 0
    n_search = 0
    last_strength: float | None = None
    forced_used = False
    for round_i in range(max_rounds + 1):
        last = round_i == max_rounds
        system = ("You answer questions about the user based ONLY on the provided memory excerpts. "
                  f"The question is asked on {qdate}. Use the memory dates to resolve any relative "
                  "time references. "
                  + ("You may not search again. Answer concisely from the excerpts; if the needed "
                     "information is not there, say you don't know."
                     if last else
                     "If the excerpts fully answer the question, answer concisely. If anything "
                     "needed is missing, do NOT guess: reply with exactly one line in the form\n"
                     "SEARCH: <3-8 search keywords, include absolute dates if relevant>"))
        if checklist:
            system += "\n\nEvidence you determined you need:\n" + checklist
        instrument = ""
        if external_gates:
            dates = set(re.findall(r"\[(\d{4}-\d{2}-\d{2})\]", shown))
            instrument = f"\n[instrument] evidence span in context: {len(dates)} distinct dates"
            if last_strength is not None:
                instrument += (f"\n[instrument] last retrieval strength: {last_strength:.2f}"
                               + (" (weak — evidence may be missing)" if last_strength < 0.5 else ""))
        if world_block:
            # 팔 W(추기 5): 세계모델 시간 색인 — 라운드 불변인 세계 상태라 매
            # 라운드 같은 자리에 얹는다. 색인과 컨텍스트의 격차가 곧 조준 신호.
            instrument += "\n" + world_block
        user = f"<memories>\n{shown}\n</memories>{instrument}\n\nQuestion: {question}\nAnswer concisely."
        total_tok += token_est(user)
        out = llm(system, user)
        m = re.match(r"^\s*SEARCH:\s*(.+)$", out, re.IGNORECASE)
        if (m is None and external_gates and not forced_used and n_search == 0
                and not last and (MULTI_EVIDENCE_RE.search(question) or world_block
                                  or (preference_probe and RECOMMEND_RE.search(question)))):
            forced_used = True
            # 팔 V ③ 검증 의무: 색인이 있으면 무검증 즉답을 1회 반려한다 —
            # W 부검의 M3(색인 권위로 검색 0회 전락 11문항, Δ−36.4pp) 수리.
            # 팔 P (추기 7): 추천성 질문의 0-탐침 즉답도 반려 — "추천 대상
            # 정보가 없다"가 아니라 "이 사람의 취향"이 회수 대상이다.
            if preference_probe and RECOMMEND_RE.search(question) and not MULTI_EVIDENCE_RE.search(question):
                shown += ("\n[instrument] This is a recommendation/personalization question. "
                          "Before answering (and before concluding anything is missing), you must "
                          "SEARCH for this user's tastes, preferences, and past interests related "
                          "to the topic.")
            elif MULTI_EVIDENCE_RE.search(question):
                shown += ("\n[instrument] This question likely needs multiple evidence pieces "
                          "(comparison/counting/ordering). You must SEARCH at least once before answering.")
            else:
                shown += ("\n[instrument] A world index is present but nothing has been verified "
                          "by search. You must SEARCH at least once before answering.")
            continue
        if not m or last:
            # 누적(스테이트리스 지불)과 최종 컨텍스트(캐시 리더 지불) 둘 다 —
            # 프리픽스 캐시가 있으면 재독 라운드는 거의 공짜라 후자가 실효 비용.
            return out, total_tok, n_search, token_est(shown)
        n_search += 1
        extra, strength = searcher(m.group(1).strip()[:300])
        last_strength = strength
        shown = shown + "\n" + (extra or "(추가 회수 결과 없음 — 같은 검색을 반복하지 말 것)")
    return out, total_tok, n_search, token_est(shown)


def expand_query(question: str, qdate: str) -> str:
    out = llm("You rewrite questions into search keywords for a memory database. "
              "Resolve every relative date reference into absolute dates (YYYY-MM-DD) "
              f"using the question date {qdate}. Output ONLY comma-separated keywords, "
              "phrases and absolute dates. No explanations.",
              question, max_tokens=80)
    return re.sub(r"\s+", " ", out)[:300]


# ── 팔 W (추기 5): 세계모델 시간 색인 ────────────────────────────────────
WM_STOP = set("""the and you your for with that this what when where why how many much did
does was were have has had are is not but about from they them their there which who whom
while will would could should than then into over under out off after before between during
within last first next previous ago today yesterday tomorrow now time times day days week
weeks month months year years date dates mention mentioned mentioning tell told say said
saying talk talked talking ask asked user assistant what's i've i'm don't didn't doesn't
it's that's most more less least very really just also ever never always usually often once
twice any some all every each other another same different new old recent recently earlier
later still going gone went come came take took taken get got getting make made give gave
know knew think thought want wanted like liked use used long often since until because
january february march april may june july august september october november december""".split())


def world_keywords(question: str) -> list[str]:
    words = re.findall(r"[a-z가-힣][a-z가-힣'-]{2,}", question.lower())
    seen: set[str] = set()
    out = []
    for w in words:
        if w in WM_STOP:
            continue
        # 복수형 s-절단 (스모크 발견: 'appointments'가 단수 본문을 놓침).
        # 부분문자열 매치라 절단형은 항상 원형에도 매치 — 순수 재현율 확장.
        if w.endswith("'s"):
            w = w[:-2]
        elif w.endswith("s") and len(w) > 4:
            w = w[:-1]
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return sorted(out, key=len, reverse=True)[:6]


def world_block_for(question: str, world_db: str) -> tuple[str, int]:
    """세계 블록 — 지평 1줄 + 질문 키워드 날짜 색인 ≤2줄. 구조(날짜·계수)만,
    제목 미주입(내용 누수 차단). 반환 (블록, 색인 줄 수)."""
    from forget.worldmodel import timeline
    evs = timeline(world_db, limit=10**6)
    all_dates = sorted({e["t"][:10] for e in evs if e["t"]})
    if not all_dates:
        return "", 0
    lines = [f"[world] memory spans {all_dates[0]} → {all_dates[-1]} "
             f"({len(all_dates)} distinct days)"]
    kw_lines = 0
    for kw in world_keywords(question):
        dates = sorted({e["t"][:10] for e in timeline(world_db, like=kw, limit=10**6)
                        if e["t"]})
        if not 1 <= len(dates) <= 15:
            continue
        shown = ", ".join(dates[:12]) + (f", …+{len(dates) - 12}" if len(dates) > 12 else "")
        lines.append(f"[world] '{kw}' appears on {len(dates)} date(s): {shown}")
        kw_lines += 1
        if kw_lines >= 2:
            break
    return "\n".join(lines), kw_lines


def world_block_v2(question: str, world_db: str) -> tuple[str, int]:
    """팔 V (추기 6): '지도이지 증거가 아니다' — ①붕괴 게이트 ②인식 재프레임.
    (③검증 의무는 read_groping의 강제 탐침 일반화가 맡는다.)"""
    from forget.worldmodel import timeline
    evs = timeline(world_db, limit=10**6)
    all_dates = sorted({e["t"][:10] for e in evs if e["t"]})
    if len(all_dates) < 3:      # ① 파생 무신호는 침묵 — 거짓 빈곤보다 낫다
        return "", 0
    lines = [f"[world-hint] sessions span {all_dates[0]} → {all_dates[-1]} "
             f"({len(all_dates)} distinct days). This index counts keyword MENTIONS "
             "in the first 90 chars of each turn — it is NOT ground truth. Use it "
             "ONLY to aim your searches; never answer from these counts."]
    kw_lines = 0
    for kw in world_keywords(question):
        dates = sorted({e["t"][:10] for e in timeline(world_db, like=kw, limit=10**6)
                        if e["t"]})
        if not 1 <= len(dates) <= 15:
            continue
        shown = ", ".join(dates[:12]) + (f", …+{len(dates) - 12}" if len(dates) > 12 else "")
        lines.append(f"[world-hint] '{kw}' mentioned on {len(dates)} date(s): {shown} "
                     "(mentions ≠ occurrences — verify by searching)")
        kw_lines += 1
        if kw_lines >= 2:
            break
    return "\n".join(lines), kw_lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--arms", default="ABC")
    ap.add_argument("--seed", type=int, default=20260824)
    args = ap.parse_args()
    if "forget.sqlite3" in os.environ.get("MEM1_DB_PATH", ""):
        sys.exit("실원장 금지 — 벤치 DB를 지정하라")

    from forget.store import assemble_context, search_memories

    data = json.load(open(DATA))
    rng = random.Random(args.seed)
    pool = [q for q in data if not str(q["question_id"]).endswith("_abs")]
    by_type: dict[str, list] = {}
    for q in pool:
        by_type.setdefault(q["question_type"], []).append(q)
    # 표본은 항상 n=100 정본 목록에서 앞 N개 — L1과 같은 문항·같은 벤치 스코프를
    # 보장한다 (스모크가 --n에 따라 다른 문항을 뽑아 빈 스코프를 때리던 결함 수리).
    N_CANON = 100
    sample = []
    for qtype, items in sorted(by_type.items()):
        k = max(1, round(N_CANON * len(items) / len(pool)))
        sample.extend(rng.sample(items, min(k, len(items))))
    sample = (sample[:N_CANON] if len(sample) > N_CANON else sample)[: args.n]

    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            try:
                done.add(json.loads(line)["qid"])
            except Exception:
                pass
    t0 = time.time()
    with open(OUT, "a") as fout:
        for qi, inst in enumerate(sample):
            if inst["question_id"] in done:
                continue
            scope = f"lme-{inst['question_id']}"
            question, qdate = inst["question"], inst.get("question_date", "")
            row = {"qid": inst["question_id"], "type": inst["question_type"]}

            probe = search_memories({"query": question, "filters": {"user_id": scope}, "top_k": 84})
            if not probe.get("results"):
                print(f"  [{qi}] {inst['question_id']} 스코프 비어 있음 — 건너뜀", flush=True)
                continue
            if "A" in args.arms:
                lines = [f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}"
                         for m in probe.get("results") or []]
                # 공개 상한 (1차 실행 후 정정 기록): 일부 multi-session 덤프가 24k
                # 서버 창을 초과해 400 — 덤프도 리더 창에서 잘리는 것이 실무이므로
                # A = "top-84, 추정 18k 토큰까지, 순위 보존·꼬리 탈락"으로 명시한다.
                # 바늘은 거의 항상 상위권(MRR 0.914)이라 증거 탈락은 드물다.
                while lines and sum(len(l) for l in lines) // 4 > 18000:
                    lines.pop()
                ctx = "\n".join(lines)
                hyp = read_answer(question, qdate, ctx)
                row["A"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["A_tok"] = token_est(ctx)
                row["A_hyp"] = hyp[:200]

            if any(a in args.arms for a in "BCDEGHRWV"):
                def assembled(query: str):
                    r = assemble_context({"query": query, "filters": {"user_id": scope},
                                          "top_k": int(os.environ.get("LME_B_TOPK", "10")),
                                          "budget_tokens": int(os.environ.get("LME_B_BUDGET", "2000")), "record_trace": False,
                                          "disable_resume_workspace": True})
                    memories = r.get("memories") or []
                    lines = [f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}"
                             for m in memories]
                    return "\n".join(lines), {str(m.get("id")) for m in memories}

            if "B" in args.arms:
                ctx, _ = assembled(question)
                hyp = read_answer(question, qdate, ctx)
                row["B"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["B_tok"] = token_est(ctx)
                row["B_hyp"] = hyp[:200]

            if "C" in args.arms:
                try:
                    expansion = expand_query(question, qdate)
                except Exception:
                    expansion = ""
                ctx, _ = assembled(f"{question} {expansion}".strip())
                hyp = read_answer(question, qdate, ctx)
                row["C"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["C_tok"] = token_est(ctx)
                row["C_exp"] = expansion[:150]
                row["C_hyp"] = hyp[:200]

            def make_groper():
                ctx0, seen = assembled(question)
                def searcher(q: str):
                    res = search_memories({"query": q, "filters": {"user_id": scope}, "top_k": 10})
                    results = res.get("results") or []
                    top = max((float(m.get("score") or 0) for m in results), default=0.0)
                    lines = []
                    for m in results:
                        mid = str(m.get("id"))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        lines.append(f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}")
                    return "\n".join(lines), top
                return ctx0, searcher

            if "D" in args.arms:
                ctx0, searcher = make_groper()
                hyp, dtok, nsrch, dctx = read_groping(question, qdate, ctx0, searcher)
                row["D"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["D_tok"] = dtok
                row["D_srch"] = nsrch
                row["D_ctx"] = dctx
                row["D_hyp"] = hyp[:200]

            if "E" in args.arms:
                ctx0, searcher = make_groper()
                chk = evidence_checklist(question, qdate)
                hyp, etok, nsrch, ectx = read_groping(question, qdate, ctx0, searcher,
                                                      checklist=chk)
                row["E"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["E_tok"] = etok + token_est(chk)
                row["E_srch"] = nsrch
                row["E_ctx"] = ectx
                row["E_chk"] = chk[:200]
                row["E_hyp"] = hyp[:200]

            if "G" in args.arms:
                ctx0, searcher = make_groper()
                hyp, gtok, nsrch, gctx = read_groping(question, qdate, ctx0, searcher,
                                                      external_gates=True)
                row["G"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["G_tok"] = gtok
                row["G_srch"] = nsrch
                row["G_ctx"] = gctx
                row["G_hyp"] = hyp[:200]

            if "R" in args.arms:
                ctx0, searcher = make_groper()
                route_g = bool(MULTI_EVIDENCE_RE.search(question))
                if route_g:
                    hyp, rtok, nsrch, rctx = read_groping(question, qdate, ctx0, searcher,
                                                          external_gates=True)
                else:
                    chk = evidence_checklist(question, qdate)
                    hyp, rtok, nsrch, rctx = read_groping(question, qdate, ctx0, searcher,
                                                          checklist=chk)
                    rtok += token_est(chk)
                row["R"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["R_tok"] = rtok
                row["R_srch"] = nsrch
                row["R_route"] = "G" if route_g else "E"
                row["R_hyp"] = hyp[:200]

            if "H" in args.arms:
                ctx0, searcher = make_groper()
                chk = evidence_checklist(question, qdate)
                hyp, htok, nsrch, hctx = read_groping(question, qdate, ctx0, searcher,
                                                      checklist=chk, external_gates=True)
                row["H"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["H_tok"] = htok + token_est(chk)
                row["H_srch"] = nsrch
                row["H_ctx"] = hctx
                row["H_hyp"] = hyp[:200]

            if "W" in args.arms:
                from forget.worldmodel import rebuild as wm_rebuild
                bench_db = os.environ.get("MEM1_DB_PATH", "")
                wm_dir = Path(os.environ.get("LME_WM_DIR",
                                             str(Path(bench_db).parent / "lme_wm")))
                wm_dir.mkdir(parents=True, exist_ok=True)
                wm_path = wm_dir / f"{scope}.sqlite3"
                if not wm_path.exists():
                    wm_rebuild(str(wm_path), bench_db, user_id=scope)
                wblock, n_kw = world_block_for(question, str(wm_path))
                ctx0, searcher = make_groper()
                hyp, wtok, nsrch, wctx = read_groping(question, qdate, ctx0, searcher,
                                                      external_gates=True,
                                                      world_block=wblock or None)
                row["W"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["W_tok"] = wtok
                row["W_srch"] = nsrch
                row["W_ctx"] = wctx
                row["W_kw"] = n_kw
                row["W_world"] = wblock[:300]
                row["W_hyp"] = hyp[:200]

            if "P" in args.arms:
                ctx0, searcher = make_groper()
                hyp, ptok, nsrch, pctx = read_groping(question, qdate, ctx0, searcher,
                                                      external_gates=True,
                                                      preference_probe=True)
                row["P"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["P_tok"] = ptok
                row["P_srch"] = nsrch
                row["P_hyp"] = hyp[:200]

            if "V" in args.arms:
                from forget.worldmodel import rebuild as wm_rebuild
                bench_db = os.environ.get("MEM1_DB_PATH", "")
                wm_dir = Path(os.environ.get("LME_WM_DIR",
                                             str(Path(bench_db).parent / "lme_wm")))
                wm_dir.mkdir(parents=True, exist_ok=True)
                wm_path = wm_dir / f"{scope}.sqlite3"
                if not wm_path.exists():
                    wm_rebuild(str(wm_path), bench_db, user_id=scope)
                vblock, v_kw = world_block_v2(question, str(wm_path))
                ctx0, searcher = make_groper()
                hyp, vtok, nsrch, vctx = read_groping(question, qdate, ctx0, searcher,
                                                      external_gates=True,
                                                      world_block=vblock or None)
                row["V"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["V_tok"] = vtok
                row["V_srch"] = nsrch
                row["V_ctx"] = vctx
                row["V_kw"] = v_kw
                row["V_inj"] = bool(vblock)
                row["V_world"] = vblock[:300]
                row["V_hyp"] = hyp[:200]

            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            marks = " ".join(f"{a}={'O' if row.get(a) else 'X'}" for a in args.arms if a in row)
            print(f"  [{qi}] {inst['question_type'][:18]:18s} {marks} "
                  f"(tok A:{row.get('A_tok','-')} B:{row.get('B_tok','-')} C:{row.get('C_tok','-')}"
                  f" D:{row.get('D_tok','-')}/{row.get('D_srch','-')}회)",
                  flush=True)

    rows = [json.loads(l) for l in open(OUT)]
    seen = {}
    for r in rows:
        seen[r["qid"]] = r
    rows = list(seen.values())
    print(f"\n{len(rows)}문항 · {time.time()-t0:.0f}s")

    def acc(arm, subset=None):
        vals = [r for r in rows if arm in r and (subset is None or r["type"] in subset)]
        return (sum(1 for r in vals if r[arm]) / len(vals), len(vals)) if vals else (float("nan"), 0)

    def tok(arm):
        vals = [r[f"{arm}_tok"] for r in rows if f"{arm}_tok" in r]
        return sum(vals) / len(vals) if vals else 0

    print(f"{'팔':4s} {'정확도':>7s} {'n':>4s} {'평균 토큰':>9s}")
    for arm in args.arms:
        a, n = acc(arm)
        print(f"{arm:4s} {a:7.3f} {n:4d} {tok(arm):9.0f}")
    if "A" in args.arms and "B" in args.arms:
        d = (acc("B")[0] - acc("A")[0]) * 100
        print(f"\nP-L2-A: B−A = {d:+.1f}pp → "
              + ("조립 우위" if d >= 3 else ("동급 (토큰 효율로 실질 승리)" if d > -3 else "조립 손실 — 해부 필요")))
    if "B" in args.arms and "C" in args.arms:
        target = {"temporal-reasoning", "multi-session"}
        d = (acc("C", target)[0] - acc("B", target)[0]) * 100
        side = (acc("C", None)[0] - acc("B", None)[0]) * 100
        print(f"P-L2-B: (temporal+multi) C−B = {d:+.1f}pp → "
              + ("접지 채택" if d >= 5 else ("기각" if d < 2 else "회색")) + f" · 전체 부작용 {side:+.1f}pp")
    if "D" in args.arms:
        srch = [r.get("D_srch", 0) for r in rows if "D" in r]
        if srch:
            print(f"P-L2-D 부기: 평균 검색 {sum(srch)/len(srch):.1f}회 · "
                  f"검색 0회 {sum(1 for s in srch if s == 0)}건 · "
                  f"5회 소진 {sum(1 for s in srch if s >= 5)}건 (판정은 A·B 참조점 대조로 원장에서)")
    if "W" in args.arms:
        wrows = [r for r in rows if "W" in r]
        if wrows:
            inj = sum(1 for r in wrows if r.get("W_kw", 0) > 0)
            print(f"P-WM-2 부기: 키워드 색인 주입 {inj}/{len(wrows)}문항 · "
                  f"평균 색인 줄 {sum(r.get('W_kw', 0) for r in wrows)/len(wrows):.2f} "
                  f"(판정 W−G는 lme_L2_G_rows.jsonl과 qid 짝지어 원장에서)")
    if "V" in args.arms:
        vrows = [r for r in rows if "V" in r]
        if vrows:
            inj = sum(1 for r in vrows if r.get("V_inj"))
            zero = sum(1 for r in vrows if r.get("V_srch", 0) == 0)
            print(f"P-WM-2b 부기: 주입 {inj}/{len(vrows)}문항(붕괴 게이트로 침묵 "
                  f"{len(vrows) - inj}) · 검색 0회 {zero}건[M3 지표] "
                  f"(판정 V−G는 lme_L2_G_rows.jsonl과 qid 짝지어 원장에서)")
    for qtype in sorted({r['type'] for r in rows}):
        line = f"  {qtype:26s}"
        for arm in args.arms:
            a, n = acc(arm, {qtype})
            line += f" {arm}:{a:.2f}(n={n})"
        print(line)


if __name__ == "__main__":
    main()
