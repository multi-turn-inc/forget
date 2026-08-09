#!/usr/bin/env python3
"""c92 보조 — 대장의 번호 공간 조회(관측 N·유형 F·예측 P). 읽기 전용."""
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parents[1]

fr = (BASE / "frictions.md").read_text(encoding="utf-8")
pr = (BASE / "predictions.md").read_text(encoding="utf-8")

heads = re.findall(r"^##+ .*$", fr, flags=re.M)
print("[frictions.md 마지막 섹션 헤딩 12개]")
print("\n".join(heads[-12:]))

obs = sorted(set(int(n) for n in re.findall(r"관측\s*(\d+)", fr)))
print("\n[관측 번호 (frictions.md)]", obs[-10:])
obs_p = sorted(set(int(n) for n in re.findall(r"관측\s*(\d+)", pr)))
print("[관측 번호 (predictions.md)]", obs_p[-10:])

ftypes = sorted(set(int(n) for n in re.findall(r"\bF(\d+)\b", fr)))
print("[유형 F 번호]", ftypes)

preds = sorted(set(int(n) for n in re.findall(r"\bP(\d+)", pr)))
print("[예측 P 번호]", preds[-12:])
