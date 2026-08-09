"""c88 앵커 1차 증거 검증 — №0003(차트의 forget 점)의 컨피그 좌표를 run summary에서 직접 읽는다.

원칙: 공개할 숫자는 그 숫자를 만든 파일의 해당 필드를 직접 열어 확인한다.
(c88 R3 프로브가 miss한 매핑 — 관측 40 — 을 1차 증거로 재확정하고 노트에 박는다.)
"""
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parents[3] / "research/longmemeval/runs"
TARGETS = ["local-v3-probe", "local-v3-r2", "local-v3-r3-merged"]

for name in TARGETS:
    p = RUNS / f"{name}.summary.json"
    if not p.exists():
        print(f"{name}: summary 없음")
        continue
    s = json.loads(p.read_text(encoding="utf-8"))
    keys = ("accuracy", "top_k", "mode", "granularity", "n", "reader_model",
            "observer_model", "reader_version", "temporal_rerank", "obs_k")
    flat = {k: s.get(k) for k in keys if k in s}
    cfg = s.get("config") or s.get("args") or {}
    if isinstance(cfg, dict):
        for k in keys:
            if k in cfg and k not in flat:
                flat[k] = cfg[k]
    print(f"{name}: {json.dumps(flat, ensure_ascii=False)}")
    if not flat:
        print(f"   (키 목록: {sorted(s.keys())})")
