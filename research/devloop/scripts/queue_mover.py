"""게이트 큐 이동기 — 상설 모듈 (계기 큐 ㉷ 집행, c266 건설).

c170~c265 96세대 동안 tmp/cN_queue_ages.py가 같은 로직을 상수만 바꿔 복제해 왔고,
그 정의역은 「## 큐」 블록뿐이라 「## 상설 파생 계수기」 표는 손 의무로만 갱신됐다 —
손-누락 실측 3회(c203~204 · c206~210 · c246). ㉷의 처치 = 이동기가 상설 표도
**재계산**하도록 편입. 이 모듈이 그 정본이며, 사이클별 tmp 이동기는 얇은 호출자가 된다.

두 패스의 산술이 다르다 — 섞지 말 것:
  · 큐 블록  = **증분**(마지막 적중 칸 +1 · 취소선 동결 스킵[㉵ⓑ] · 다중/영 적중 무접촉)
  · 상설 표  = **재계산**(산식 `N − anchor + 1` 직독 — 증분이 아니므로 몇 프레임을
    누락했어도 한 번에 정위로 돌아온다. 이것이 손-누락 근절의 전부다.)

규율 승계: `### 정산 (cNNN)` 이하 산문은 과거 프레임의 기록이라 건드리지 않는다.
상설 절의 불릿(정산 이력)도 마찬가지 — 이 모듈은 **표 행만** 만진다.
회귀 = tests/test_devloop_queue_mover.py.
"""
import re

AGE_RE = re.compile(r"(\d+)(사이클째)")
# 산식 칸 직독 — 마이너스는 U+2212(정본 표기)와 ASCII 하이픈 둘 다 허용
FORMULA_RE = re.compile(r"`\s*N\s*[−-]\s*(\d+)\s*\+\s*1\s*`")
QUEUE_HDR = "## 큐 (프레임"
PERM_HDR = "## 상설 파생 계수기"
FRAME_CELL_RE = re.compile(r"프레임 N=(\d+) 값")


class FrameMismatch(Exception):
    """헤더 프레임이 기대 프레임이 아니다 — 이중 실행·crash-orphan 의심. 판정은 손 몫."""


def shift_queue_frame(lines, old_n, new_n):
    """「## 큐」 블록: 헤더 프레임 교체 + 경과값 증분. lines를 제자리 수정.

    반환 report: {changed: [(1-based line, old, new)], skipped: [(line, cell)],
                  bad: [(line, cell_idx, hits)], header: (old, new)}
    """
    start = next(i for i, l in enumerate(lines) if l.startswith(QUEUE_HDR))
    end = next(i for i, l in enumerate(lines[start + 1:], start + 1)
               if l.startswith("###"))
    hdr = lines[start]
    if f"N={old_n}" not in hdr:
        raise FrameMismatch(f"큐 헤더 프레임이 N={old_n}이 아니다: {hdr}")
    lines[start] = hdr.replace(f"N={old_n}", f"N={new_n}")

    report = {"changed": [], "skipped": [], "bad": [],
              "header": (hdr, lines[start]), "span": (start, end)}
    for i in range(start + 1, end):
        line = lines[i]
        if not line.lstrip().startswith("|"):
            continue
        cells = line.split("|")
        idx = [j for j, c in enumerate(cells) if AGE_RE.search(c)]
        if not idx:
            continue
        target = idx[-1]
        if "~~" in cells[target]:
            report["skipped"].append((i + 1, cells[target].strip()[:48]))
            continue
        hits = AGE_RE.findall(cells[target])
        if len(hits) != 1:
            report["bad"].append((i + 1, target, hits))
            continue
        old = int(hits[0][0])
        cells[target] = AGE_RE.sub(lambda m: f"{old + 1}{m.group(2)}",
                                   cells[target], count=1)
        lines[i] = "|".join(cells)
        report["changed"].append((i + 1, old, old + 1))
    return report


def recalc_permanent_table(lines, new_n):
    """「## 상설 파생 계수기」 표: 헤더 프레임 + 값 칸을 산식으로 **재계산**.

    증분이 아니다 — 직전 값이 몇 프레임 뒤처져 있어도(드리프트) 산식이 정위를 준다.
    드리프트는 고치되 침묵시키지 않는다: report의 drift에 (line, 발견값, 기대_직전값)로
    남긴다. 표 아래 불릿·`### 정산` 산문은 무접촉.

    반환 report: {header: (old_frame, new_n) | None, rows: [(line, anchor, old, new)],
                  drift: [(line, found, expected_prev)], no_formula: [line]}
    """
    start = next(i for i, l in enumerate(lines) if l.startswith(PERM_HDR))
    report = {"header": None, "rows": [], "drift": [], "no_formula": []}
    in_table = False
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.startswith("#"):
            break
        if not line.lstrip().startswith("|"):
            if in_table:
                break  # 표 종료 — 아래 불릿 산문은 정의역 밖
            continue
        cells = line.split("|")
        hdr_hit = [(j, m) for j, c in enumerate(cells)
                   if (m := FRAME_CELL_RE.search(c))]
        if hdr_hit:
            in_table = True
            j, m = hdr_hit[-1]
            old_frame = int(m.group(1))
            cells[j] = FRAME_CELL_RE.sub(f"프레임 N={new_n} 값", cells[j], count=1)
            lines[i] = "|".join(cells)
            report["header"] = (old_frame, new_n)
            continue
        if not in_table or set(line.replace("|", "").strip()) <= {"-", ":", " "}:
            continue
        fm = FORMULA_RE.search(line)
        if not fm:
            report["no_formula"].append(i + 1)
            continue
        anchor = int(fm.group(1))
        new_val = new_n - anchor + 1
        idx = [j for j, c in enumerate(cells) if AGE_RE.search(c)]
        if not idx:
            report["no_formula"].append(i + 1)
            continue
        target = idx[-1]
        old_val = int(AGE_RE.search(cells[target]).group(1))
        expected_prev = new_val - 1
        if old_val != expected_prev:
            report["drift"].append((i + 1, old_val, expected_prev))
        cells[target] = AGE_RE.sub(lambda m: f"{new_val}{m.group(2)}",
                                   cells[target], count=1)
        lines[i] = "|".join(cells)
        report["rows"].append((i + 1, anchor, old_val, new_val))
    return report


def move_frame(text, old_n, new_n):
    """두 패스 일괄 실행. 반환 (new_text, queue_report, perm_report)."""
    lines = text.splitlines()
    q = shift_queue_frame(lines, old_n, new_n)
    p = recalc_permanent_table(lines, new_n)
    return "\n".join(lines) + "\n", q, p
