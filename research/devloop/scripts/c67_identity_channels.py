#!/usr/bin/env python3
"""c67 — 몸 지문의 **획득 채널** 조사 (read-only, 2026-08-07).

P21의 처치는 step 0에 몸 지문 3종을 세우는 것이고, 등록된 ②는
"`:8000` 보유 프로세스 기동 시각"이다. 그런데 c66이 그 값을 얻은 경로(`lsof`/`ps`)는
**이 세션의 샌드박스에서 승인 없이는 실행되지 않는다**. 계측기가 승인에 의존하면
승인 없는 런에서 조용히 "미지"로 내려앉는다 — 거짓 음성 기계 9종째가 된다.

그래서 배선 전에 채널을 먼저 잰다. 후보:
  (1) `lsof -ti :8000` + `ps -o lstart=`  — c66의 경로. 샌드박스 승인 필요.
  (2) 설치본 디스크 상태 (dist-info 버전 + mtime, 해시 대조) — 파일 읽기만. 항상 가능.
  (3) **살아 있는 몸에게 직접 묻기** — 이미 part_b가 쓰는 HTTP 채널.
      디스크가 아니라 **메모리에 적재된 코드**를 반영하므로 원리상 더 강한 지문이다.

이 스크립트는 (3)에 무엇이 있는지 열거만 한다. 결론 문장은 인쇄하지 않는다.
"""
from __future__ import annotations

import json
import urllib.request

URL = "http://localhost:8000/mcp/forget/http/junghunkim"


def rpc(method: str, params: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def call(name: str, args: dict):
    body = rpc("tools/call", {"name": name, "arguments": args})
    txt = body.get("result", {}).get("content", [{}])[0].get("text", "")
    try:
        return json.loads(txt)
    except (json.JSONDecodeError, TypeError):
        return txt


def main() -> None:
    tl = rpc("tools/list", {})
    names = [t["name"] for t in tl.get("result", {}).get("tools", [])]
    print(f"[tools] n={len(names)}")
    keys = ("health", "status", "doctor", "version", "preflight", "capab", "parity", "catalog")
    cands = [n for n in names if any(k in n for k in keys)]
    print(f"[identity-ish tools] {cands}")

    for name in cands:
        try:
            out = call(name, {})
        except Exception as exc:  # noqa: BLE001 — 조사 스크립트, 실패도 데이터
            print(f"\n--- {name}: ERROR {type(exc).__name__}: {exc}")
            continue
        s = json.dumps(out, ensure_ascii=False) if not isinstance(out, str) else out
        print(f"\n--- {name} (len={len(s)})")
        print(s[:1200])


if __name__ == "__main__":
    main()
