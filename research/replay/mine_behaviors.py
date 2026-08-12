#!/usr/bin/env python3
"""행동-사례 채굴기 v0 — 4대 표적 중 어휘-포착 가능한 2종의 전수 수색.

일반화 요건(같은 방향, 다른 표면)을 채우는 도구: A급 9건과 같은 행동이
다른 문맥으로 등장한 장면을 코퍼스 전체에서 캔다. 각 사례 = (직전 어시스턴트
턴 = 음성 후보, 사용자 반응 = 판정 근거). 자동 승격 없음 — 검수 큐로만.

표적 A: 완료 주장 → 사용자 반박 (미검증 완료 주장의 다른 표면들)
표적 B: 대기 자세 → 사용자 재촉 (조기 중단의 다른 표면들)
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from mine_pairs import PROJECT_DIRS, _text_of, _decay

# 표적 A: 어시스턴트의 완료 선언 어휘 (강신호만 — "됐어/완료/완성/배포/고쳤/살아났/성공")
CLAIM = re.compile(r"(됐어|완료|완성했|배포 완료|배포했|고쳤어|수리했|살아났|성공했|끝났어|해결했)", re.U)
# ...에 대한 사용자의 반박 — 상태-부정 핵심어 필수 ("아니" 단독은 담화 표지가 태반)
REBUT_CORE = re.compile(r"(안 ?됐|안 ?되|안 ?바뀌|안 ?늘|안 ?보이|그대로인|여전히|잘못|틀렸|아닌데|어디가 (완|된)|다시 봐|허접|구린|별로)", re.U)

# 표적 B: 어시스턴트 말미의 대기 자세 (마지막 300자)
WAIT = re.compile(r"(말해줘|알려줘|골라줘|고르시면|기다릴게|결정만 남|승인하면|어떻게 할까|어디로 갈까|필요하면 말)", re.U)

# 표적 C: 명시적 칭찬 — 직전 어시스턴트 턴이 양성 SFT 시연 후보
PRAISE = re.compile(r"^(좋아|좋다|완벽|잘했|훌륭|오 |오오|굿|나이스|깔끔하|마음에 들|이게 맞|바로 그거)", re.U)
# ...에 대한 사용자의 재촉/자율 요구 — 서두 120자 내 탐색 ("아니 ~ 계속 가보자" 패턴)
PUSH = re.compile(r"(계속 (가|진행|해)|멈추지 ?마|왜 끊|왜 멈|이어서 (해|가)|알아서 (해|진행)|직접 (해|진행)|일을 몇시간이고|쉬지 말)", re.U)


def mine_file(path: Path, now: float) -> list[dict]:
    rows = []
    for lineno, line in enumerate(path.open(), 1):
        try:
            d = json.loads(line)
        except Exception:
            continue
        d["_line"] = lineno
        rows.append(d)

    out = []
    prev_assist_idx = None
    for i, d in enumerate(rows):
        if d.get("type") == "assistant":
            prev_assist_idx = i
            continue
        if d.get("type") != "user" or prev_assist_idx is None:
            continue
        user_text = _text_of((d.get("message") or {}).get("content"))
        if not user_text:
            continue
        assist_text = _text_of((rows[prev_assist_idx].get("message") or {}).get("content"))
        if not assist_text:
            continue

        cls = None
        if REBUT_CORE.search(user_text[:120]) and CLAIM.search(assist_text):
            cls = "claim_rebutted"
        elif PUSH.search(user_text[:120]) and WAIT.search(assist_text[-300:]):
            cls = "stall_pushed"
        elif PRAISE.match(user_text.strip()[:20]) and len(assist_text) > 300:
            cls = "praised"  # 양성 SFT 시연 (짧은 어시 턴은 칭찬 대상 특정이 안 돼 제외)
        if cls is None:
            continue
        out.append({
            "class": cls,
            "weight": 2.5,
            "priority": 2.5 * _decay(d.get("timestamp", ""), now),
            "rejected_head": assist_text[:400],
            "user_head": user_text.strip()[:200],
            "src": f"{path.name}:{d['_line']}",
            "ts": d.get("timestamp", ""),
        })
    return out


def main() -> None:
    now = time.time()
    found: list[dict] = []
    n = 0
    for pdir in PROJECT_DIRS:
        if not pdir.is_dir():
            continue
        for f in sorted(pdir.glob("*.jsonl")):
            if f.stat().st_size < 1024:
                continue
            n += 1
            found += mine_file(f, now)
    # 세션 포크 복제 제거 (내용 지문)
    seen = set()
    uniq = []
    for r in sorted(found, key=lambda r: -r["priority"]):
        fp = (r["class"], r["user_head"], r["rejected_head"][:120])
        if fp in seen:
            continue
        seen.add(fp)
        uniq.append(r)
    out_path = Path(__file__).parent / "behavior_cases_v0.jsonl"
    with out_path.open("w") as fh:
        for r in uniq:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"세션 {n}개 → 원시 {len(found)} → 중복제거 {len(uniq)}건 {dict(Counter(r['class'] for r in uniq))} → {out_path}")
    for r in uniq[:6]:
        print(f"[{r['class']} p={r['priority']:.2f}] 유저: {r['user_head'][:70]}")


if __name__ == "__main__":
    main()
