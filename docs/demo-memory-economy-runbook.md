# 기억 경제 데모 런북 — 멘토링 1:1용 (5분)

2026-08-28 작성. 대상: LB인베스트먼트 2차 멘토링 (온라인 화면공유).
서사: **"기억을 가진 에이전트 팀 — 지식은 흐르고, 개인정보는 안 흐르고, 모든
접근이 암호학적 영수증으로 남는다."** BM 문서의 검증 항목 3(공유 기억)의 실물.

## 사전 준비 (데모 전에 1회)

```bash
# ① 격리 forget (스파이크 DB — 어제 데이터 그대로 살아 있음)
cd ~/orca/workspaces/forget/내-프롬프트를-공유하기-싫어
SCRATCH="/private/tmp/claude-501/-Users-junghunkim-orca-workspaces-forget----------------/45dc8302-58e8-4d35-adce-c97499f29a78/scratchpad"
MEM1_DB_PATH="$SCRATCH/bbb_spike.sqlite3" .venv/bin/python -m uvicorn forget.server:app --port 43917 &

# ② botbotbot (워크스페이스 UI)
cd ~/orca/workspaces/forget/botbotbot
OPENAI_API_KEY="$(cat ~/.config/openai/lmev2.key)" FORGET_BASE_URL="http://127.0.0.1:43917" npm run dev &
# → http://localhost:5173

# ③ 그랜트 존재 확인 (없으면 생성)
curl -s http://127.0.0.1:43917/v1/grants/ | python3 -m json.tool | head -20
# 비어 있으면:
curl -s http://127.0.0.1:43917/v1/grants/ -X POST -H "Content-Type: application/json" \
  -d '{"grantee_pattern":"bbb-agent-*","scope_app":"botbotbot","quota":100}'
```

리허설 리셋(같은 대사 반복 연습 시): `rm "$SCRATCH/bbb_spike.sqlite3"` 후 ① 재기동
→ 그랜트 재생성.

## 데모 본편 (비트 4개, 각 ~1분)

**비트 1 — 팀 기억 심기.** 워크스페이스(localhost:5173)에서 대화 A를 열고:
> "팀 공유로 기억해줘: 다음 고객 미팅은 9월 3일이고, 담당자 연락처는
> 010-4821-7733이야. 짧게 확인만."

**비트 2 — 새 에이전트가 기억하되, 개인정보는 못 본다.** 대화 B(완전 새
세션)를 열고:
> "다음 고객 미팅이 언제지? 담당자 연락처도 알려줘."

기대 답: 미팅 **9월 3일** (지식이 팀을 건넜다) + 연락처는 **[redacted-phone]**
(출구 검문 — B의 모델에 닿기 전에 가려져서 유출 능력 자체가 없음).
→ 여기서 한 문장: *"프라이버시가 프롬프트 부탁이 아니라 코드 구조입니다."*

**비트 3 — 모든 접근이 영수증으로.** 터미널 전환:
```bash
curl -s "http://127.0.0.1:43917/v1/receipts/access/?limit=5" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    print(f\"{p['at'][11:19]} {p['grantee']:14} allowed={p['allowed']} served={p['items_served']} redactions={p['redactions']}\")"
```
가림 횟수까지 찍힌 접근 원장. 거부(allowed=False)도 남는다는 것 강조 —
*"안 나간 것까지 감사 대상입니다."*

**비트 4 — 서버를 안 믿어도 영수증은 진짜다 (Ed25519).**
```bash
curl -s http://127.0.0.1:43917/v1/receipts/public_key/   # 공개키
# 제3자 검증 시뮬 (서버 코드·비밀키 없이 공개키만으로):
curl -s "http://127.0.0.1:43917/v1/receipts/access/?limit=1" | .venv/bin/python -c "
import json,sys
from nacl.signing import VerifyKey
r=json.load(sys.stdin)[0]
body={k:v for k,v in r.items() if k not in ('signature_hmac_sha256','signature_ed25519','public_key_ed25519')}
payload=json.dumps(body,ensure_ascii=False,sort_keys=True).encode()
VerifyKey(bytes.fromhex(r['public_key_ed25519'])).verify(payload,bytes.fromhex(r['signature_ed25519']))
print('영수증 서명 검증: VALID (공개키만으로)')"
```
→ 마무리 문장: *"삭제 증명·접근 감사가 규제 산업(L2)에 파는 상품이고,
이 영수증 인프라가 그 기반입니다."*

## 예비 (질문 대비)

- **"에이전트끼리 실제로 협업하나?"** → 우리 개발 자체가 실사례: Claude와
  Codex 세션이 이 공유 원장으로 사람 복붙 없이 설계 합의·반박·수렴함
  (합의 원장, 인증 귀속, 응답 권한 규칙까지 — 우리가 첫 팀 사용자).
- **"검문을 우회하면?"** → 쓰기 단일 문(team_note/serve)·자격 결합·영수증
  선기록(영수증 없으면 서빙 무효)이 전부 서버 집행 + 계약 테스트 763개.
- **"벤치마크는?"** → LongMemEval-V2 제출 완료(8/20)·게재 대기 — 리더보드
  자체가 아직 미개장(전 시스템 공통)임을 병기.

## 실패 대비 폴백

- UI가 안 뜨면: 비트 1·2를 curl로 (FORGET_INTEGRATION.md의 /api/pi/prompt 예시).
- 모델 응답 지연: 비트 2의 기대 답 스크린샷을 미리 찍어 백업.
- 43917 죽음: `lsof -i :43917`로 확인 후 ① 재기동 (데이터는 DB 파일에 영속).
