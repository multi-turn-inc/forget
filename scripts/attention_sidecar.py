#!/usr/bin/env python3
"""주의 사이드카 — 전사를 보며 작업 블록을 유지한다 (2026-09-07).

  .venv/bin/python scripts/attention_sidecar.py                 # 최신 Claude Code 전사를 따라간다
  .venv/bin/python scripts/attention_sidecar.py --source <jsonl> [--once] [--force] [--dry] [--interval 2]
"""
from __future__ import annotations
import argparse, glob, json, os, socket, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forget import attention as T


HARNESS_GLOBS = {"claude": ["~/.claude/projects/*/*.jsonl"], "pi": ["~/.pi/agent/sessions/*/*.jsonl"],
                 "codex": ["~/.codex/sessions/*/*/*/rollout-*.jsonl"], "body": ["~/.forget/body/*.jsonl"]}
HARNESS_ENTRYPOINTS = {"sdk-cli", None}   # 상주·devloop 등 SDK로 띄운 세션의 user 턴은 «사람 발화»가 아니다 — latest_transcript가 이들에 끌려 정훈 창을 놓쳤다(09-21 관측: 오늘 log.jsonl에 정훈 원문 0줄)


def _last_user_ts(path: str) -> float:
    """전사 꼬리에서 마지막 «사람 발화»의 시각. 도구 결과·자동 세션은 0에 가깝다.
    꼬리는 8MB까지 본다 — 도구 출력이 큰 세션은 마지막 사람 말이 수 MB 위에 있다(2026-09-07 실측)."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 8 * 1024 * 1024)); data = f.read().decode("utf-8", "ignore")
    except Exception:
        return 0.0
    best = 0.0
    born = 0.0                                     # pi 세션 헤더 시각 — 이식된(더 오래된 시각의) 턴은 «이 파일에서 말한 것»이 아니다
    try:
        with open(path, "rb") as f:
            head = json.loads(f.readline().decode("utf-8", "ignore"))
        if head.get("type") == "session":
            from datetime import datetime as _dt
            born = _dt.fromisoformat(str(head.get("timestamp", "")).replace("Z", "+00:00")).timestamp()
    except Exception:
        born = 0.0
    for line in data.splitlines():
        if '"role":"user"' not in line and '"role": "user"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message") or {}
        if not m and d.get("type") == "response_item":                 # Codex
            pl = d.get("payload") or {}
            if pl.get("type") != "message" or pl.get("role") != "user":
                continue
            m = {"role": "user", "content": pl.get("content", [])}
        c = m.get("content")
        if c is None or d.get("isSidechain") or d.get("isCompactSummary") or d.get("isMeta"):
            continue
        if d.get("entrypoint") in HARNESS_ENTRYPOINTS:
            continue                               # 몸(상주)이 주입한 턴 — 사람이 아니다. 2026-09-21 실측: 내 세션 10개 전부 sdk-cli, 정훈 창은 cli/claude-desktop
        if isinstance(c, list) and c and isinstance(c[0], dict) and c[0].get("type") in ("tool_result",):
            continue
        try:
            txt = str(c) if isinstance(c, str) else "".join(p.get("text", "") for p in c if isinstance(p, dict))
        except (TypeError, AttributeError):
            continue
        if not txt.strip() or txt.startswith("<") or txt.startswith("[Request interrupted"):
            continue
        ts = d.get("timestamp") or ""
        try:
            from datetime import datetime
            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
        except Exception:
            t = os.path.getmtime(path)
        if born and t < born - 5:
            continue                               # 이식분 제외
        best = max(best, t)
    return best


def latest_transcript(harness: str = "auto") -> Path:
    """여러 세션이 동시에 살아 있을 때는 mtime이 아니라 «사람이 마지막으로 말한» 전사를 따른다
    (자동 세션·다른 창의 도구 소음에 끌려가지 않게)."""
    keys = list(HARNESS_GLOBS) if harness == "auto" else [harness]
    files = [f for k in keys for g in HARNESS_GLOBS[k] for f in glob.glob(os.path.expanduser(g))]
    recent = sorted(files, key=os.path.getmtime, reverse=True)[:RECENT_WINDOW]
    return Path(max(recent, key=lambda f: (_user_ts_cached(f), os.path.getmtime(f))))


RECENT_WINDOW = 48   # mtime 상위 8은 너무 좁았다 — SDK 세션 8개가 정훈 창보다 새로우면 창이 슬라이스 밖으로 밀려 entrypoint 필터가 닿지도 못한다(09-21 실측: 1시간 내 수정 20개, 6시간 111개)
_TS_CACHE: dict[str, tuple[float, int, float]] = {}   # path -> (mtime, size, last_user_ts) — 안 바뀐 파일은 다시 읽지 않는다


def _user_ts_cached(path: str) -> float:
    try:
        st = os.stat(path); key = (st.st_mtime, st.st_size)
    except Exception:
        return 0.0
    hit = _TS_CACHE.get(path)
    if hit and hit[:2] == key:
        return hit[2]
    ts = _last_user_ts(path)
    _TS_CACHE[path] = (key[0], key[1], ts)
    return ts


def ensure_tunnel() -> None:
    host, port = "127.0.0.1", int(T.LLM_URL.rsplit(":", 1)[-1])
    s = socket.socket(); s.settimeout(1)
    try:
        s.connect((host, port)); return
    except Exception:
        pass
    finally:
        s.close()
    subprocess.Popen(["ssh", "-N", "-o", "ExitOnForwardFailure=yes", "-L", f"{port}:127.0.0.1:11434", "spark"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)


def status() -> int:
    st = T.load_state()
    print(T.render_block(st.get("block", []), st.get("updated_at")) or "(블록 비어 있음)")
    log = T.ATTN_DIR / "log.jsonl"
    if log.exists():
        last = [json.loads(l) for l in log.read_text().splitlines()[-30:]]
        judges = [l for l in last if l.get("kind") == "judge"]
        if judges:
            j = judges[-1]
            print(f"마지막 판정 {j['at'][11:16]}Z · 빠름 {j.get('fast_s')}s · 게이트 {j.get('gate_s')}s · 판정 {j.get('judge_s')}s · 놀람 {j.get('judge', {}).get('surprise')}")
        sil = sum(1 for l in last if l.get("kind") == "silence")
        print(f"최근 30틱 중 침묵 {sil}")
    prop = T.ATTN_DIR / "proposals.jsonl"
    n = len(prop.read_text().splitlines()) if prop.exists() else 0
    print(f"관찰 저장 {n}건 · 소스 {st.get('source', '?')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source"); ap.add_argument("--once", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--interval", type=float, default=2.0); ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--harness", choices=["auto", "claude", "pi", "codex", "body"], default=os.getenv("FORGET_ATTENTION_HARNESS", "auto"),
                    help="따라갈 전사의 하네스. 두 하네스를 번갈아 쓰는 동안은 하나를 못 박는다")
    ap.add_argument("--status", action="store_true", help="지금 들고 있는 블록·마지막 틱·관찰 수를 보여주고 끝낸다")
    a = ap.parse_args()
    if a.status:
        return status()
    src = Path(a.source) if a.source else latest_transcript(a.harness)
    ensure_tunnel()
    st = T.load_state()
    print(f"source {src}  block {len(st['block'])}", file=sys.stderr)
    while True:
        try:
            if not a.source:                       # 새 세션이 열리면 그쪽을 따라간다
                cur = latest_transcript(a.harness)
                if cur != src:
                    print(f"switch → {cur}", file=sys.stderr); src = cur
            r = T.tick(st, src, force=a.force, k_actions=a.k, dry=a.dry)
            if not a.dry:
                T.save_state(st)
            if r.get("status") not in ("idle", "wait"):
                print(json.dumps(r, ensure_ascii=False)[:1200], file=sys.stderr)
        except Exception as e:
            T.log("error", error=repr(e)[:300]); print("error", e, file=sys.stderr)
        if a.once:
            break
        a.force = False
        time.sleep(a.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
