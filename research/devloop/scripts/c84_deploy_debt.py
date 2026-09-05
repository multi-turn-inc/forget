"""c84 배포 부채 계량 — 설치본(살아 있는 몸) vs 저장소 제품 파일의 발산 실측.

read-only · LLM 0 · $0. 후보 ① 문면의 "⑮ 배포 패키지 비대화 주의 병기"를 수치로 이행한다.
비교 대상: ~/.forget/venv/.../site-packages/forget (몸) vs ./forget (저장소).
판정 문장은 이 파일에 쓰지 않는다 — 출력에만 산다(관측 32 보강 규약: 독스트링은 아무것도
막지 않는다).
"""
import difflib
import glob
import os

INST = sorted(glob.glob(os.path.expanduser(
    "~/.forget/venv/lib/python3*/site-packages/forget")))
REPO = os.path.join(os.path.dirname(__file__), "..", "..", "..", "forget")


def py_files(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                full = os.path.join(dirpath, fn)
                out[os.path.relpath(full, root)] = full
    return out


def main():
    if not INST:
        print("[!] 설치본 미발견 — ~/.forget/venv 경로 확인")
        return
    inst_root, repo_root = INST[0], os.path.abspath(REPO)
    dist = sorted(glob.glob(os.path.expanduser(
        "~/.forget/venv/lib/python3*/site-packages/forget_ai-*.dist-info")))
    print(f"[몸] {inst_root}")
    print(f"[dist-info] {[os.path.basename(d) for d in dist]}")
    print(f"[저장소] {repo_root}")

    inst, repo = py_files(inst_root), py_files(repo_root)
    keys = sorted(set(inst) | set(repo))
    same, diverged, only_inst, only_repo = [], [], [], []
    for k in keys:
        if k not in inst:
            only_repo.append(k)
        elif k not in repo:
            only_inst.append(k)
        else:
            a = open(inst[k], encoding="utf-8", errors="surrogateescape").read()
            b = open(repo[k], encoding="utf-8", errors="surrogateescape").read()
            if a == b:
                same.append(k)
            else:
                al, bl = a.splitlines(), b.splitlines()
                plus = minus = 0
                for line in difflib.unified_diff(al, bl, lineterm="", n=0):
                    if line.startswith("+") and not line.startswith("+++"):
                        plus += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        minus += 1
                diverged.append((k, plus, minus))

    total = len(keys)
    print(f"\n[집계] 파일 합집합 {total} = 동일 {len(same)} + 발산 {len(diverged)}"
          f" + 설치본 단독 {len(only_inst)} + 저장소 단독 {len(only_repo)}")
    for k, plus, minus in diverged:
        print(f"  발산: {k}  +{plus} −{minus}")
    for k in only_inst:
        print(f"  설치본 단독: {k}")
    for k in only_repo:
        print(f"  저장소 단독: {k}")
    dsum = sum(p + m for _, p, m in diverged)
    print(f"\n[부채 크기] 발산 파일 {len(diverged)}개, diff 라인 합 {dsum}"
          f" (+{sum(p for _, p, _ in diverged)} −{sum(m for _, _, m in diverged)})")


if __name__ == "__main__":
    main()
