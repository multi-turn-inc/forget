#!/usr/bin/env python3
"""c66 — 도그푸드 :8000의 몸(설치본) 동일성 감사 (read-only, 2026-08-07).

계기: audit-60 R3 집행 중 oracle replay 커밋본(c59)이 재현되지 않았다.
  regime A 0=0 ✔ / regime B 7=7 ✔ / regime C 2 → **11** ✘
  동일 (질의, 기억) 쌍의 점수가 상승: c36 0.5755→0.7012, A10 0.4833→0.6378.
  regime C 25행 전원이 게이트 0.45를 통과 — 게이트가 판별력을 잃었다.

1차 증거로 확인된 몸의 교체:
  - 설치본 site-packages/forget + forget_ai-0.4.0.dist-info mtime = 08-06 16:45
  - :8000 보유 프로세스 pid 86942 start = 08-06 16:45:56 (etime 10:54:43)
  - c59 재생 실측 시각 = 08-06 03:38  → **c59는 구 스택, c66은 신 스택**
  - 그 사이 비-devloop 커밋: fd30a68 "body A1-A4: 턴 회상에 피드백 주소,
    평탄도 소음 게이트, **임베딩 경로 수리**" + 4222ce6 "capsule: 자기 슬롯"
  - 벤치 인스턴스 8600(08-03 기동)·8601(08-05 기동)은 별 포트 — 원칙 3 격리 유지

이 스크립트가 판정하는 것 (LOOP.md 원칙 3의 영수증 검사):
  ① 설치본이 P11 처치 1·2·3을 실제로 보유하는가
     — task_state가 10사이클간 "설치본 구본 가동"으로 게이트 대기에 올려둔 항목.
       보유가 확인되면 그 게이트 항목은 **이미 충족**이고 원장이 틀린 것이다.
  ② 신 스택의 점수 성분 구성 (score_breakdown 키)
  ③ 임베딩 공간 동일성 — 차원 분포로 재임베딩 영수증 유무를 본다

    .venv/bin/python research/devloop/scripts/c66_body_identity.py
"""
import glob
import os
import re

INSTALLED = glob.glob(os.path.expanduser(
    "~/.forget/venv/lib/python3*/site-packages/forget"))

MARKERS = {
    "P11 처치3 차원거부": r"dimension_mismatch|dim_mismatch|expected_dim|차원 불일치",
    "P11 처치1 effective스택": r"effective_stack|effective_provider|effective\[",
    "평탄도 소음게이트(fd30a68)": r"flatness|flat_gate|평탄도|noise_gate",
    "entity_boost 성분": r"entity_boost",
    "score_breakdown 반환": r"score_breakdown",
}


def scan(root):
    hits = {k: [] for k in MARKERS}
    nfiles = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            nfiles += 1
            p = os.path.join(dirpath, f)
            try:
                t = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for k, pat in MARKERS.items():
                if re.search(pat, t):
                    hits[k].append(os.path.relpath(p, root))
    return hits, nfiles


def main():
    print("c66 — 도그푸드 :8000 몸 동일성 감사")
    if not INSTALLED:
        print("설치본 미발견 — 판정 불가")
        return
    inst = INSTALLED[0]
    print(f"설치본: {inst}")
    di = glob.glob(os.path.expanduser("~/.forget/venv/lib/python3*/site-packages/forget_ai-*.dist-info"))
    for d in di:
        print(f"  dist-info: {os.path.basename(d)}")

    print("\n=== ① 설치본 마커 스캔 (P11 처치 보유 여부) ===")
    hits, nfiles = scan(inst)
    print(f"  스캔 {nfiles}개 .py")
    for k, v in hits.items():
        state = "**보유**" if v else "미보유"
        print(f"  {k:<26} {state:<8} {len(v)}파일 {v[:3]}")

    print("\n=== ② 저장소본 대조 (같은 마커) ===")
    repo = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))), "forget")
    if os.path.isdir(repo):
        rhits, rn = scan(repo)
        print(f"  스캔 {rn}개 .py ({repo})")
        for k, v in rhits.items():
            same = "일치" if bool(v) == bool(hits[k]) else "**불일치**"
            print(f"  {k:<26} 저장소={'보유' if v else '미보유':<6} "
                  f"설치본={'보유' if hits[k] else '미보유':<6} {same}")
    else:
        print(f"  저장소 forget/ 미발견: {repo}")

    print("\n=== ③ 파일 해시 대조 — 설치본이 저장소본에서 빌드됐는가 (결정적 채널) ===")
    print("  task_state가 10사이클간 유지한 주장: '저장소본이 3처치 보유·설치본 구본 가동'")
    if os.path.isdir(repo):
        import hashlib

        def digest(p):
            return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]

        same, diff, only_repo, only_inst = [], [], [], []
        rfiles = {f for f in os.listdir(repo) if f.endswith(".py")}
        ifiles = {f for f in os.listdir(inst) if f.endswith(".py")}
        for f in sorted(rfiles | ifiles):
            rp, ip = os.path.join(repo, f), os.path.join(inst, f)
            if f not in ifiles:
                only_repo.append(f)
            elif f not in rfiles:
                only_inst.append(f)
            elif digest(rp) == digest(ip):
                same.append(f)
            else:
                diff.append(f)
        tot = len(same) + len(diff)
        print(f"  최상위 .py 대조: 동일 {len(same)}/{tot}  상이 {len(diff)}/{tot}")
        print(f"  저장소만 {len(only_repo)}건 {only_repo}  설치본만 {len(only_inst)}건 {only_inst}")
        if diff:
            print(f"  **상이 파일**: {diff}")
        verdict = ("설치본 == 저장소본 (구본 가동 주장은 **거짓**)" if not diff and not only_repo
                   else "설치본 != 저장소본 — 상이분 존재, 구본 가동 주장 부분 성립")
        print(f"  판정: {verdict}")

    print("\nCAVEAT: ① 마커 정규식은 존재 증거이지 동작 증거가 아니다 — 보유가 곧 "
          "배선 완료는 아니며, 반대로 미검출이 부재의 증명도 아니다(리팩터로 이름이 "
          "바뀌었을 수 있다) ② 이 스캔은 설치본 디스크 상태이고, :8000 프로세스가 "
          "메모리에 적재한 코드는 기동 시점(08-06 16:45:56) 것이다 — 그 이후 디스크가 "
          "다시 바뀌었다면 둘은 또 다르다 ③ 원칙 3의 영수증(재임베딩)은 이 스크립트가 "
          "판정하지 않는다 — 차원 분포 감사는 embedding_space_audit.py 별도 채널.")


if __name__ == "__main__":
    main()
