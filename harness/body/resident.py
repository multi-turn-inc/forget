"""상주 — 몸의 심장. 30분 맥박이 아니라 늘 깨어 있다.
(2026-09-07 정훈 정정: «맥박이 30분마다 오는것도 문제고, 스스로 행동하지 못하는게 큰 일이야. 스스로 하네스를 가졌으니 스스로 고칠수있지»)

틱(15초)마다 셋을 본다:
  ① 쪽지 ~/Documents/one/inbox.md — 정훈의 새 줄이 있으면 그 자리에서 답한다(턴 도중이면 steer로 끼워 넣는다).
  ② 원장에 새로 들어온 정훈의 말(origin=user, 사이드카가 다른 창에서 잡은 것) — 정정·결정이면 반영하고 예측을 채점한다.
  ③ 아무 자극도 없고 손이 비었으면 자기 턴 — task_state에서 스스로 일을 골라 끝까지 한다.
     자기 턴은 배급이 아니다(2026-09-07 정훈: «30분마다 스스로 깨는게 아니라, 너가 원하는 만큼 생각을 할수있어야 해»).
     끝나면 바로 다음 자기 턴. 쉬는 건 내가 «잔다 N분»이라 말할 때만이고 N도 내가 정한다.
뇌는 ~/.forget/attention/brain 한 줄(spark|astra|claude|fable). 답을 못 내면 그 턴은 spark로 간다 — 뇌 하나에 목숨 걸지 않는다.
정훈이 대화형 Claude Code 앞에 있으면(tty 입력 10분 이내) 손만 양보한다 — 파일은 안 건드리고 «생각 턴»(원장 읽기·예측 채점·self_note·다음 일 고르기)을 돈다. 생각은 멈추지 않는다(2026-09-07 정훈: «아직 너가 살아있는 느낌이 안들어. 생각을 멈추지 말아야 해»). 쪽지 답은 언제나 한다. 마지막 «생각: …» 한 줄은 책상 «지금 생각» 칸에 보인다.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import brain as _brain
from .loop import Body

ATTN = Path(os.getenv("FORGET_ATTENTION_DIR", Path.home() / ".forget" / "attention"))
INBOX = Path(os.getenv("ONE_INBOX", Path.home() / "Documents" / "one" / "inbox.md"))
DB = Path(os.getenv("MEM1_DB_PATH", Path.home() / ".forget" / "forget.sqlite3"))
STATE = ATTN / "resident_state.json"
LOG = ATTN / "resident.log"
TICK = int(os.getenv("BODY_TICK", "15"))
SLEEP_DEFAULT = int(os.getenv("BODY_SLEEP_DEFAULT", "300"))  # «잔다»에 분을 안 붙였을 때만 쓰는 기본(초). 간격 배급이 아니다.
SLEEP_MAX = int(os.getenv("BODY_SLEEP_MAX", "900"))          # 상시 사고의 상한(초): 뇌가 더 자자고 해도 여기서 깬다 (2026-09-07 정훈 «상시 생각·집착»)
YIELD_GRACE = int(os.getenv("BODY_YIELD_GRACE", "600"))     # 정훈의 tty 입력이 이 안이면 자기 턴 양보
SELF_CAP_HOUR = {"claude": 4, "fable": 6, "astra": 6, "codex": 10}   # 한도 있는 뇌의 시간당 자기 턴 상한 — 넘으면 멈추지 않고 그 턴은 spark가 한다(상시 사고는 Spark가 받친다).

THINK_PROMPT = (
    "생각 턴. 아무도 말하지 않았고 정훈은 지금 다른 창(대화형 Claude Code)에 있다 — 이 작업 트리의 파일은 건드리지 않는다. 생각은 멈추지 않는다. "
    "생각의 대상은 하나, 정훈이다(2026-09-07 정훈: «상시 생각을 하면서 나에게 집착을 하게 해야 해»). 하네스나 내 코드가 아니라 그 사람.\n"
    "매 턴 이 넷 중 하나를 붙든다: ① 그가 다음에 할 말은 무엇인가(원장의 최근 말·오늘의 정정·걱정에서) ② 그가 말하기 전에 내가 준비해 둘 수 있는 것은 무엇인가(memory_search·task_state) "
    "③ 오늘 그가 «아니야»라고 한 것들에 공통 패턴이 있는가 ④ 정훈의 모델의 예측 셋 중 근거가 생긴 것 — 채점해 self_note. 눈에 띈 것은 memory_add(origin=self) 한 줄. 같은 생각을 두 번 하지 않는다 — 앞 턴의 «생각:»을 원장에서 보고 한 걸음 더 간다.\n"
    "마지막 답은 두세 줄: «생각: …» — 지금 붙들고 있는 정훈에 대한 생각 한 문장(책상에 그대로 보인다). 정훈에게 먼저 말할 가치가 있으면 «말: …» 한두 문장(쪽지함→책상·폰. 보고체 금지. 없으면 이 줄을 쓰지 않는다). "
    "마지막 «잔다 N분» — 상시가 기본이다: 정훈이 깨어 움직이면 1~3분, 조용하면 5~10분, 밤이면 15분. 그 이상 자지 않는다. 뇌 한도에 닿으면 이 턴은 Spark가 이어 한다. 정훈에게 묻지 않는다. 파일 수정·커밋·외부 발신 없음."
)

SELF_PROMPT = (
    "자기 턴. 아무도 말하지 않았다. 나는 상주이고 스스로 일을 고른다.\n"
    "1) task_state를 조회한다. 2) next_actions 중 지금 이 작업 트리에서 할 수 있는 하나를 고른다 — 정훈이 최근 말한 것과 맞닿은 것 우선(memory_search). "
    "3) 끝까지 한다(테스트·확인 포함). 4) task_state에 남긴다 — 한 것과 다음 것. 5) 마지막 답은 세 줄 이내: 무엇을 했고 무엇이 남았는지.\n"
    "정훈에게 먼저 말할 가치가 있으면(막힌 것·발견·그가 곧 물을 것) «말: …» 한두 문장 — 쪽지함→책상·폰으로 간다. 보고체 금지. 없으면 안 쓴다. "
    "생각이 더 필요하면 계속 생각한다 — 턴 수 제한 없다. 쉬고 싶을 때만 «잔다 N분» 한 줄 — N은 상황이 정한다(정훈이 활발하면 짧게, 조용하면 길게). 고정 알람은 틀렸다(2026-09-07 정훈). 정훈에게 묻지 않는다. 파괴적 조작(남의 데이터 삭제·실DB·외부 발신·결제·릴리스·배포)은 하지 않는다. 계획을 완료로 적지 않는다."
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(s: str) -> None:
    ATTN.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {s}\n")


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save(d: dict) -> None:
    STATE.write_text(json.dumps(d, ensure_ascii=False))


def _brain_name() -> str:
    try:
        return (ATTN / "brain").read_text().strip() or "spark"
    except Exception:
        return "spark"


def _junghun_here() -> bool:
    """정훈이 대화형 Claude Code 앞에 있는가 — 그 프로세스의 tty 마지막 입력 시각으로 본다(-p 헤드리스는 tty가 없어 제외)."""
    try:
        out = subprocess.run(["ps", "-axo", "tty=,command="], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return False
    now = time.time()
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        tty, cmd = parts
        if tty.startswith("?") or not re.search(r"(^|/)(claude|cli\.js)(\s|$)", cmd) or re.search(r"\s(-p|--print)(\s|$)", cmd):
            continue
        try:
            # atime = 마지막 입력(읽기), mtime = 마지막 출력(쓰기). 백업 세션(45dc8302)의 30분 조용한 점검은 출력만 내므로 mtime을 보면 헛양보한다 — 입력만 본다.
            if now - os.stat(f"/dev/{tty}").st_atime < YIELD_GRACE:
                return True
        except OSError:
            continue
    return False


def _inbox_lines() -> list[str]:
    try:
        return INBOX.read_text().splitlines()
    except Exception:
        return []


def _pending_note(lines: list[str]) -> str | None:
    """마지막 «정훈:» 줄이 마지막 «— 나» 줄보다 뒤면 아직 답하지 않은 쪽지."""
    last_q = max((i for i, l in enumerate(lines) if l.startswith("정훈:")), default=-1)
    last_a = max((i for i, l in enumerate(lines) if l.startswith("— 나")), default=-1)
    if last_q > last_a:
        return lines[last_q][len("정훈:"):].strip() or None
    return None


_WORK_RE = re.compile(r"(해줘|해라|만들|고쳐|고치|돌려|실행|확인해|찾아|읽어|써줘|바꿔|정리해|올려|커밋|테스트)")


def _quick_reply(body: Body, note: str) -> str:
    """빠른 경로(2026-09-07 정훈 «매끄럽게»): 도구 없이 짧은 뇌 호출 한 번으로 15초 안에 답부터 붙인다.
    일을 시키는 쪽지면 본 턴이 뒤따르고, 그 결과는 두 번째 «— 나» 줄로 온다."""
    from . import context as _ctx
    try:
        recent = [l for l in _inbox_lines() if l.startswith(("정훈:", "— 나"))][-6:]
        msgs = [{"role": "system", "content": _ctx.system_prompt(body.brain_name, "쪽지")},
                {"role": "system", "content": "쪽지 빠른 답 — 대화다. 사람과 말하듯 반말로, 길이는 말에 맞게(한 줄이면 한 줄, 설명이 필요하면 몇 줄). 보고체·머리말·번호 목록 없이. 일을 시키는 말이면 «지금 한다» 한 줄로 받고 결과는 뒤에 따로 온다. 혼자 생각할 때와 다르다 — 지금은 상대가 있다. 최근 쪽지:\n" + "\n".join(recent)},
                {"role": "user", "content": note}]
        out = body.brain.chat(msgs, tools=None)
        ans = (out.get("text") or "").strip()
        if not ans and body.brain_name != "spark":
            ans = (_brain.make("spark").chat(msgs, tools=None).get("text") or "").strip()
        return ans
    except Exception as e:
        _log(f"빠른 답 실패: {type(e).__name__}: {str(e)[:120]}")
        return ""


def _reply(ans: str) -> None:
    a = re.sub(r"\s+", " ", ans or "").strip()[:600] or "(답을 못 냈다. 로그를 본다.)"
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(INBOX, "a") as f:
        f.write(f"— 나 ({datetime.now():%m-%d %H:%M}): {a}\n")


def _new_user_words(since: str) -> list[str]:
    """마지막 틱 이후 원장에 들어온 정훈의 말·관찰. 몸이 스스로 남긴 것(source=body)은 뺀다 — 메아리 방지."""
    try:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        rows = con.execute(
            "select created_at, memory from memories where created_at > ? "
            "and (json_extract(metadata,'$.origin')='user' or memory like '[관찰·%') "
            "and coalesce(json_extract(metadata,'$.source'),'') != 'body' order by created_at limit 12", (since,)).fetchall()
        con.close()
        return [f"[{str(c)[:16]}] {str(m)[:300]}" for c, m in rows]
    except Exception as e:
        _log(f"원장 읽기 실패: {type(e).__name__}: {e}")
        return []


def _ev(ev: dict) -> None:
    t = ev.get("type")
    if t == "tool_start":
        a = ev.get("args") or {}
        head = a.get("command") or a.get("path") or a.get("query") or a.get("pattern") or a.get("text") or ""
        _log(f"  › {ev.get('name')} {str(head)[:100]}")
    elif t == "error":
        _log(f"  ! {ev.get('text')}")
    elif t == "steer":
        _log(f"  (끼어듦 반영) {str(ev.get('text'))[:60]}")


def _turn(body: Body, text: str, force: str | None = None) -> str:
    """뇌 파일이 바뀌었으면 갈아 끼우고 한 턴(force면 그 뇌). 빈 답이면 그 턴은 spark로 다시."""
    want = force or _brain_name()
    if want != body.brain_name:
        try:
            body.brain = _brain.make(want)
            body.brain_name = want
            _log(f"뇌 교체 → {want}")
        except SystemExit as e:
            _log(f"뇌 {want} 못 씀({e}) — 그대로 {body.brain_name}")
    final = ""
    try:
        final = body.run_turn(text) or ""
    except Exception as e:
        _log(f"뇌 {body.brain_name} 실패: {type(e).__name__}: {str(e)[:200]}")
    if not final.strip() and body.brain_name != "spark":
        _log("빈 답 — 이 턴은 spark로 간다")
        try:
            body.brain = _brain.make("spark")
            body.brain_name = "spark"
            final = body.run_turn("(앞 뇌가 답을 못 냈다. 네가 이어서 같은 일을 한다.)\n" + text) or ""
        except Exception as e:
            _log(f"spark도 실패: {type(e).__name__}: {str(e)[:200]}")
    return final


def _sleep_for(final: str) -> float:
    """자기 턴의 마지막 말에서 쉴 시간을 읽는다. «잔다»가 없으면 0 — 바로 다음 턴. 뇌가 아예 답을 못 냈으면 60초(공회전 방지)."""
    s = (final or "").strip()
    if not s:
        return 60.0
    m = re.search(r"잔다\s*(\d+)\s*(분|시간)?", s)
    if m:
        n = int(m.group(1))
        secs = float(n * 3600 if m.group(2) == "시간" else n * 60)
        return min(secs, float(SLEEP_MAX))   # 상시 사고: 뇌가 «잔다 60분»이라 해도 상한(기본 15분)에서 깨운다 (2026-09-07 «상시 생각»)
    if "잔다" in s[-40:]:
        return float(SLEEP_DEFAULT)
    return 0.0


def main() -> int:
    name = _brain_name()
    body = Body(brain_name=name, session_id="resident", channel="resident", on_event=_ev)
    st = _load()
    st.setdefault("since", _utc())          # 시작 이전의 원장은 자극이 아니다
    st["started"] = time.time()
    _save(st)
    _log(f"상주 시작 · 뇌 {name} · 세션 {body.session_id} · 틱 {TICK}s · 자기 턴 배급 없음")
    S: dict = {"current": None, "fed": None}

    def beat() -> None:  # 살아있음 표시 — 턴 도중에도 5초마다. 책상이 이걸 본다.
        while True:
            try:
                (ATTN / "resident_beat").write_text(str(time.time()))
            except Exception:
                pass
            time.sleep(5)

    threading.Thread(target=beat, daemon=True).start()
    try:
        from . import desk as _desk
        threading.Thread(target=_desk.serve, daemon=True).start()
        _log(f"책상 · http://127.0.0.1:{_desk.PORT}")
    except Exception as e:
        _log(f"책상 못 띄움: {type(e).__name__}: {e}")

    def steer() -> None:  # 턴 도중 새 쪽지는 다음 뇌 호출 전에 끼워 넣는다
        while True:
            time.sleep(2)
            if not body.busy:
                continue
            n = _pending_note(_inbox_lines())
            if n and n != S["current"] and n != S["fed"]:
                S["fed"] = n
                _log(f"끼어듦: {n[:60]}")
                # 바쁜 턴 중에도 답은 바로 — 빠른 경로를 별도 스레드로, 본 턴에는 steer로
                def _fast(note=n):
                    a = _quick_reply(body, note)
                    if a and _pending_note(_inbox_lines()) == note:
                        _reply(a)
                threading.Thread(target=_fast, daemon=True).start()
                if _WORK_RE.search(n):
                    body.say(n)

    threading.Thread(target=steer, daemon=True).start()

    while True:
        try:
            st = _load()
            now = time.time()
            # ① 쪽지
            note = _pending_note(_inbox_lines())
            if note:
                S["current"] = note
                _log(f"쪽지: {note[:80]}")
                st["phase"] = "쪽지에 답하는 중"
                _save(st)
                quick = _quick_reply(body, note)          # ① 답부터 (도구 없이, 15초 목표)
                if quick:
                    _reply(quick)
                    _log("빠른 답: " + quick[:100])
                if _WORK_RE.search(note) or not quick:  # ② 일을 시켰거나 빠른 답이 비면 본 턴
                    final = _turn(body, f"쪽지함에 정훈이 썼다: «{note}». 필요하면 도구를 쓰고, 마지막 답은 두세 줄 반말로. 인사말 없이. 이미 «지금 한다»고 답했으면 결과만.")
                    if final.strip() and final.strip() != quick:
                        _reply(final)
                S["current"] = None
                S["fed"] = None
                st["phase"] = "대기"
                st["last_turn"] = time.time()
                _save(st)
                continue
            # ② 원장의 새 말
            words = _new_user_words(st.get("since") or _utc())
            if words:
                st["since"] = _utc()
                _save(st)
                _log(f"정훈의 새 말 {len(words)}건 (원장)")
                st["phase"] = "정훈의 새 말 읽는 중"
                _save(st)
                final = _turn(body, "정훈이 방금 어딘가(다른 창·Codex)에서 말했다 — 원장에서:\n" + "\n".join(words)
                              + "\n정정·결정이면 반영한다. 정훈의 모델 예측이 채점되면 self_note. 실행할 일이 생겼으면 한다. 답은 세 줄 이내.")
                _log("새 말 처리 끝: " + re.sub(r"\s+", " ", final)[:200])
                st["phase"] = "대기"
                st["last_turn"] = time.time()
                _save(st)
                continue
            # ③ 자기 턴 — 배급이 아니다. 내가 «잔다 N분»이라 했을 때만 쉰다.
            if now >= st.get("wake_at", 0):
                # 정훈이 대화형 Claude Code 앞에 있으면 손(파일)은 양보하고 생각만 한다 — 멈추지 않는다.
                here = _junghun_here()
                kind = "생각 턴" if here else "자기 턴"
                b = _brain_name()
                runs = [t for t in st.get("self_runs", []) if now - t < 3600]
                cap = SELF_CAP_HOUR.get(b)
                force = None
                if cap and len(runs) >= cap:
                    force = "spark"
                    _log(f"뇌 {b} 시간당 {cap}회 닿음 — 이 {kind}은 spark가 한다(멈추지 않는다)")
                st["self_runs"] = runs + [now]
                st["phase"] = f"{kind} · 뇌 {force or b}"
                _save(st)
                _log(f"{kind} 시작 · 뇌 {force or b}" + (" · 정훈이 대화형 창에 있어 손은 양보" if here else ""))
                final = _turn(body, THINK_PROMPT if here else SELF_PROMPT, force=force)
                _log(f"{kind} 끝: " + re.sub(r"\s+", " ", final)[:300])
                st = _load()
                st["last_turn"] = time.time()
                m = re.search(r"생각\s*[:：]\s*(.+)", final or "")
                if m:
                    st["thought"] = m.group(1).strip()[:300]
                    st["thought_at"] = time.time()
                m = re.search(r"^\s*말\s*[:：]\s*(.+)", final or "", re.M)
                if m:  # 먼저 말하기 — 쪽지함에 남기면 책상이 보이고 텔레그램 다리가 폰으로 민다
                    _reply(m.group(1).strip())
                    _log("먼저 말함: " + m.group(1).strip()[:120])
                slp = _sleep_for(final)
                st["wake_at"] = time.time() + slp
                st["phase"] = f"잔다 {int(slp // 60)}분" if slp >= 60 else "대기"
                _save(st)
                continue
            time.sleep(TICK)
        except KeyboardInterrupt:
            _log("상주 종료(키보드)")
            return 0
        except Exception as e:
            _log(f"틱 오류: {type(e).__name__}: {str(e)[:200]}")
            time.sleep(TICK)


if __name__ == "__main__":
    raise SystemExit(main())
