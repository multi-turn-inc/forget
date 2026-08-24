"""W-트랙 SFT 궤적 채굴 v0 — 원장 memory_history → 쓰기-게이트 세계모델 훈련쌍.

§8.4 레시피(Qwen-AgentWorld의 개인화 번역)의 첫 기계화: 원장이 곧 궤적
데이터셋이다. 훈련 과제 v0 = **쓰기 게이트 모방** — (원발화) → (이 사람의
기준으로 오래갈 사실들). "무엇을 기억할 사람인가"가 정체성의 절반이므로,
이 쌍이 개인 델타(가중치 층)의 첫 교재가 된다.

쌍 구성: ADD 사건을 (input 해시, 같은 분) 단위로 묶어 발화 1 → 사실 N.
생애주기 태그: 이후 DELETE된 사실은 kept_final=False (편집자가 물린 수 —
훈련 시 가중 인하 후보). SUPERSEDE/CONFIRM/UPDATE는 저빈도(계 39건)라
전이 태그로만 부기. 음성 예시(게이트가 거른 발화)는 v1 (게이트 로그 원천
확인 필요 — observation_events엔 판정 컬럼 없음, 공시).

원장 접근은 SELECT만. 출력: research/eval/wm_sft_v0.jsonl (+ 통계 stdout).
등록은 훈련 시점에 (P-W-1로 예약) — 이 단계는 데이터셋 구축이라 숫자 판정 없음.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

LEDGER = str(Path.home() / ".forget" / "forget.sqlite3")
OUT = Path(__file__).resolve().parent.parent / "research/eval/wm_sft_v0.jsonl"


def norm_input(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def main() -> None:
    conn = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT event, input, new_memory, old_memory, memory_id, app_id, created_at "
        "FROM memory_history ORDER BY created_at"
    ).fetchall()
    deleted_ids = {r[0] for r in conn.execute(
        "SELECT DISTINCT memory_id FROM memory_history WHERE event = 'DELETE'")}
    conn.close()

    groups: dict[tuple, dict] = {}
    transitions = []
    # 원천 필터 (1차 실행이 잡은 오염 공시): history의 86%가 app_id=lme —
    # 벤치 인게스트 흔적(실기억은 전부 삭제됨, history는 append-only라 잔존).
    # 개인 세계모델의 교재는 이 사람의 삶뿐이다: forget·무표기만 채굴.
    PERSONAL_APPS = {"forget", ""}
    for event, inp, new_mem, old_mem, mid, app_id, created in rows:
        if str(app_id or "") not in PERSONAL_APPS:
            continue
        if event == "ADD":
            inp_n = norm_input(inp)
            if len(inp_n) < 12 or not norm_input(new_mem):
                continue
            key = (hashlib.sha1(inp_n.encode()).hexdigest()[:16], str(created or "")[:16])
            g = groups.setdefault(key, {
                "ts": str(created or ""), "app_id": str(app_id or ""),
                "input": inp_n[:2000], "facts": [], "kept_final": []})
            g["facts"].append(norm_input(new_mem)[:600])
            g["kept_final"].append(str(mid) not in deleted_ids)
        elif event in ("SUPERSEDE", "CONFIRM", "UPDATE"):
            transitions.append({"ts": str(created or ""), "op": event,
                                "old": norm_input(old_mem)[:400],
                                "new": norm_input(new_mem)[:400],
                                "memory_id": str(mid)})

    with open(OUT, "w") as f:
        for key, g in groups.items():
            f.write(json.dumps({"kind": "gate_pair", **g}, ensure_ascii=False) + "\n")
        for tr in transitions:
            f.write(json.dumps({"kind": "transition", **tr}, ensure_ascii=False) + "\n")

    n_pairs = len(groups)
    facts_per = [len(g["facts"]) for g in groups.values()]
    survive = sum(sum(g["kept_final"]) for g in groups.values())
    total_facts = sum(facts_per)
    apps = Counter(g["app_id"] for g in groups.values())
    print(f"게이트 쌍 {n_pairs:,} (발화→사실, 평균 {total_facts/max(n_pairs,1):.1f}사실/발화)")
    print(f"사실 총 {total_facts:,} · 최종 생존 {survive:,} ({survive/max(total_facts,1):.1%}) — "
          f"비생존은 편집자가 물린 수, 훈련 가중 인하 후보")
    print(f"전이 궤적 {len(transitions)} (SUPERSEDE/CONFIRM/UPDATE — 저빈도, 부기용)")
    print("원천 상위:", dict(apps.most_common(5)))
    print(f"출력: {OUT}")


if __name__ == "__main__":
    main()
