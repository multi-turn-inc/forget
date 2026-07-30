# MemoryArena × forget — 파일럿 (2026-07-30)

[MemoryArena](https://memoryarena.github.io/) (arXiv 2602.16313, Stanford·UCSD·UIUC·Princeton)는
상호의존 멀티세션 에이전트 태스크로 기억 시스템을 재는 2세대 벤치마크다.
LongMemEval 이후 세대에서 forget이 어디에 서는지 보려고 파일럿을 돌렸다.

## 한 일
- `forget_adapter.py` — MemoryArena 메모리 시스템 프로토콜(initialize/add/wrap_user_prompt) 구현.
  `memory/memory_systems/forget.py`로 복사하고 `MEMORY_FACTORIES`에 `"forget"` 등록하면 붙는다.
  등록된 시스템 중 **유일하게 API 키 없이 로컬에서 도는 시스템**이며, 회수 결과에 trust 라벨을 실어 보낸다.
- 환경: `formal_reasoning_math` (40논문 × 5연쇄문항). 파일럿은 앞 2논문 = 10문항.
- 에이전트·판정: gpt-5-mini. forget은 전용 인스턴스(포트 8010, 별도 DB)에서 실행 — 도그푸드 스토어 불변.

## 결과 (n=10, 통계적 의미 없음 — 파이프라인 검증용)
| 구성 | 정답 | 평균 회수 컨텍스트 |
|---|---|---|
| forget | 7/10 | 3,557자 |
| BM25 (대조군) | 7/10 | 3,168자 |

**문항별 정오가 10/10 완전 일치.** 두 시스템이 맞힌 문항도, 틀린 문항도 동일.

## 배운 것
1. **`formal_reasoning_math`는 기억 시스템 변별력이 없다** (적어도 이 규모·이 에이전트에서).
   연구 수학 증명에서 병목은 회수가 아니라 에이전트의 수학 능력이다. 기억을 바꿔도 결과가 안 움직인다.
   → 다음 실측은 제품 논지에 가까운 `bundled_shopping` / `progressive_search`에서.
   → MemDelta(2606.29914)의 경고 그대로: 대조군 없이는 어떤 메모리 숫자도 해석 불가.
2. **벤치 설정과 모델의 불일치가 조용히 0점을 만든다.** 1차 실행은 10/10 오답이었는데,
   원인은 기억이 아니라 `temperature: 0.0` — gpt-5 계열이 400으로 거부하고 에이전트가 이를 빈 문자열로 삼켰다.
   판정은 정직하게 전부 False를 찍었다. 벤치 결과를 볼 때 **"0점"은 성능이 아니라 배선 실패일 수 있다.**
3. forget 어댑터는 정상 작동: 문항이 진행될수록 회수 컨텍스트가 누적(36자 → 7,895자)되며
   앞 문항의 과제·풀이가 뒤 문항에 실려 들어갔다.

## 업스트림 기여 후보 (로컬 패치로 검증됨)
- `run_math.py`가 `main()`을 두 번 호출 — 전체 벤치를 2회 태운다(비용 2배). 
- `memory_systems/__init__.py`가 모든 서드파티 SDK를 즉시 임포트 — 하나만 없어도 서버 전체가 죽는다. 선택적 임포트 필요.
- 파일럿용 `--limit N` 옵션 부재.

## 재현
```bash
git clone https://github.com/ZexueHe/MemoryArena.git && cd MemoryArena
cp <forget>/research/memoryarena/forget_adapter.py memory/memory_systems/forget.py
# MEMORY_FACTORIES에 "forget": ForgetMemorySystem 등록
FORGET_BASE_URL=http://127.0.0.1:8010 python memory/server.py   # 메모리 서버
python env/env_server.py                                        # 환경 서버
python run_math.py -c configs/formal_reasoning_configs/math_forget.json --limit 2
```
