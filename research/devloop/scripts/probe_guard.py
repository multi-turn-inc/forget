"""일회용 프로브의 하드 실패 — 폴백을 갖지 않는다 (c158 신설, P45, c157 HAND 별건 3).

왜. c157의 `tmp/c157_hand_corpus.py`가

    hits = NC.scan(items) if hasattr(NC, "scan") else []

로 쓰였고 `scan`은 존재하지 않았다. `[]`가 **조용히** 반환돼 *"검출기 hit = 0건"*으로
인쇄됐다(계기 본체 직접 실행 시 실제 35문장). 원장에 닿기 전에 잡았으나 **한 번
보고됐다**. 계기 본체(`c48_step0_check` · `c129_negative_claims` · `harvest_stat`)는
전부 하드 가드를 갖췄고 **일회용 프로브만 갖추지 않았다** — 임시성이 면제 사유로
작동했고, 임시로 쓰는 도구일수록 실패를 0으로 위장하기 쉽다.

규약. 프로브에서 *"있으면 쓰고 없으면 넘어간다"*를 쓰지 말 것. 없으면 **터진다**:

    import sys; sys.path.insert(0, "research/devloop/scripts")
    from probe_guard import need

    scan = need(NC, "scan")      # 없으면 ProbeFailure — []가 아니다
    hits = scan(items)

두 팔이다. `need()` 계열은 **당 사이클** 차단(프로브가 import해야 작동)이고,
`scan_probes()`는 **다음 사이클** 인구조사다(c48 파트 X가 매 사이클 호출). 위상이
어긋나며 그 한계는 P45 한계 ①에 적었다 — 주기는 맞췄고 위상은 못 맞췄다.

이 모듈 자체의 검증: `.venv/bin/python research/devloop/scripts/probe_guard.py --selftest`.
계기가 자기 하드 가드를 갖지 않으면 같은 병을 한 층 위에서 반복한다.
"""

from __future__ import annotations

import ast
import glob
import os
import sys

# --- 하드 실패 -------------------------------------------------------------


class ProbeFailure(BaseException):
    """프로브의 전제가 깨졌다. 값을 지어내지 않고 죽는다.

    `Exception`이 아니라 `BaseException`을 상속한다 — 의도적이다. 이 예외가
    막으려는 패턴 중 하나가 `except Exception: pass`이고, 그 밑에 서면 하드
    실패가 다시 조용해진다. `KeyboardInterrupt`·`SystemExit`과 같은 자리에
    두어 **일반 포획망을 통과**시킨다.

    대가: `except Exception`으로 프로브를 감싸는 관례가 있다면 그 관례가
    깨진다. devloop 프로브는 일회용이고 감싸지 않으므로 그 대가를 받는다.
    """


def need(obj: object, name: str, *, what: str = "") -> object:
    """`obj.name`을 돌려주거나 죽는다. 기본값 인자를 **갖지 않는다**."""
    try:
        return getattr(obj, name)
    except AttributeError:
        avail = ", ".join(sorted(a for a in dir(obj) if not a.startswith("_"))[:12])
        raise ProbeFailure(
            f"프로브 전제 실패: {what or type(obj).__name__}에 '{name}'이 없다. "
            f"폴백 대신 죽는다 (c157 별건 3). 가용 후보: {avail}"
        ) from None


def need_all(obj: object, *names: str, what: str = "") -> tuple:
    """여러 속성을 한 번에. 하나라도 없으면 죽는다."""
    return tuple(need(obj, n, what=what) for n in names)


def need_import(module: str, *, what: str = ""):
    """import하거나 죽는다. `except ImportError` 폴백을 갖지 않는다."""
    try:
        __import__(module)
    except Exception as exc:
        raise ProbeFailure(
            f"프로브 전제 실패: '{module}' import 불가 ({type(exc).__name__}: {exc})."
            f"{' — ' + what if what else ''}"
        ) from None
    return sys.modules[module]


def need_nonempty(value, label: str):
    """0/빈 결과가 **거짓일 수 있는** 자리에서만 쓴다.

    0은 정당한 값일 수 있다 — 그래서 기본이 아니라 **선택**이다. 다만
    "검출기 hit = 0건"처럼 0이 곧 결론이 되는 자리에서는 0의 출처가
    성공인지 폴백인지 구분돼야 한다.
    """
    try:
        n = len(value)
    except TypeError:
        n = 1 if value else 0
    if not n:
        raise ProbeFailure(
            f"프로브 전제 실패: '{label}'이 비었다. 0을 결론으로 쓰기 전에 "
            f"출처가 성공인지 폴백인지 확인할 것 (c157 별건 3)."
        )
    return value


# --- 인구조사 (다음 사이클 팔) ---------------------------------------------

#: 탐지 패턴은 **4종뿐**이다. 조용한 실패의 형태는 더 많다(빈 파일 읽기, 0행
#: glob, 잘못된 경로의 빈 결과…). 이 스캐너의 침묵은 *"이 4종이 없다"*는 뜻이지
#: *"조용한 거짓이 없다"*가 아니다 — P45 한계 ③.
PATTERNS = ("hasattr-삼항", "getattr-기본값", "except-pass", "except-빈리터럴")

_EMPTY_LITERAL = (ast.List, ast.Dict, ast.Set, ast.Tuple)


def _is_empty_literal(node: ast.AST) -> bool:
    if isinstance(node, _EMPTY_LITERAL):
        return not getattr(node, "elts", getattr(node, "keys", []))
    if isinstance(node, ast.Constant):
        return node.value in (0, None, "", False)
    return False


def _violations_in_tree(tree: ast.AST, src_lines: list[str]) -> list[dict]:
    out: list[dict] = []

    def snip(node: ast.AST) -> str:
        i = getattr(node, "lineno", 0) - 1
        return src_lines[i].strip()[:96] if 0 <= i < len(src_lines) else ""

    for node in ast.walk(tree):
        # ① `X if hasattr(o, "n") else []` — c157의 정확한 형태
        if isinstance(node, ast.IfExp):
            test = node.test
            if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) \
                    and test.func.id == "hasattr":
                out.append({"kind": "hasattr-삼항", "line": node.lineno, "src": snip(node)})
        # ② `getattr(o, "n", 기본값)` — 3인자 형태가 곧 폴백이다
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "getattr" and len(node.args) == 3:
            out.append({"kind": "getattr-기본값", "line": node.lineno, "src": snip(node)})
        # ③④ `except ...:` 아래가 pass이거나 빈 리터럴 대입/반환
        elif isinstance(node, ast.ExceptHandler):
            body = node.body
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                out.append({"kind": "except-pass", "line": node.lineno, "src": snip(node)})
            elif all(
                (isinstance(s, ast.Assign) and _is_empty_literal(s.value))
                or (isinstance(s, ast.Return) and s.value is not None
                    and _is_empty_literal(s.value))
                for s in body
            ) and body:
                out.append({"kind": "except-빈리터럴", "line": node.lineno, "src": snip(node)})
    return sorted(out, key=lambda d: d["line"])


def scan_source(src: str) -> list[dict]:
    """소스 문자열 1본의 위반 목록. 파싱 실패는 **예외로 올린다** (0을 반환하지 않는다)."""
    tree = ast.parse(src)
    return _violations_in_tree(tree, src.splitlines())


def scan_probes(paths: list[str]) -> dict:
    """프로브 파일들을 훑는다.

    반환의 `unparsed`가 핵심이다 — 파싱 실패를 '위반 0'에 섞으면 이 계기가
    바로 그 병(조용한 0)에 걸린다. 호출자는 **반드시** unparsed를 함께 인쇄할 것.
    """
    scanned, violations, unparsed, guarded = [], [], [], []
    for path in sorted(paths):
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except OSError as exc:
            unparsed.append({"path": path, "why": f"{type(exc).__name__}: {exc}"})
            continue
        if "probe_guard" in src:
            guarded.append(path)
        try:
            hits = scan_source(src)
        except SyntaxError as exc:
            unparsed.append({"path": path, "why": f"SyntaxError line {exc.lineno}"})
            continue
        scanned.append(path)
        for h in hits:
            violations.append({"path": path, **h})
    return {
        "scanned": scanned,
        "violations": violations,
        "unparsed": unparsed,
        "guarded": guarded,
        "patterns": list(PATTERNS),
    }


def probe_paths(repo: str, pattern: str = "tmp/*.py") -> list[str]:
    return glob.glob(os.path.join(repo, pattern))


def cycle_of(path: str) -> int | None:
    """`tmp/c157_foo.py` → 157. 관례 밖 이름은 None (그 사실을 인쇄로 드러낸다)."""
    base = os.path.basename(path)
    if not base.startswith("c"):
        return None
    head = base[1:].split("_", 1)[0]
    return int(head) if head.isdigit() else None


# --- 자기 검증 -------------------------------------------------------------

_BAD = '''
def f(NC, items):
    hits = NC.scan(items) if hasattr(NC, "scan") else []
    n = getattr(NC, "count", 0)
    try:
        x = g()
    except Exception:
        pass
    try:
        y = h()
    except Exception:
        y = []
    return hits, n, y
'''

_GOOD = '''
from probe_guard import need
def f(NC, items):
    return need(NC, "scan")(items)
'''


def _selftest() -> int:
    fails = []

    kinds = sorted(h["kind"] for h in scan_source(_BAD))
    if kinds != sorted(PATTERNS):
        fails.append(f"4패턴 탐지 실패: {kinds}")

    if scan_source(_GOOD):
        fails.append("클린 표본에서 오탐")

    class _Empty:
        pass

    try:
        need(_Empty(), "scan")
        fails.append("need()가 없는 속성에 죽지 않았다")
    except ProbeFailure:
        pass

    try:
        need_nonempty([], "검출기 hit")
        fails.append("need_nonempty()가 빈 값에 죽지 않았다")
    except ProbeFailure:
        pass

    # ProbeFailure는 `except Exception`을 **통과**해야 한다 (설계 근거의 검증)
    leaked = True
    try:
        try:
            need(_Empty(), "scan")
        except Exception:  # noqa: BLE001 — 의도적 함정
            leaked = False
    except ProbeFailure:
        pass
    if not leaked:
        fails.append("ProbeFailure가 `except Exception`에 잡혔다 — BaseException 상속이 깨졌다")

    try:
        scan_source("def f(:")
        fails.append("파싱 실패가 예외로 오르지 않았다")
    except SyntaxError:
        pass

    for f in fails:
        print(f"  !! {f}")
    print(f"probe_guard selftest: {'FAIL' if fails else 'PASS'} ({len(fails)} 실패)")
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    rep = scan_probes(probe_paths(repo))
    print(f"scanned={len(rep['scanned'])} violations={len(rep['violations'])} "
          f"unparsed={len(rep['unparsed'])} guarded={len(rep['guarded'])}")
    for v in rep["violations"]:
        print(f"  {os.path.relpath(v['path'], repo)}:{v['line']}  {v['kind']}  {v['src']}")
    for u in rep["unparsed"]:
        print(f"  !! 미검사 {os.path.relpath(u['path'], repo)}  {u['why']}")
