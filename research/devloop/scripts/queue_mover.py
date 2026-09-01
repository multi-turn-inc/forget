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

㉨ (c284 집행 — «깨진 devloop 소유 계기의 자기 수리» 열째 선례): 이동기는 자기 산출물의
영수증 거처(«- **cN 정산**:» 불릿)를 검산하지 않았다 — c276~c280 다섯 프레임의 정산 줄이
무공지로 소멸해도(관측 130) 드리프트 0만 인쇄했다. 처치 = 재계산 패스 말미에
**직전 프레임 정산 줄 존재 1비트**를 읽기 전용으로 산출한다(`settlement_receipt`) —
부재면 시끄럽게, 침묵 금지. 불릿은 **읽기만** 한다(무접촉 규율 불변).
"""
import re

AGE_RE = re.compile(r"(\d+)(사이클째)")
# 산식 칸 직독 — 마이너스는 U+2212(정본 표기)와 ASCII 하이픈 둘 다 허용
FORMULA_RE = re.compile(r"`\s*N\s*[−-]\s*(\d+)\s*\+\s*1\s*`")
QUEUE_HDR = "## 큐 (프레임"
PERM_HDR = "## 상설 파생 계수기"
FRAME_CELL_RE = re.compile(r"프레임 N=(\d+) 값")
# 정산 불릿 두 서식: «- **cN 정산**:» (단일·범위 cA~cB) / «- **cA~cB 정산 줄 공백**» (공백 기재)
SETTLE_RE = re.compile(r"^- \*\*c(\d+)(?:~c(\d+))? 정산(?P<gap> 줄 공백)?")


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


def settlement_receipt(lines, prev_n):
    """㉨ — 직전 프레임 cN 정산 줄 **존재 1비트** (읽기 전용·불릿 무접촉).

    정의역 = 파일 전체의 «- **cN 정산**» 불릿 계열(단일 cN · 범위 cA~cB · «줄 공백» 기재).
    범위 불릿은 그 구간 전 프레임을 덮는다. «줄 공백» 기재는 정산 줄이 아니라 **공백의
    기록**이므로 present=False이되 kind='gap'으로 갈라 적는다 — 기재된 공백과 침묵 소멸을
    한 값으로 접지 않는다(관측 130의 병은 후자다).

    반환: {prev_frame, present(bool: 정산 줄 자체가 있다), kind('settle'|'gap'|None),
           line(1-based|None), series_min, series_max, recorded_gaps[프레임],
           silent_missing[프레임 — series_min..prev_n 중 어느 불릿도 안 덮는 것],
           duplicates[프레임 — 불릿 2개 이상]}
    """
    covered = {}
    for i, l in enumerate(lines):
        m = SETTLE_RE.match(l)
        if not m:
            continue
        a = int(m.group(1))
        b = int(m.group(2) or a)
        kind = "gap" if m.group("gap") else "settle"
        for f in range(a, b + 1):
            covered.setdefault(f, []).append((kind, i + 1))
    r = {"prev_frame": prev_n, "present": False, "kind": None, "line": None,
         "series_min": None, "series_max": None, "recorded_gaps": [],
         "silent_missing": [], "duplicates": []}
    if not covered:
        r["silent_missing"] = [prev_n]
        return r
    r["series_min"], r["series_max"] = min(covered), max(covered)
    hit = covered.get(prev_n)
    if hit:
        kinds = [k for k, _ in hit]
        if "settle" in kinds:
            r["present"], r["kind"] = True, "settle"
            r["line"] = next(ln for k, ln in hit if k == "settle")
        else:
            r["kind"], r["line"] = "gap", hit[0][1]
    r["recorded_gaps"] = sorted(f for f, v in covered.items()
                                if all(k == "gap" for k, _ in v))
    r["silent_missing"] = [f for f in range(r["series_min"], prev_n + 1)
                           if f not in covered]
    r["duplicates"] = sorted(f for f, v in covered.items() if len(v) > 1)
    return r


def format_settlement_receipt(r):
    """인쇄 서식 — 부재는 «!!»로 시끄럽게. 문자열 리스트 반환(호출자가 print)."""
    n = r["prev_frame"]
    out = []
    if r["present"]:
        out.append(f"[㉨] 직전 프레임 c{n} 정산 줄 = 존재 (L{r['line']}) · 1비트 = 1")
    elif r["kind"] == "gap":
        out.append(f"[㉨] !! 직전 프레임 c{n} 정산 줄 = 부재 — 단 «줄 공백» 기재 있음 (L{r['line']}) · 1비트 = 0(기재된 공백)")
    else:
        out.append(f"[㉨] !! 직전 프레임 c{n} 정산 줄 = **부재·무기재** — 관측 130 재발 표본 · 1비트 = 0 · 원장에 적을 것(침묵 금지)")
    if r["series_min"] is not None:
        out.append(f"     불릿 계열 c{r['series_min']}~c{r['series_max']} · 기재된 공백 {len(r['recorded_gaps'])}프레임"
                   + (f" {_ranges(r['recorded_gaps'])}" if r["recorded_gaps"] else ""))
    if r["silent_missing"]:
        out.append(f"     !! 침묵 소멸(어느 불릿도 안 덮음) {len(r['silent_missing'])}프레임: {_ranges(r['silent_missing'])}")
    if r["duplicates"]:
        out.append(f"     [주의] 불릿 2개 이상인 프레임: {_ranges(r['duplicates'])}")
    return out


def _ranges(frames):
    """[206,207,208,210] → 'c206~c208·c210' — 인쇄 축약 전용."""
    if not frames:
        return ""
    runs, start, prev = [], frames[0], frames[0]
    for f in frames[1:]:
        if f != prev + 1:
            runs.append((start, prev))
            start = f
        prev = f
    runs.append((start, prev))
    return "·".join(f"c{a}" if a == b else f"c{a}~c{b}" for a, b in runs)


def move_frame(text, old_n, new_n):
    """두 패스 일괄 실행 + ㉨ 영수증. 반환 (new_text, queue_report, perm_report).

    perm_report['settlement_prev'] = settlement_receipt(직전 프레임 = old_n) — 이동 직전
    프레임의 정산 줄은 그 사이클 수확이 썼어야 하므로, 이동 시점이 그 1비트의 검산 시점이다.
    """
    lines = text.splitlines()
    q = shift_queue_frame(lines, old_n, new_n)
    p = recalc_permanent_table(lines, new_n)
    p["settlement_prev"] = settlement_receipt(lines, old_n)
    return "\n".join(lines) + "\n", q, p
