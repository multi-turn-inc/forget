#!/usr/bin/env python3
"""사이클 48 계측 — step 0 규약을 문장이 아니라 **실행 가능한 검사**로 (읽기 전용).

두 가지를 잰다.

  (A) 규약 (ii) "HEAD보다 새로운 미커밋 파일" 검사의 **구현 의존성**
      이 체크아웃은 git worktree라 `.git`이 디렉터리가 아니라 포인터 **파일**이다.
      따라서 `find . -newer .git/HEAD`는 참조 파일이 없어 조용히 실패하고 0건을 낸다 —
      즉 항상 "깨끗함"이라고 답하는 거짓 음성 기계다. 워크트리 안전형과 나란히 낸다.

  (B) 규약 도달 계측의 **니들 판본 대조**
      c47이 (iii)의 니들에 "tail 금지"를 추가한 뒤 3/3을 보고했다. 대조군(c46·c47 초측
      1/3)은 확장 전 니들로 쟀으므로, 같은 캡슐을 두 판본으로 재서 확장분을 분리한다.

      **c64 확장 (P19, 가산적 — 기존 자를 치우지 않는다).** V1·V2의 니들은 규약의
      *내용*이 아니라 c47이 목격한 *어휘*를 고정했고, 루프가 같은 지시를 다른 말로 옮겨
      적을 때마다 계측이 조용히 0으로 내려앉았다(거짓 음성 6종째, c62 발견·c64 재확인:
      캡슐이 "번호·모드는 … c48_step0_check.py 첫 줄"을 실제로 날라 그 손이 준수했는데
      capsule_reach=1/3). 방향이 위험한 쪽이다 — **해결된 것을 미해결로 보고**한다.
      그래서 셋을 더한다: V3 의미 니들(표현의 논리합) · **캡슐 원문 인쇄** · sha256.
      V1·V2는 문면 그대로 둔다 — c46~c64 시계열의 비교 가능성이 그 자에 걸려 있다.
      한계(정직): V3도 리터럴의 논리합이라 표류를 늦출 뿐 없애지 못한다. 드리프트에
      대한 실제 방어는 원문 인쇄이고 V3는 시계열 숫자를 잇기 위한 보조다.

규약: 결론 문장을 상수로 인쇄하지 않는다. 숫자와 원문만 낸다.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
INSTALLED_HOOKS = os.path.expanduser("~/.forget/hooks")
FORGET_URL = "http://localhost:8000/mcp/forget/http/junghunkim"
FINGERPRINT_BASELINE = os.path.join(REPO, "research", "devloop", "body-fingerprint.json")
FORGET_DB = os.path.expanduser("~/.forget/forget.sqlite3")
UNKNOWN = "미확인"


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout.strip()


def run_raw(cmd: list[str]) -> str:
    """strip() 없이 stdout 그대로.

    c64 발견: `git status --porcelain`의 행 형식은 `XY<space><path>`이고 미스테이지
    변경의 X는 **공백**이다(` M path`). `run()`의 `.strip()`은 그 선행 공백을
    **첫 행에서만** 지워 `line[3:]`이 경로의 첫 글자를 먹고, 존재하지 않는 경로가 되어
    조용히 `continue`된다 — 즉 **변경 파일 목록의 첫 항목이 언제나 보이지 않았다**.
    변경 파일이 정확히 1개면 검사는 `0`을 답한다: 절차 2가 막으려는 바로 그 상황
    (타 세션 WIP 1건이 있는데 "깨끗함"으로 읽고 코드 사이클 진입)에서 침묵한다.
    part_a가 폭로하려던 `.git/HEAD` 거짓 음성 기계와 같은 종류의 결함을 part_a 자신이
    갖고 있었다. 형식이 열(column)로 정의된 출력은 strip하지 않는다.
    """
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout


def call(name: str, arguments: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(FORGET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(req, timeout=20).read())
    return json.loads(body["result"]["content"][0]["text"])


def cycle_number_and_mode(cycles: list[int]) -> tuple[int, str]:
    """cycle 필드 max+1과 모드. **순수 함수** — part_n의 산술을 테스트 가능하게 분리 (c71).

    part_n/part_a/part_b 파싱 테스트 미커버가 c64→c70 7회 재이월된 부채의 부분 상환:
    번호·모드 산술이 처음으로 회귀 감시 아래 들어간다. 출력 문면은 불변이다.
    """
    n = max(cycles) + 1
    mode = "적대 감사" if n % 10 == 0 else ("회고" if n % 5 == 0 else "일반")
    return n, mode


def part_n() -> None:
    """c52 재배선(F-절차0 처치): 사이클 번호 N을 이 스크립트가 인쇄한다.

    근본 원인(c52 발견): 지시서 절차 0의 문면("metrics.jsonl 마지막 줄에서 N = 마지막+1")이
    tail류 접근을 사실상 지시하고, 'cycle 필드만·tail 금지' 규약은 그림자 채널에만 있어
    문면과 충돌한다 — '알고도' 위반 4연속(c49~c52)의 기전. 금지문 대신 물리 경로를 바꾼다:
    이미 의무인 영토 검사가 번호를 함께 배달하면 metrics.jsonl을 열 동기 자체가 사라진다.
    번호는 cycle 필드의 max+1 — 마지막 줄이 아니라 전체 파싱(순서 오염에도 안전).

    c61 추가 배선(F-절차0 10회차 처치, 무-게이트): 금지문 자체를 이 출력에 싣는다.
    c61 실측 — 캡슐 병행 트랙 슬롯이 90자에서 끊겨 도착분 마지막 토큰이 `metrics`,
    금지 술어 `열지 마라`의 시작 인덱스는 91(컷 밖 1문자)이었다. 캡슐은 목적어를
    배달하고 술어를 버렸고, 도착분만 읽으면 위반이 지시로 오독된다. 산문 채널(캡슐·
    지시서)이 절단·충돌로 실패하므로 P14 교훈("규약은 도구 채널로 보내라")을 적용:
    번호를 얻으려 이 스크립트를 실행하는 손은 금지문을 절단 불가능한 형태로 함께 받는다.
    한계(정직): 이 처치는 **절단 축**만 다룬다. 지시서 절차 0 문면("마지막 줄에서 N")은
    A-55.1 게이트 대기 중이라 살아 있고, step0을 병렬 배선하면 규약 도착과 위반이 같은
    턴에 고정되는 축도 남는다 — c62~c66 재발 시 남은 원인은 문면 단독으로 확정한다.
    """
    cycles = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cycles.append(int(json.loads(line)["cycle"]))
    n, mode = cycle_number_and_mode(cycles)
    print("[!] metrics.jsonl을 직접 열지 말 것 — 번호·모드는 아래 한 줄이 정본이다.")
    print("    (tail/cat/head 계열 0회. 이 스크립트가 이미 전체를 파싱했다.")
    print("     지시서 절차 0의 '마지막 줄에서 N' 문면은 A-55.1 게이트 대기 중인 구본이며,")
    print("     감사 사이클의 metrics 정독 임무는 번호 결정 단계와 별개로 허용된다.)")
    print(f"[N. 사이클 번호 — cycle 필드 max+1]")
    print(f"  last_cycle={max(cycles)}  N={n}  mode={mode} (N%10={n % 10}, N%5={n % 5})")


def compare_fingerprint(live: dict[str, str], baseline: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """live와 baseline을 대조한다. **순수 함수** — I/O 없음, 그래서 테스트된다.

    설계의 핵심 성질 하나: **채취하지 못한 항목을 '일치'로 보고하지 않는다.**
    관측 30의 병리가 조용한 흡수였으므로, 미채취(`UNKNOWN`)는 '일치'가 아니라
    **판정 불가**로 격리한다. baseline에 없는 신규 키도 미채취와 같게 다룬다 —
    지문 정의를 넓히는 것은 자[尺] 변경이고, 그 변경은 baseline 커밋으로만 승인된다.

    반환: (verdict, changed, unknown)
      changed 있으면 "재교정 필요" (몸이 바뀌었다)
      changed 없고 unknown 있으면 "판정 불가" (모른다 — 위양성으로 계상하지 않는다)
      둘 다 없으면 "일치"
    """
    changed: list[str] = []
    unknown: list[str] = []
    for key in sorted(set(live) | set(baseline)):
        got, want = live.get(key, UNKNOWN), baseline.get(key, UNKNOWN)
        if got == UNKNOWN or want == UNKNOWN:
            unknown.append(key)
        elif got != want:
            changed.append(key)
    verdict = "재교정 필요" if changed else ("판정 불가" if unknown else "일치")
    return verdict, changed, unknown


def _installed_dist_info() -> str:
    di = glob.glob(os.path.expanduser(
        "~/.forget/venv/lib/python3*/site-packages/forget_ai-*.dist-info"))
    return os.path.basename(di[0]).replace(".dist-info", "") if di else UNKNOWN


def _installed_vs_repo() -> str:
    """설치본과 저장소본의 최상위 .py 해시 대조 (c66_body_identity.py에서 이식)."""
    inst = glob.glob(os.path.expanduser("~/.forget/venv/lib/python3*/site-packages/forget"))
    repo_pkg = os.path.join(REPO, "forget")
    if not inst or not os.path.isdir(repo_pkg):
        return UNKNOWN

    def digest(path: str) -> str:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    rfiles = {f for f in os.listdir(repo_pkg) if f.endswith(".py")}
    ifiles = {f for f in os.listdir(inst[0]) if f.endswith(".py")}
    both = rfiles & ifiles
    same = sum(1 for f in both
               if digest(os.path.join(repo_pkg, f)) == digest(os.path.join(inst[0], f)))
    # 분모는 합집합이다 — 교집합을 분모로 쓰면 한쪽에만 있는 파일이 사라진다 (c64 규율).
    return f"{same}/{len(rfiles | ifiles)}"


def _store_vec() -> str:
    """스토어 임베딩의 형식·우세 차원. 디코드 없이 byte length만 집계한다.

    행 수는 싣지 않는다 — 매 사이클 증가하므로 위양성 기계가 된다 (P21 (b)).
    dim = (len - 4) // 4  (MEB1 = 4바이트 매직 + little-endian float32).
    """
    if not os.path.exists(FORGET_DB):
        return UNKNOWN
    try:
        con = sqlite3.connect(f"file:{FORGET_DB}?mode=ro", uri=True)
        try:
            # 매직 비교는 **hex 리터럴**이어야 한다: embedding은 BLOB이고 SQLite에서
            # BLOB은 TEXT 리터럴('MEB1')과 절대 같지 않다(저장 클래스가 다르면 불일치).
            # 첫 배선에서 이 비교가 항상 거짓이라 1540바이트 MEB1 행을 JSON으로 보고했고,
            # baseline 대조가 같은 사이클 안에서 그것을 잡았다 — 계측기가 자기 결함을
            # 자기 첫 런에서 검출한 표본이다. x'4D454231' = b"MEB1".
            rows = con.execute(
                "select substr(embedding,1,4)=x'4D454231', length(embedding), count(*) "
                "from memories where deleted=0 and embedding is not null and embedding != '' "
                "group by 1, 2 order by count(*) desc limit 1").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return UNKNOWN
    if not rows:
        return UNKNOWN
    is_meb1, blen, _ = rows[0]
    return f"MEB1:{(int(blen) - 4) // 4}" if is_meb1 else f"JSON:len{int(blen)}"


def _effective_stack() -> tuple[str, str, str]:
    """살아 있는 몸에게 직접 묻는다 — 디스크가 아니라 **적재된 런타임**의 자기 보고.

    두 필드를 함께 낸다. `checks.embeddings`는 **저장된 설정**의 거울이라
    폴백 이름(deterministic-128)을 들고 있고, `effective`가 실제 실행 스택이다
    (provider_runtime.py:779-784). 불일치 자체가 지문의 일부다.
    """
    try:
        health = call("get_provider_health", {})
    except Exception:  # noqa: BLE001 — 서버 정지도 데이터다. 조용히 '일치'가 되지만 않으면 된다.
        return UNKNOWN, UNKNOWN, UNKNOWN
    eff = health.get("effective") or {}
    chk = (health.get("checks") or {}).get("embeddings") or {}
    effective = (f"{eff.get('embedding_provider')}:{eff.get('embedding_model')}"
                 if eff.get("embedding_model") else UNKNOWN)
    checks = (f"{chk.get('provider')}:{chk.get('model')}" if chk.get("model") else UNKNOWN)
    return effective, str(eff.get("resolution") or UNKNOWN), checks


def part_body() -> None:
    """P21 처치 (c67 배선) — 몸 지문을 step 0의 첫 화면에 세운다.

    계기: 관측 30 / notes/cycle-66. c59 oracle replay가 무수정 재실행에서 재현되지
    않았고 원인은 어휘가 아니라 **12시간 전에 교체된 몸**이었다. 루프는 c61~c65
    다섯 사이클을 새 몸에서 돌면서 그 사실을 원장에 적지 못했다(검출 지연 5사이클).
    step 0 스크립트를 고른 이유: F-절차0 처치가 만든 **절단 불가능 채널**이고,
    관측 29가 실측한 대로 그 채널에 없는 규약은 산다는 보장이 없다.

    등록본 이탈 1건(선언): ②'프로세스 기동 시각'을 빼고 **effective 스택 + resolution**을
    넣었다 — lsof/ps가 샌드박스 승인에 의존해 승인 없는 런에서 지문이 조용히 미지로
    내려앉기 때문이다. 근거와 대안은 body-fingerprint.json의 `_omitted_process_start`.

    출력은 **3줄 고정** (P21 정직 병기 ②: 늘어나면 F-절차0 재발로 계상한다).
    """
    effective, resolution, checks = _effective_stack()
    live = {"dist_info": _installed_dist_info(),
            "installed_vs_repo": _installed_vs_repo(),
            "effective_embedding": effective,
            "embedding_resolution": resolution,
            "checks_embedding": checks,
            "store_vec": _store_vec()}
    try:
        with open(FINGERPRINT_BASELINE, encoding="utf-8") as fh:
            baseline = json.load(fh).get("fingerprint", {})
    except (OSError, json.JSONDecodeError):
        baseline = {}
    verdict, changed, unknown = compare_fingerprint(live, baseline)

    mark = "**재교정 필요**" if changed else verdict
    print(f"[Body. 몸 지문 — 게이트 상수 의존 계기의 유효 전제 (P21, baseline=body-fingerprint.json)]")
    print(f"  {live['dist_info']} inst_vs_repo={live['installed_vs_repo']} "
          f"eff={live['effective_embedding']} res={resolution.split(' (')[0]} "
          f"checks={live['checks_embedding']} store={live['store_vec']}")
    print(f"  대조: {mark}"
          + (f" — 변경 {changed}" if changed else "")
          + (f" / 미채취 {unknown}" if unknown else "")
          + ("  → oracle replay 계열·gate_audit·score_weight_* 를 재교정 전 판정 금지"
             if changed else ""))


def recall_components(note: str) -> dict[str, int] | None:
    """recall_note에서 성분 4값(능동 hit/miss · 주입 hit/miss)을 추출한다. **순수 함수**.

    정본 형식(P15 (b)): `능동 X회(hit a·miss b) / 주입 Y건(hit c·miss d)`.
    관측된 의역(c70: "능동 검색 0회", "주입 4건 = … hit 1 + … 3건 miss")도 받되,
    값이 **유일하게** 정해지지 않으면 None을 반환한다 — '추출 불가'는 P24 (b)의
    계상 대상이지 조용히 0으로 접을 값이 아니다(compare_fingerprint와 같은 규율:
    모르는 것을 '일치'로 보고하지 않는다).
    """
    text = note.replace("*", "")
    inj = re.search(r"주입\s*(\d+)\s*건", text)
    act = re.search(r"능동[^0-9]{0,12}?(\d+)\s*회", text)
    if not inj or not act:
        return None

    def hitmiss(seg: str) -> tuple[int | None, int | None]:
        h = re.search(r"hit\s*(\d+)", seg)
        m = re.search(r"miss\s*(\d+)", seg) or re.search(r"(\d+)\s*건[^0-9]{0,8}?miss", seg)
        return (int(h.group(1)) if h else None), (int(m.group(1)) if m else None)

    act_seg, inj_seg = text[:inj.start()], text[inj.start():]
    a_cnt, i_cnt = int(act.group(1)), int(inj.group(1))
    a_hit, a_miss = hitmiss(act_seg)
    if a_hit is None and a_miss is None and a_cnt == 0:
        a_hit = a_miss = 0  # "능동 0회"는 분해 생략이 유일 해석이다
    if a_hit is None or a_miss is None:
        return None
    i_hit, i_miss = hitmiss(inj_seg)
    # 한쪽만 명시돼도 총계로 닫히면 유일 결정이다 (예: "주입 4건 = hit 1 + 3건 miss")
    if i_hit is None and i_miss is not None and i_miss <= i_cnt:
        i_hit = i_cnt - i_miss
    elif i_miss is None and i_hit is not None and i_hit <= i_cnt:
        i_miss = i_cnt - i_hit
    if i_hit is None or i_miss is None:
        return None
    return {"active_hits": a_hit, "active_misses": a_miss, "active_total": a_cnt,
            "injected_hits": i_hit, "injected_misses": i_miss, "injected_total": i_cnt}


def recall_identity(row: dict) -> tuple[str, str]:
    """원장 행의 recall 필드가 성분 합과 일치하는지 검산한다. **순수 함수** (P24 처치 ②).

    반환 (verdict, detail). verdict ∈ {일치, 불일치, 추출 불가}.
    audit-70 §1-a가 적발한 c64형 결함(필드=구정의·산문=신정의, 무선언 분열)을
    다음 사이클의 step 0이 기계로 잡는다. 결론 문장은 만들지 않는다 — 값과 판정만.
    """
    comp = recall_components(str(row.get("recall_note", "")))
    if comp is None:
        return "추출 불가", "성분 4값 유일 추출 실패 — P24 (b) 계상 대상"
    want = (comp["active_hits"] + comp["injected_hits"],
            comp["active_misses"] + comp["injected_misses"])
    got = (int(row.get("recall_hits", -1)), int(row.get("recall_misses", -1)))
    detail = (f"fields(hits={got[0]}·misses={got[1]}) vs "
              f"성분(능동 {comp['active_hits']}·{comp['active_misses']} / "
              f"주입 {comp['injected_hits']}·{comp['injected_misses']})")
    return ("일치" if got == want else "불일치"), detail


def part_recall() -> None:
    """P15 (a) 반증 처방의 배선 (c71, P24) — 정의 A를 절단 불가능 채널로 인쇄하고
    직전 원장 행의 `성분 합 = 필드 값` 항등식을 검산한다.
    """
    rows = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    last = max(rows, key=lambda r: r["cycle"])
    verdict, detail = recall_identity(last)
    print("\n[R. recall 계상 — 정의 A 정본 출력 (P15 (a) 반증 → P24 배선, c71)]")
    print("  계상 대상 = 이 사이클에 표면화된 회상 전체: 능동 검색 + 주입(캡슐·task_state·훅).")
    print("  계기의 검색 호출은 계상 제외(c68 선언). hit = 행동을 바꾼 신규 정보이며, 도착")
    print("  시각이 행동을 바꾸면 hit(c64 확장의 성문화 — 노출이지 승인 아님, audit-70 N7).")
    print("  필드 항등식: recall_hits = 능동hit+주입hit · recall_misses = 능동miss+주입miss.")
    print("  recall_note 병기 형식: '능동 X회(hit a·miss b) / 주입 Y건(hit c·miss d)'.")
    print(f"  [직전 행 검산] cycle={last['cycle']}: {detail} → {verdict}")


def porcelain_changed_paths(raw: str) -> list[str]:
    """`git status --porcelain` 원문(무-strip)에서 경로 열을 뽑는다. **순수 함수** (c82).

    part_a 인라인이던 파싱의 분리 — "part_n/part_a/part_b 파싱 미커버" 부채(c64 등재,
    c71 부분 상환, audit-80 §3-(b) 재지적)의 잔여 상환. 동작은 문면 그대로 보존한다:
    행 형식 `XY<space><path>`에서 `line[3:]`, 공백 행 무시, 둘러싼 따옴표 제거.
    입력은 run_raw의 무-strip 원문이어야 한다 — strip된 원문을 주면 첫 행의 X열(공백)이
    사라져 경로 첫 글자를 먹는다(run_raw 독스트링의 c64 결함, 이제 테스트가 방향을 고정).

    알려진 거짓 음성 2종 (c82 관측 — 원칙 2: 고치기 전에 기록, 처치는 후속 사이클 몫):
      ① 스테이지된 리네임 행 `R  old -> new`는 `old -> new` 통짜 문자열이 되어
         하류 os.path.exists에서 조용히 탈락한다.
      ② core.quotepath 기본값에서 비ASCII 경로는 8진 이스케이프(`"\\355…"`)로 와서
         디스크에 없는 경로가 된다 — 한국어 파일명 저장소에서 실질 위험.
    두 경우 모두 "변경 있음"이 "깨끗함" 쪽으로 접히는 방향이다(절차 2가 막으려는 상황).
    현행 동작을 테스트가 그대로 단언한다 — 처치가 오면 그 단언이 울리는 것이 의도다.
    """
    return [line[3:].strip().strip('"') for line in raw.splitlines() if line.strip()]


def part_a() -> None:
    print("[A. 규약 (ii) — 구현 의존성]")
    dotgit = os.path.join(REPO, ".git")
    kind = "dir" if os.path.isdir(dotgit) else ("file(worktree pointer)" if os.path.isfile(dotgit) else "missing")
    print(f"  .git kind={kind}")

    naive_ref = os.path.join(REPO, ".git", "HEAD")
    print(f"  naive_ref_exists={os.path.exists(naive_ref)}  ref={naive_ref}")

    safe_ref = os.path.join(REPO, run(["git", "rev-parse", "--git-path", "HEAD"]))
    print(f"  safe_ref_exists={os.path.exists(safe_ref)}   ref={safe_ref}")

    head_ct = int(run(["git", "log", "-1", "--format=%ct"]))
    print(f"  head_commit_epoch={head_ct}  ({run(['git', 'log', '-1', '--format=%ci'])})")

    # 참조 파일 mtime이 아니라 **커밋 시각**과 비교한다 — .git/HEAD의 mtime은
    # 체크아웃·페치 같은 무관한 조작으로도 갱신되므로 커밋 시각이 더 정확한 기준이다.
    newer: list[tuple[str, int]] = []
    changed = porcelain_changed_paths(run_raw(["git", "status", "--porcelain"]))
    print(f"  changed_paths_total={len(changed)}")  # c64: 분모를 병기해 침묵 절단을 드러낸다
    for rel in changed:
        full = os.path.join(REPO, rel)
        if os.path.isdir(full):
            mt = max((os.path.getmtime(os.path.join(r, f))
                      for r, _, fs in os.walk(full) for f in fs), default=0.0)
        elif os.path.exists(full):
            mt = os.path.getmtime(full)
        else:
            continue
        if int(mt) > head_ct:
            newer.append((rel, int(mt) - head_ct))

    print(f"  uncommitted_paths_newer_than_HEAD={len(newer)}")
    for rel, delta in newer:
        print(f"    +{delta:5d}s  {rel}")


def needle_reach(capsule: str, rules: dict[str, list[str]]) -> tuple[int, dict[str, int]]:
    detail = {k: int(any(nd in capsule for nd in v)) for k, v in rules.items()}
    return sum(detail.values()), detail


def capsule_char_budget(src: str) -> int:
    """훅 소스에서 CAPSULE_CHAR_BUDGET 정수를 뽑는다. **순수 함수** (c82).

    part_b 인라인 정규식의 분리 — 같은 부채의 잔여 상환. 예산은 truncated 판정과
    니들 도달의 분모를 정한다: 이 값을 잘못 읽으면 part_b 전체가 통째로 어긋난다.
    `1_600` 같은 밑줄 리터럴을 허용한다(현행 동작 보존). 마커 부재 시 AttributeError로
    **시끄럽게** 죽는다 — 조용히 기본값으로 접혀 거짓 음성이 되는 것보다 낫고,
    그 성질도 테스트가 고정한다(compare_fingerprint의 규율: 모르는 것을 '일치'로
    보고하지 않는다).
    """
    return int(re.search(r"CAPSULE_CHAR_BUDGET\s*=\s*([0-9_]+)", src).group(1).replace("_", ""))


def part_b() -> None:
    print("\n[B. 규약 도달 — 니들 판본 대조]")
    sys.path.insert(0, INSTALLED_HOOKS)
    from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402

    src = open(os.path.join(INSTALLED_HOOKS, "forget_sessionstart.py"), encoding="utf-8").read()
    budget = capsule_char_budget(src)

    project = None if scope_disabled() else project_key_for_path(REPO)
    args = {"query": f"session startup in {REPO} — active tasks, open loops, recent decisions",
            "include_debug": False}
    pf = layered_filter(project)
    if pf:
        args["filters"] = pf
        args["project"] = project
    capsule = str(call("prepare_context_autopilot", args).get("capsule_text") or "").strip()
    shown = capsule[:budget]
    print(f"  budget={budget} capsule_chars={len(capsule)} truncated={len(capsule) > budget}")

    v1 = {"(i)": ["devloop-self"], "(ii)": ["mtime"], "(iii)": ["cycle` 필드", "cycle 필드"]}
    v2 = {"(i)": ["devloop-self"], "(ii)": ["mtime"], "(iii)": ["cycle` 필드", "cycle 필드", "tail 금지"]}
    # V3 (c64, P19): 어휘가 아니라 **규약의 내용**을 노린다. 각 항은 그 규약을 나르는
    # 알려진 표현들의 논리합이며, 새 표현이 관측되면 여기에 더한다(그 추가는 자[尺]
    # 변경이므로 사이클 보고에 선언한다). 넓히되 **규약 간 경계는 넘지 않는다** —
    # 아무 캡슐이나 3/3으로 통과시키는 자가 되면 P19 (a)가 반증된다.
    v3 = {
        "(i)": ["devloop-self", "devloop_self"],
        "(ii)": ["mtime", "미커밋", "HEAD보다", "newer", "영토 규약"],
        "(iii)": ["cycle` 필드", "cycle 필드", "tail 금지", "tail/cat/head",
                  "c48_step0_check", "번호·모드", "열지 마"],
    }
    for label, rules in (("V1 (c46 원본 니들)", v1), ("V2 (c47 확장 니들)", v2),
                         ("V3 (c64 의미 니들)", v3)):
        hits, detail = needle_reach(shown, rules)
        print(f"  {label:22s} capsule_reach={hits}/3  {detail}")

    for lit in ("tail 금지", "cycle 필드", "cycle` 필드", "mtime", "devloop-self",
                "c48_step0_check", "번호·모드"):
        print(f"    literal {lit!r:18s} in_capsule={int(lit in shown)}")

    # 원문 인쇄 (c64, P19 ②) — 관측 23이 명시한 수용 기준의 직접 이행.
    # 니들 판본은 표류하지만 원문은 표류하지 않는다. 다음 손이 육안으로 대조한다.
    # 주의: 이 캡슐은 SessionStart 주입본과 **같은 질의·다른 시각**의 별개 응답이다.
    print(f"  capsule_sha256={hashlib.sha256(capsule.encode('utf-8')).hexdigest()[:16]}"
          f"  shown_chars={len(shown)}")
    print("  [캡슐 원문 — SessionStart 주입본의 재취득본, 동일 질의·다른 시각]")
    for line in shown.splitlines():
        print(f"  | {line}")


if __name__ == "__main__":
    part_n()
    # part_n을 1행에 남긴다 — 그 배너가 F-절차0 처치이고 P16 (a)가 5/5로 성립한
    # 작동 중인 처치다. 몸 지문은 그 **직후**(여전히 첫 화면)에 세운다.
    part_body()
    part_recall()
    part_a()
    part_b()
