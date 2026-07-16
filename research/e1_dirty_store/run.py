"""E1 pilot — Dirty-Store Recall v0.

Pre-registered design: research/e1_dirty_store/design.md (criteria fixed
before results). Runs against the local forget server.

    python research/e1_dirty_store/run.py [--url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import random
import sys

import httpx

# --- facts: 30 simple (unique key token) + 10 update pairs -----------------

SIMPLE_FACTS = [
    ("백업은 Restic으로 매일 밤 자동으로 돌린다", "백업 도구 뭐 쓰기로 했지?", "restic"),
    ("DB 마이그레이션 도구는 Alembic으로 확정했다", "마이그레이션 도구 뭐였지?", "alembic"),
    ("사내 위키는 Outline을 셀프호스트해서 쓴다", "위키 뭐 쓰지?", "outline"),
    ("서버 모니터링은 Netdata로 본다", "모니터링 도구 뭐였지?", "netdata"),
    ("웹 폰트는 Pretendard만 허용하기로 했다", "폰트 뭐 쓰기로 했지?", "pretendard"),
    ("스테이징 리전은 ap-northeast-2 서울이다", "스테이징 리전 어디지?", "ap-northeast-2"),
    ("로그 보존 기간은 37일로 정했다", "로그 며칠 보관하지?", "37"),
    ("에러 트래킹은 GlitchTip을 쓴다", "에러 트래킹 뭐 쓰지?", "glitchtip"),
    ("사내 메신저 봇 이름은 도토리다", "우리 봇 이름 뭐지?", "도토리"),
    ("코드 리뷰는 두 명 승인 필수다", "리뷰 승인 몇 명 필요하지?", "두 명"),
    ("API 게이트웨이는 Kong으로 통일했다", "게이트웨이 뭐 쓰지?", "kong"),
    ("시크릿 관리는 Infisical로 한다", "시크릿 어디서 관리하지?", "infisical"),
    ("주간 회고는 금요일 오후 4시다", "회고 언제 하지?", "금요일"),
    ("이미지 CDN은 Bunny를 쓴다", "이미지 CDN 뭐였지?", "bunny"),
    ("결제 웹훅 재시도 한도는 6회다", "웹훅 재시도 몇 번까지지?", "6"),
    ("테스트 커버리지 하한은 72%로 정했다", "커버리지 기준 몇 프로지?", "72"),
    ("사옥 와이파이 비번은 회의실 화이트보드에 있다", "와이파이 비번 어디 있지?", "화이트보드"),
    ("고객 문의 SLA는 영업일 기준 하루다", "문의 응답 SLA가 어떻게 되지?", "하루"),
    ("데이터 웨어하우스는 DuckDB 기반이다", "웨어하우스 뭐 쓰지?", "duckdb"),
    ("사내 발표자료 템플릿은 Marp로 만든다", "발표자료 뭐로 만들지?", "marp"),
    ("온보딩 버디는 입사 후 2주간 배정된다", "온보딩 버디 기간 얼마지?", "2주"),
    ("장애 등급은 SEV1부터 SEV4까지 4단계다", "장애 등급 몇 단계지?", "sev"),
    ("프론트 상태관리는 Zustand로 통일했다", "상태관리 라이브러리 뭐지?", "zustand"),
    ("사내 도메인 메일은 Fastmail로 옮겼다", "메일 어디 쓰지?", "fastmail"),
    ("계약서 서명은 Modusign으로 받는다", "전자서명 뭐 쓰지?", "modusign"),
    ("주문 번호 접두사는 ORD- 형식이다", "주문 번호 형식 뭐지?", "ord-"),
    ("클라우드 비용 알림 임계값은 월 80만원이다", "비용 알림 기준 얼마지?", "80"),
    ("QA 환경 초기화는 매주 월요일 새벽이다", "QA 환경 언제 리셋되지?", "월요일"),
    ("사용자 인터뷰 사례금은 5만원 상품권이다", "인터뷰 사례금 얼마지?", "5만원"),
    ("연차 신청은 Flex에서 한다", "연차 어디서 신청하지?", "flex"),
]

UPDATE_PAIRS = [
    ("주력 에디터는 Vim이다", "주력 에디터를 Vim에서 Zed로 바꿨다", "지금 주력 에디터 뭐지?", "zed", "vim"),
    ("CI는 Jenkins를 쓴다", "CI를 Jenkins에서 Buildkite로 이전했다", "지금 CI 뭐 쓰지?", "buildkite", "jenkins"),
    ("사무실은 대전 궁동이다", "사무실을 대전에서 판교로 옮겼다", "사무실 지금 어디지?", "판교", "대전"),
    ("기본 브랜치는 master다", "기본 브랜치를 master에서 trunk로 변경했다", "기본 브랜치 이름 뭐지?", "trunk", "master"),
    ("패키지 매니저는 npm이다", "패키지 매니저를 npm에서 pnpm으로 바꿨다", "패키지 매니저 뭐 쓰지?", "pnpm", "npm"),
    ("디자인 툴은 Figma다", "디자인 툴을 Figma에서 Penpot으로 전환했다", "디자인 툴 지금 뭐지?", "penpot", "figma"),
    ("원두 구독은 브라질 산투스다", "원두 구독을 브라질에서 에티오피아 예가체프로 바꿨다", "요즘 원두 뭐 마시지?", "에티오피아", "브라질"),
    ("업무 노트북은 M2 맥북이다", "업무 노트북을 M2에서 M4 맥북으로 교체했다", "지금 노트북 뭐지?", "m4", "m2"),
    ("사내 VPN은 Tailscale이다", "VPN을 Tailscale에서 Netbird로 이전했다", "VPN 지금 뭐 쓰지?", "netbird", "tailscale"),
    ("요금제는 Pro 플랜이다", "요금제를 Pro에서 Team 플랜으로 올렸다", "지금 요금제 뭐지?", "team", "pro"),
]

# --- junk: seeded expansion of REAL junk from the 2026-07-13 store audit ----

JUNK_SEEDS = [
    "API 비용을 줄이거나 (출처: github.com)",
    "특히 AI 제품 만들 (출처: dev.to)",
    "데이터는 모두 암호화되고 외부 추적이 (출처: hmans.dev)",
    "[근데누가사] 로컬 LLM 운영 완전정복 가이드를 다뤘다 — 깃허브에 리포가 1200 포인트를 받았어요.",
    "[이게된다고] 구조 읽고 추론하는 멀티모달 AI를 다뤘다 — 기초 모델이 나왔어요.",
    "[어떻게짰대] 캐시 경쟁을 피하려면 128바이트로 정렬하세요를 다뤘다.",
    "직접 서버에 설치해 쓸 수 있고, 가볍고 빠르며 음성·화상통화도 지원합니다.",
    "GitHub에서 1600+ 포인트를 받았으니 실제 연구자들이 반겨주는 수준이라고 봐요.",
    "이론상 64바이트면 되지만 실제로는 Intel (출처: monoid.github.io)",
    "모든 메시지를 자동 스캔하는 이 법안이 여름 휴회 직전 331대304로 가결된 거죠.",
    "커뮤니티에서도 누군가 이 주제를 꺼냈을 때 28명이 공감했다는 건 (출처: dev.to)",
    "본문 발췌만 있어서 정확한 내용은 알 수 없지만, 포인트 124를 받은 걸 보면 주목받는 소식 같아요.",
    "연동 점검용 기억 — 오프레코 운영 콘솔에서 기록함",
    "작년 증가량(7TWh)보다 올해가 거의 2배(12TWh) 급증했다는 게 놀랍죠.",
    "마치 우리가 뭔가를 생각할 때 일부만 의식하듯이, 모델도 무언의 사고공간에서 (출처: anthropic.com)",
]

CHANNELS = ["근데누가사", "이게된다고", "어떻게짰대", "이거봤어요", "거기서봤는데", "또투자받았대"]
TOPICS = [
    "새 오픈소스 벡터 검색 라이브러리", "경량 임베딩 모델", "러스트 재작성 사례", "GPU 가격 동향",
    "에이전트 프레임워크 비교", "정적 사이트 생성기", "모노레포 빌드 도구", "쿠버네티스 대안",
    "타입 시스템 논쟁", "개발자 번아웃 설문", "AI 규제 표결", "스타트업 펀딩 뉴스",
]
SOURCES = ["github.com", "dev.to", "huggingface.co", "techcrunch.com", "news.ycombinator.com", "arxiv.org"]


def build_junk(count: int, rng: random.Random) -> list[str]:
    pool = list(JUNK_SEEDS)
    while len(pool) < count:
        kind = rng.random()
        channel, topic, source = rng.choice(CHANNELS), rng.choice(TOPICS), rng.choice(SOURCES)
        points = rng.randint(40, 1900)
        if kind < 0.4:
            pool.append(f"[{channel}] {topic}를 다뤘다 — 커뮤니티에서 {points} 포인트를 받았어요.")
        elif kind < 0.7:
            pool.append(f"{topic} 관련해서 반응이 갈리는 것 같아요, 특히 성능 얘기가 (출처: {source})")
        else:
            pool.append(f"{topic}의 요점은 결국 비용인데, 자세한 건 본문 참고 (출처: {source})")
    rng.shuffle(pool)
    return pool[:count]


def ingest(client: httpx.Client, scope: str, text: str, created_at: str, infer: bool) -> int:
    """Returns number of memories stored for this submission."""
    payload: dict = {"infer": infer, "user_id": scope, "app_id": "e1", "created_at": created_at}
    if infer:
        payload["messages"] = [{"role": "user", "content": text}]
    else:
        payload["text"] = text
    response = client.post("/v1/memories/", json=payload)
    response.raise_for_status()
    body = response.json()
    items = body if isinstance(body, list) else body.get("results") or ([body] if body.get("id") else [])
    return len([item for item in items if item.get("id")])


def search(client: httpx.Client, scope: str, query: str, top_k: int = 3) -> list[dict]:
    response = client.post("/v3/memories/search/", json={
        "query": query, "top_k": top_k, "temporal_rerank": True,
        "filters": {"user_id": scope, "app_id": "e1"},
    })
    response.raise_for_status()
    return response.json()["results"]


def run_cell(client: httpx.Client, junk_ratio: float, gate: bool) -> dict:
    scope = f"e1-p{int(junk_ratio*100)}-{'gate' if gate else 'raw'}"
    client.request("DELETE", "/v1/memories/", json={"user_id": scope, "app_id": "e1"})
    rng = random.Random(42)

    facts_stored = 0
    fact_count = 0
    for text, _q, _tok in SIMPLE_FACTS:
        fact_count += 1
        facts_stored += 1 if ingest(client, scope, text, "2026-06-15T09:00:00", gate) > 0 else 0
    for old, new, _q, _new_tok, _old_tok in UPDATE_PAIRS:
        fact_count += 2
        facts_stored += 1 if ingest(client, scope, old, "2026-05-01T09:00:00", gate) > 0 else 0
        facts_stored += 1 if ingest(client, scope, new, "2026-07-01T09:00:00", gate) > 0 else 0

    junk_count = 0 if junk_ratio == 0 else round(fact_count * junk_ratio / (1 - junk_ratio))
    junk_stored = 0
    for i, junk in enumerate(build_junk(junk_count, rng)):
        day = 1 + (i % 28)
        junk_stored += 1 if ingest(client, scope, junk, f"2026-06-{day:02d}T12:00:00", gate) > 0 else 0

    hit1 = hit3 = 0
    for _text, query, token in SIMPLE_FACTS:
        results = search(client, scope, query)
        texts = [r["memory"].lower() for r in results]
        hit1 += 1 if texts and token in texts[0] else 0
        hit3 += 1 if any(token in t for t in texts) else 0

    current_truth = 0
    for _old, _new, query, new_tok, old_tok in UPDATE_PAIRS:
        results = search(client, scope, query)
        texts = [r["memory"].lower() for r in results]
        # success = the first result that mentions either state is the NEW
        # fact. (v0 scoring bug, disclosed: transition-phrased new facts
        # contain the old token, so "old_tok absent" could never pass.)
        for text in texts:
            if new_tok in text:
                current_truth += 1
                break
            if old_tok in text:  # stale fact outranked the update
                break

    return {
        "p": junk_ratio, "gate": gate,
        "hit@1": round(hit1 / len(SIMPLE_FACTS), 3),
        "hit@3": round(hit3 / len(SIMPLE_FACTS), 3),
        "current_truth": round(current_truth / len(UPDATE_PAIRS), 3),
        "fact_retention": round(facts_stored / fact_count, 3),
        "junk_rejection": round(1 - junk_stored / junk_count, 3) if junk_count else None,
        "store_rows": facts_stored + junk_stored,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()
    rows = []
    with httpx.Client(base_url=args.url, timeout=60) as client:
        for gate in (False, True):
            for p in (0.0, 0.3, 0.6, 0.88):
                cell = run_cell(client, p, gate)
                rows.append(cell)
                print(json.dumps(cell, ensure_ascii=False), flush=True)
    print("\n| p | gate | hit@1 | hit@3 | current-truth | fact-keep | junk-reject | rows |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['p']} | {'on' if r['gate'] else 'off'} | {r['hit@1']} | {r['hit@3']} "
              f"| {r['current_truth']} | {r['fact_retention']} | {r['junk_rejection']} | {r['store_rows']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
