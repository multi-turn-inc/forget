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


def latest_transcript() -> Path:
    files = glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl"))
    return Path(max(files, key=os.path.getmtime))


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source"); ap.add_argument("--once", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--interval", type=float, default=2.0); ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args()
    src = Path(a.source) if a.source else latest_transcript()
    ensure_tunnel()
    st = T.load_state()
    print(f"source {src}  block {len(st['block'])}", file=sys.stderr)
    while True:
        try:
            if not a.source:                       # 새 세션이 열리면 그쪽을 따라간다
                cur = latest_transcript()
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
