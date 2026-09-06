"""책상 — 무슨 일이 벌어지는지 한눈에 (2026-09-07 정훈: «어떻게 되고있는지 파악이 안되네 UX를 고려해서 앱을 만들어줘»).
상주가 켜지면 같이 뜬다(http://127.0.0.1:8031). 혼자서도 뜬다: python -m harness.body.desk
왼쪽: 지금(살아있음·뇌·하는 일·다음 깸) + 정훈의 모델의 예측 + 작업 상태.
가운데: 지금 턴의 흐름 — 내 말·도구 호출·결과가 흐르는 대로.
오른쪽: 쪽지 — 여기서 쓰면 inbox.md에 «정훈:» 줄로 붙고 상주가 그 자리에서 듣는다.
서버는 표준 라이브러리만. 상태는 전부 파일에서 읽는다 — 상주가 죽어도 책상은 «상주 안 뜸»을 보여 준다.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ATTN = Path(os.getenv("FORGET_ATTENTION_DIR", Path.home() / ".forget" / "attention"))
INBOX = Path(os.getenv("ONE_INBOX", Path.home() / "Documents" / "one" / "inbox.md"))
BODY_DIR = Path(os.getenv("BODY_DIR", Path.home() / ".forget" / "body"))
SESSION = BODY_DIR / "resident.jsonl"
STATE = ATTN / "resident_state.json"
BEAT = ATTN / "resident_beat"
LOG = ATTN / "resident.log"
SCHEMA = ATTN / "schema.md"
PORT = int(os.getenv("BODY_DESK_PORT", "8031"))

_task_cache: dict = {"t": 0.0, "v": ""}


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except Exception:
        return ""


def _tail(p: Path, n: int) -> list[str]:
    try:
        with open(p, errors="replace") as f:
            return list(deque(f, maxlen=n))
    except Exception:
        return []


def _local(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
    except Exception:
        return ""


def alive() -> bool:
    try:
        return time.time() - float(_read(BEAT).strip() or 0) < 20
    except Exception:
        return False


def state() -> dict:
    try:
        return json.loads(_read(STATE) or "{}")
    except Exception:
        return {}


def brain() -> str:
    return _read(ATTN / "brain").strip() or "spark"


def _head(a: dict) -> str:
    for k in ("command", "path", "query", "pattern", "text", "summary", "task_id"):
        if a.get(k):
            return str(a[k])[:140]
    return json.dumps(a, ensure_ascii=False)[:140]


def turn() -> tuple[list[dict], str]:
    """세션 파일 꼬리에서 마지막 턴(마지막 사용자 문자열 메시지부터)을 흐름으로."""
    rows = []
    for line in _tail(SESSION, 400):
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    start = max((i for i, r in enumerate(rows) if r.get("type") == "user" and isinstance((r.get("message") or {}).get("content"), str)), default=-1)
    if start < 0:
        return [], ""
    items: list[dict] = []
    for r in rows[start:]:
        m = r.get("message") or {}
        c = m.get("content")
        ts = _local(r.get("timestamp") or "")
        if r.get("type") == "user" and isinstance(c, str):
            items.append({"k": "prompt", "t": c[:500], "ts": ts})
        elif r.get("type") == "user" and isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "tool_result":
                    items.append({"k": "result", "t": str(p.get("content") or "")[:300], "ts": ts})
        elif r.get("type") == "assistant":
            for p in c if isinstance(c, list) else []:
                if not isinstance(p, dict):
                    continue
                if p.get("type") == "text" and p.get("text", "").strip():
                    items.append({"k": "say", "t": p["text"][:2000], "ts": ts})
                elif p.get("type") == "tool_use":
                    items.append({"k": "tool", "name": p.get("name"), "head": _head(p.get("input") or {}), "ts": ts})
    return items[-120:], _local(rows[start].get("timestamp") or "")


def inbox() -> list[dict]:
    out = []
    for l in _read(INBOX).splitlines():
        l = l.rstrip()
        if l.startswith("정훈:"):
            out.append({"who": "정훈", "t": l[3:].strip()})
        elif l.startswith("— 나"):
            out.append({"who": "나", "t": re.sub(r"^— 나\s*(\([^)]*\))?:?\s*", "", l)})
        elif l.strip() and out:
            out[-1]["t"] += "\n" + l
    return out[-40:]


def predictions() -> list[str]:
    s = _read(SCHEMA)
    m = re.search(r"^## 예측\s*$(.*?)(?=^## |\Z)", s, re.S | re.M)
    if not m:
        return []
    return [re.sub(r"^\s*[-*]\s*", "", l).strip() for l in m.group(1).splitlines() if l.strip().startswith(("-", "*"))]


def task() -> str:
    if time.time() - _task_cache["t"] < 30:
        return _task_cache["v"]
    try:
        from . import tools as _tools
        v = _tools.run("task_state", {})[:2500]
    except Exception as e:
        v = f"(작업 상태 못 읽음: {type(e).__name__})"
    _task_cache.update(t=time.time(), v=v)
    return v


def snapshot() -> dict:
    st = state()
    items, ts = turn()
    return {"alive": alive(), "brain": brain(), "phase": st.get("phase") or ("대기" if alive() else ""), "state": st,
            "turn": items, "turn_ts": ts, "inbox": inbox(), "log": [l.rstrip() for l in _tail(LOG, 40)],
            "predictions": predictions(), "task": task(), "now": time.time()}


def say(text: str) -> None:
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    with open(INBOX, "a") as f:
        f.write(f"정훈: {text.strip()}\n")


HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>책상</title>
<style>
:root{--bg:#f7f6f2;--fg:#1c1b19;--mute:#8a877f;--line:#e3e0d8;--card:#fff;--ok:#2f9e5b;--off:#b5b2aa;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--fg:#ecebe6;--mute:#8d8b84;--line:#2a2927;--card:#1c1c1a;--off:#4a4946}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Pretendard","Apple SD Gothic Neo",system-ui,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:14px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:1}
.dot{width:10px;height:10px;border-radius:50%;background:var(--off)}.dot.on{background:var(--ok);box-shadow:0 0 0 4px rgba(47,158,91,.15)}
header b{font-weight:600}header .m{color:var(--mute)}header .sp{flex:1}
main{display:grid;grid-template-columns:290px minmax(0,1fr) 360px;gap:18px;padding:18px 22px;max-width:1560px;margin:0 auto;align-items:start}
@media(max-width:1050px){main{grid-template-columns:1fr}}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
section+section{margin-top:18px}
h2{font-size:12px;letter-spacing:.06em;color:var(--mute);margin:0 0 10px;font-weight:600}
.kv{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-top:1px solid var(--line)}.kv:first-child{border-top:0}.kv span:first-child{color:var(--mute)}.kv span:last-child{text-align:right}
.stream{max-height:calc(100vh - 110px);overflow:auto}
.it{padding:8px 0;border-top:1px solid var(--line);position:relative}.it:first-child{border-top:0}
.it.prompt{color:var(--mute);font-size:13px;white-space:pre-wrap}.it.say{white-space:pre-wrap}
.it.tool{font:13px var(--mono);color:var(--mute);word-break:break-all}.it.tool b{color:var(--fg);font-weight:600}
.it.result{font:12px/1.4 var(--mono);color:var(--mute);white-space:pre-wrap;padding-left:14px;border-left:2px solid var(--line);border-top:0;margin-left:2px;word-break:break-all}
.ts{font-size:11px;color:var(--mute);float:right;margin-left:8px}
.note{padding:7px 0;border-top:1px solid var(--line);white-space:pre-wrap}.note:first-child{border-top:0}.note.you{color:var(--mute)}.note .w{font-size:12px;color:var(--mute);margin-right:6px}
form{display:flex;gap:8px;margin-top:12px}input{flex:1;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
button{padding:10px 14px;border:0;border-radius:8px;background:var(--fg);color:var(--bg);font:inherit;cursor:pointer}
pre{font:12px/1.45 var(--mono);white-space:pre-wrap;margin:0;color:var(--mute);word-break:break-all}
ul{margin:0;padding-left:18px}li{margin:4px 0;font-size:14px}
</style></head><body>
<header><div class="dot" id="dot"></div><b id="alive">…</b><span class="m" id="brain"></span><span class="sp"></span><span class="m" id="phase"></span></header>
<main>
<div>
<section><h2>지금</h2><div id="now"></div></section>
<section><h2>정훈의 모델 · 예측</h2><ul id="pred"></ul></section>
<section><h2>작업 상태</h2><pre id="task"></pre></section>
</div>
<section class="stream"><h2 id="turnh">지금 턴</h2><div id="turn"></div></section>
<div>
<section><h2>쪽지</h2><div id="inbox"></div><form id="f"><input id="t" placeholder="여기 쓰면 상주가 듣는다" autocomplete="off"><button>보내기</button></form></section>
<section><h2>로그</h2><pre id="log"></pre></section>
</div>
</main>
<script>
const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function rel(t,now){if(!t)return '—';const d=now-t;const a=Math.abs(d),s=d<0?' 뒤':' 전';if(a<60)return Math.round(a)+'초'+s;if(a<3600)return Math.round(a/60)+'분'+s;return (a/3600).toFixed(1)+'시간'+s}
async function tick(){try{const s=await(await fetch('/api/state',{cache:'no-store'})).json();const now=s.now||Date.now()/1000;
$('dot').className='dot'+(s.alive?' on':'');$('alive').textContent=s.alive?'살아 있다':'상주 안 뜸';$('brain').textContent='뇌 '+s.brain;$('phase').textContent=s.phase||'';
const st=s.state||{};const wake=st.wake_at&&st.wake_at>now?rel(st.wake_at,now):'바로';
$('now').innerHTML=[['하는 일',s.phase||'—'],['지금 생각',st.thought?st.thought+' ('+rel(st.thought_at,now)+')':'—'],['마지막 턴',rel(st.last_turn,now)],['다음 자기 턴',wake],['이번 시간 자기 턴',(st.self_runs||[]).filter(t=>now-t<3600).length+'회'],['상주 시작',rel(st.started,now)]].map(([k,v])=>`<div class="kv"><span>${k}</span><span>${esc(v)}</span></div>`).join('');
$('pred').innerHTML=(s.predictions||[]).map(p=>`<li>${esc(p)}</li>`).join('')||'<li>없음</li>';
$('task').textContent=s.task||'';
$('turnh').textContent=s.turn_ts?'지금 턴 · '+s.turn_ts+' 시작':'지금 턴';
const el=$('turn'),sc=el.parentElement;const atBottom=sc.scrollTop+sc.clientHeight>=sc.scrollHeight-60;
el.innerHTML=(s.turn||[]).map(i=>i.k==='tool'?`<div class="it tool"><span class="ts">${i.ts}</span><b>${esc(i.name)}</b> ${esc(i.head)}</div>`:i.k==='result'?`<div class="it result">${esc(i.t)}</div>`:`<div class="it ${i.k}"><span class="ts">${i.ts}</span>${esc(i.t)}</div>`).join('')||'<div class="it prompt">아직 턴이 없다</div>';
if(atBottom)sc.scrollTop=sc.scrollHeight;
$('inbox').innerHTML=(s.inbox||[]).map(n=>`<div class="note ${n.who==='나'?'me':'you'}"><span class="w">${esc(n.who)}</span>${esc(n.t)}</div>`).join('')||'<div class="note you">아직 없다</div>';
$('log').textContent=(s.log||[]).join('\n');
}catch(e){$('alive').textContent='책상 연결 끊김';$('dot').className='dot'}}
$('f').onsubmit=async e=>{e.preventDefault();const t=$('t').value.trim();if(!t)return;$('t').value='';await fetch('/api/say',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});tick()};
tick();setInterval(tick,2000);
</script></body></html>
"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 조용히
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._send(200, json.dumps(snapshot(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        else:
            # 화면은 파일(desk.html)이 정본 — 고치면 재시작 없이 다음 요청에 반영. 없으면 내장 HTML.
            page = Path(__file__).with_name("desk.html")
            body = page.read_text() if page.exists() else HTML
            self._send(200, body.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path.startswith("/api/say"):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                d = {}
            t = str(d.get("text") or "").strip()
            if t:
                say(t)
            self._send(200, b'{"ok":true}', "application/json")
        else:
            self._send(404, b"", "text/plain")


def serve(port: int = PORT) -> None:
    ThreadingHTTPServer.allow_reuse_address = True
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    print(f"책상 · http://127.0.0.1:{PORT}")
    serve()
