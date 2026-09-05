"""c83 종단 검증 — 실제 git이 만든 porcelain 출력으로 관측 38 처치를 검사한다.

단위 테스트(tests/test_devloop_step0_parsing.py)는 손으로 쓴 porcelain 문자열을
단언한다 — 그 문자열이 git의 실제 출력과 다르면 테스트는 통과하고 계기는 틀린다.
이 스크립트는 그 간극을 닫는다: 일회용 저장소에서 ① 한국어 파일명 리네임(스테이지)
② 한국어 미추적 파일을 만들고, core.quotepath=true(기본값 방향을 명시 고정)의
porcelain 원문을 porcelain_changed_paths에 통과시켜 반환 경로가 **디스크에 실재하는
문자열**인지 단언한다. 실DB·본 저장소 무접촉, 산출물은 tempfile 아래에만 생겼다 사라진다.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c48_step0_check.py")

spec = importlib.util.spec_from_file_location("c48", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

work = tempfile.mkdtemp(prefix="c83_porcelain_e2e_")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", work, *args], capture_output=True, text=True)


try:
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    with open(os.path.join(work, "원본노트.md"), "w", encoding="utf-8") as fh:
        fh.write("a\n")
    with open(os.path.join(work, "keep.md"), "w", encoding="utf-8") as fh:
        fh.write("b\n")
    git("add", "-A")
    git("commit", "-qm", "init")
    git("mv", "원본노트.md", "새 이름.md")
    with open(os.path.join(work, "한글미추적.md"), "w", encoding="utf-8") as fh:
        fh.write("c\n")

    raw = subprocess.run(
        ["git", "-C", work, "-c", "core.quotepath=true", "status", "--porcelain"],
        capture_output=True, text=True).stdout
    print("porcelain 원문:")
    for line in raw.splitlines():
        print(f"  {line!r}")

    paths = c48.porcelain_changed_paths(raw)
    print(f"parsed: {paths}")
    exists = {p: os.path.exists(os.path.join(work, p)) for p in paths}
    print(f"exists: {exists}")
    assert exists.get("새 이름.md") is True, "리네임 new 경로 미감지"
    assert exists.get("한글미추적.md") is True, "한국어 미추적 경로 미감지"
    assert exists.get("원본노트.md") is False, "old 경로는 디스크에 없어야 함(D 행 취급)"
finally:
    shutil.rmtree(work, ignore_errors=True)

print("E2E OK — 리네임 new + 한국어 경로 모두 디스크 실재 문자열로 복원, old는 exists 필터로 탈락")
sys.exit(0)
