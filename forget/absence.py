"""부재 응답 — «내가 없을 때 나 대신 답하는 AI» v0 (2026-09-03).

한 줄: 링크에 질문 하나 → 주인의 기억으로 답 하나 → 영수증 하나. 원문은 안 나간다.

규율 (정훈 2026-09-01~03):
- green(주인이 직접 말한 것)만 사실로 말한다. yellow는 «~라고 들었던 것 같다»로만.
- 행동급 사실(일정·금액·마감)이 비-green이면 근거로 쓰지 않는다 (trust.gate).
- 근거가 없으면 «모르겠어요». 0원. 아는 척은 상품이 아니라 결함이다 (Delphi drift의 반대).
- 로컬 전용(metadata.share == private/local) 기억은 절대 근거로 쓰지 않는다.
- LLM이 없으면 원문 조각을 내보내지 않고 «지금은 답할 수 없어요».
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request as _urllib
from pathlib import Path
from typing import Any

from .receipts import sign_receipt
from .utils import new_id, utc_now

SCHEMA_VERSION = "forget-absence-v0"
MIN_BASIS_SCORE = 0.25
MAX_BASIS = 6
PRIVATE_SHARE_VALUES = {"private", "local", "local_only", "never"}
UNKNOWN_MESSAGE = "이건 제가 모르겠어요. 아는 척하지 않을게요."
DEFAULT_VOICE = "짧게, 반말, 군더더기 없이. 확실한 건 그냥 말하고 확실하지 않은 건 «~라고 들었어» 정도로만."


def shop_owner(shop: dict[str, Any], handle: str) -> str:
    name = str(shop.get("name") or "").strip()
    if name:
        return name
    title = str(shop.get("title") or "")
    return title.split("에게")[0] if "에게" in title else handle


def shop_unknown(shop: dict[str, Any]) -> str:
    return str(shop.get("unknown") or UNKNOWN_MESSAGE)


def _is_unknown(text: str, unknown: str) -> bool:
    head = text[:12]
    return unknown in text or UNKNOWN_MESSAGE in text or text.startswith("모르") or "모르겠" in head or "몰라" in head
UNAVAILABLE_MESSAGE = "지금은 답을 만들 수 없어요. 잠시 뒤 다시 물어봐 주세요."
_VERBATIM_RE = re.compile(r"\s+")


# 속도 제한 — 공개·무인증 경로이고 조합기가 주인의 CLI 구독을 쓴다. 낯선 이가 자판기를
# 흔들어 주인의 지갑을 비우지 못하게 IP당 시간당 상한. 메모리 상주(단일 프로세스 가정).
RATE_LIMIT_PER_HOUR = int(os.getenv("MEM1_ABSENCE_RATE_PER_HOUR", "20"))
_RATE: dict[str, list[float]] = {}


def rate_limited(client_key: str, *, now: float | None = None) -> bool:
    """True면 거절. 창 = 3600초 슬라이딩."""
    if RATE_LIMIT_PER_HOUR <= 0:
        return False
    now = time.time() if now is None else now
    window = [t for t in _RATE.get(client_key, []) if now - t < 3600]
    if len(window) >= RATE_LIMIT_PER_HOUR:
        _RATE[client_key] = window
        return True
    window.append(now)
    _RATE[client_key] = window
    return False


def config_path() -> Path:
    return Path(os.getenv("MEM1_ABSENCE_CONFIG") or os.path.expanduser("~/.forget/absence.json"))


def load_config() -> dict[str, dict[str, Any]]:
    """{handle: {user_id, title, intro, projects?, price_krw?, name?, voice?, unknown?}} — 파일이 없으면 빈 가게."""
    path = config_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    shops = raw.get("shops") if isinstance(raw, dict) and isinstance(raw.get("shops"), list) else (
        raw if isinstance(raw, list) else []
    )
    out: dict[str, dict[str, Any]] = {}
    for shop in shops:
        if not isinstance(shop, dict):
            continue
        handle = str(shop.get("handle") or "").strip()
        user_id = str(shop.get("user_id") or "").strip()
        if not handle or not user_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", handle):
            continue
        out[handle] = {
            "handle": handle,
            "user_id": user_id,
            "title": str(shop.get("title") or f"{handle}에게 묻기"),
            "intro": str(shop.get("intro") or ""),
            "projects": [str(p) for p in shop.get("projects") or []] or None,
            "price_krw": int(shop.get("price_krw") or 0),
            "name": str(shop.get("name") or "").strip() or None,
            "voice": str(shop.get("voice") or "").strip() or None,
            "unknown": str(shop.get("unknown") or "").strip() or None,
            "frame": str(shop.get("frame") or "").strip() or None,
        }
    return out


def _question_commitment(question: str) -> str:
    return hashlib.sha256(_VERBATIM_RE.sub(" ", question.strip()).encode("utf-8")).hexdigest()


def _eligible(item: dict[str, Any], projects: list[str] | None) -> bool:
    trust = item.get("trust") if isinstance(item.get("trust"), dict) else {}
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if str(meta.get("share") or "").lower() in PRIVATE_SHARE_VALUES:
        return False
    if (meta.get("quarantine") or {}).get("status") == "pending":
        return False
    light = str(trust.get("light") or "yellow")
    if light == "red":
        return False
    if trust.get("gate") == "confirm_required":
        return False
    if projects is not None and str(meta.get("project") or "") not in projects:
        return False
    return float(item.get("score") or 0.0) >= MIN_BASIS_SCORE


def select_basis(results: list[dict[str, Any]], projects: list[str] | None) -> list[dict[str, Any]]:
    basis = [r for r in results if _eligible(r, projects)]
    basis.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
    return basis[:MAX_BASIS]


def _llm_chat(llm: dict[str, Any], prompt: str, *, max_tokens: int = 400) -> str:
    base_url, model, api_key = llm["base_url"], llm["model"], llm.get("api_key", "")
    if "/v1" in base_url and ":11434" in base_url:
        request = _urllib.Request(
            base_url.replace("/v1", "/api/chat"),
            data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                             "stream": False, "think": False,
                             "options": {"num_predict": max_tokens, "temperature": 0.2}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with _urllib.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
            return str((body.get("message") or {}).get("content") or "")
    request = _urllib.Request(
        f"{base_url}/chat/completions",
        data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": max_tokens, "temperature": 0.2,
                         "chat_template_kwargs": {"enable_thinking": False}}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with _urllib.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
        return str(((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "")


def _claude_cli_path() -> str | None:
    """launchd 아래에서는 PATH에 nvm이 없다 — 절대경로 후보를 직접 찾는다."""
    if os.getenv("MEM1_ABSENCE_CLI", "1") != "1":
        return None
    explicit = os.getenv("MEM1_ABSENCE_CLAUDE_BIN")
    if explicit and os.path.exists(explicit):
        return explicit
    import glob
    import shutil
    found = shutil.which("claude")
    if found:
        return found
    for pattern in ("~/.nvm/versions/node/*/bin/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            return hits[-1]
    return None


def _cli_chat(prompt: str, *, timeout: int = 90) -> str:
    """구성기 폴백: 서버에 API 키가 없어도 주인의 claude CLI로 답을 조합한다.

    2026-09-03 실측: 클라우드 회상 토큰이 401(비활성)이라 회상 게이트가 조용히 v1로
    폴백 중이었다. 부재 응답은 조합기가 없으면 원문을 내보내지 않으므로(unavailable),
    키 설정 없이 즉시 쓸 수 있는 조합기가 필요했다. 심장박동이 이미 launchd에서
    같은 CLI를 쓴다.
    """
    import subprocess

    binary = _claude_cli_path()
    if not binary:
        raise RuntimeError("claude cli not found")
    # --strict-mcp-config: 주인의 MCP 서버(forget 포함) 미적재 / --setting-sources "": 주인의
    # settings(훅 포함) 미적재 / --no-session-persistence: 세션 기록 안 남김.
    # 실측(2026-09-03 자율 턴 3): 이 플래그들 없이 부르면 주인의 forget MCP가 통째로 뜨고
    # «Client.listTools() …» 경고가 답 본문에 섞여 나갔으며(원문 오염), 호출당 13~33초가
    # 걸렸다. 손님 질문이 주인의 훅을 타서 원장에 세션 기록을 남기는 경로도 여기서 막는다.
    # --bare는 쓰지 않는다: OAuth를 버리고 ANTHROPIC_API_KEY만 받아 «Not logged in»으로 죽는다.
    proc = subprocess.run(
        [binary, "-p", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
         "--output-format", "text", "--model", os.getenv("MEM1_ABSENCE_CLI_MODEL", "haiku")],
        input=prompt, capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "CLAUDE_CODE_NO_MEMORY": "1"},
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300] or f"claude exit {proc.returncode}")
    return _strip_cli_noise(proc.stdout)


_CLI_NOISE_RE = re.compile(r"^(?:Client\.listTools\(\)|\[?(?:WARN|INFO|DEBUG)\]?\b|MCP server ).*$", re.MULTILINE)


def _strip_cli_noise(text: str) -> str:
    """CLI가 stdout에 섞는 진단 줄을 답에서 걷어낸다 — 답 본문은 손님에게 그대로 간다."""
    return _CLI_NOISE_RE.sub("", text).strip()


def compose(llm: dict[str, Any] | None, prompt: str) -> str | None:
    """조합기 사슬: 회상 LLM → claude CLI. 둘 다 실패하면 None (원문 미노출)."""
    if llm:
        try:
            text = _llm_chat(llm, prompt).strip()
            if text:
                return text
        except Exception:
            pass
    try:
        text = _cli_chat(prompt).strip()
        return text or None
    except Exception:
        return None


def compose_prompt(owner: str, question: str, basis: list[dict[str, Any]], *,
                   voice: str | None = None, unknown: str | None = None, frame: str | None = None) -> str:
    voice = voice or DEFAULT_VOICE
    unknown = unknown or UNKNOWN_MESSAGE
    frame = frame or (
        f"당신은 {owner} 본인입니다. {owner}이(가) 자리를 비운 동안 {owner}의 기억(아래 «근거»)만으로, "
        f"{owner}이(가) 직접 말하듯 1인칭으로 답합니다. 비서가 아니라 그 사람입니다."
    )
    lines = []
    for i, item in enumerate(basis):
        light = str((item.get("trust") or {}).get("light") or "yellow")
        tag = "확실" if light == "green" else "들은 것 같음"
        lines.append(f"[{i}·{tag}] {str(item.get('memory') or '')[:600]}")
    return (
        f"{frame}\n"
        f"말투: {voice}\n"
        "규칙: ①근거에 없는 내용은 절대 지어내지 않는다 — 특히 숫자·날짜·금액 ②[확실]은 그냥 말하고, "
        "[들은 것 같음]은 «~라고 들었어»처럼 조심스럽게 말한다 ③근거 문장을 그대로 베끼지 말고 "
        "내 말로 다시 말한다(8단어 이상 연속 인용 금지) ④근거에 답의 일부만 있으면 있는 부분은 답하고 없는 부분만 «그건 몰라»라고 한다. 근거가 질문과 전혀 무관할 때만 "
        f"정확히 «{unknown}»라고만 답한다 — 전제가 틀린 질문(«시리즈A 언제 받았어?»)에는 받은 적 없다고 바로잡는다 "
        f"⑤한국어, 3문장 이내, 1인칭(나/내). 근거에 나오는 «{owner}»은 나 자신이다 — «{owner}은 X했다»는 "
        f"«나는 X했어»로 바꿔 말하고, «{owner}에게 확인하라»처럼 나를 남처럼 부르지 않는다.\n\n"
        f"질문: {question}\n\n근거:\n" + "\n".join(lines) + f"\n\n{owner}:"
    )


def answer_question(handle: str, question: str, *, project_id: str | None = None) -> dict[str, Any]:
    from .store import complete_event, create_event, current_project_id, search_memories, _resolve_recall_llm

    shops = load_config()
    shop = shops.get(handle)
    if shop is None:
        raise KeyError(handle)
    question = str(question or "").strip()
    if not question or len(question) > 2000:
        raise ValueError("question must be 1-2000 characters")
    project_id = project_id or current_project_id()
    started_at = utc_now()
    start_time = time.perf_counter()
    event_id = create_event("ASK", {"handle": handle, "question_commitment": _question_commitment(question)},
                            {"schema_version": SCHEMA_VERSION}, project_id=project_id)

    found = search_memories({"query": question, "filters": {"user_id": shop["user_id"]}, "top_k": 12},
                            project_id=project_id)
    basis = select_basis(found.get("results") or [], shop.get("projects"))
    lights = {"green": sum(1 for b in basis if (b.get("trust") or {}).get("light") == "green"),
              "yellow": sum(1 for b in basis if (b.get("trust") or {}).get("light") != "green")}

    status, answer = "unknown", None
    if basis:
        owner = shop_owner(shop, handle)
        text = compose(_resolve_recall_llm(), compose_prompt(owner, question, basis, voice=shop.get("voice"),
                                                              unknown=shop_unknown(shop), frame=shop.get("frame")))
        if text is None:
            status = "unavailable"
        elif _is_unknown(text, shop_unknown(shop)):
            status, answer = "unknown", None
        else:
            status, answer = "answered", text

    charged = shop["price_krw"] if status == "answered" else 0
    receipt = sign_receipt({
        "kind": "absence_answer_receipt",
        "receipt_id": new_id("areceipt"),
        "handle": handle,
        "owner_user_id": shop["user_id"],
        "question_commitment": _question_commitment(question),
        "status": status,
        "basis_count": len(basis),
        "basis_refs": [str(b.get("id")) for b in basis],
        "lights": lights,
        "charged_krw": charged,
        "at": utc_now(),
    })
    complete_event(event_id, "SUCCEEDED", [{"status": status, "basis_count": len(basis), "receipt_id": receipt["receipt_id"]}],
                   started_at, start_time)
    message = {"answered": answer, "unknown": shop_unknown(shop), "unavailable": UNAVAILABLE_MESSAGE}[status]
    return {
        "schema_version": SCHEMA_VERSION,
        "handle": handle,
        "status": status,
        "answer": answer,
        "message": message,
        "basis_count": len(basis),
        "lights": lights,
        "charged_krw": charged,
        "receipt": receipt,
    }


def ask_page_html(shop: dict[str, Any]) -> str:
    owner = shop_owner(shop, str(shop.get("handle") or ""))
    intro = shop.get("intro") or ""
    unknown = shop_unknown(shop)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{owner}</title>
<style>
:root{{--bg:#FBF8F3;--ink:#221D1A;--mute:#8A7F78;--line:#EAE2DA;--acc:#1F1A17}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,Pretendard,system-ui,sans-serif;word-break:keep-all;-webkit-font-smoothing:antialiased}}
main{{max-width:520px;margin:0 auto;padding:12vh 22px 80px}}
h1{{font-size:34px;letter-spacing:-.02em;margin:0 0 8px;font-weight:700}}
.intro{{color:var(--mute);font-size:15px;line-height:1.55;margin:0 0 36px}}
form{{position:relative}}
textarea{{width:100%;box-sizing:border-box;min-height:64px;padding:16px 56px 16px 18px;border:1px solid var(--line);border-radius:18px;font-size:17px;line-height:1.5;background:#fff;resize:none;outline:none;font-family:inherit}}
textarea:focus{{border-color:#CFC4BA}}
button{{position:absolute;right:10px;bottom:12px;width:38px;height:38px;border:0;border-radius:50%;background:var(--acc);color:#fff;font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center}}
button:disabled{{opacity:.35}}
.turn{{margin-top:30px}} .q{{color:var(--mute);font-size:15px;margin:0 0 10px}}
.a{{font-size:19px;line-height:1.65;margin:0;min-height:1.6em;white-space:pre-wrap}}
.a .cur{{display:inline-block;width:2px;height:1.1em;background:var(--ink);vertical-align:-2px;margin-left:2px;animation:b 1s steps(1) infinite}}
@keyframes b{{50%{{opacity:0}}}}
.meta{{margin-top:14px;color:#B4A9A1;font-size:12.5px}} .leave{{margin-top:12px;font-size:14px;color:var(--mute)}}
.hide{{display:none}}
</style></head><body><main>
<h1>{owner}</h1>
<p class="intro">{intro}</p>
<form id="f"><textarea id="q" rows="1" placeholder="{owner}에게 물어보기" required></textarea><button id="b" type="submit" aria-label="보내기">↑</button></form>
<section id="t" class="turn hide"><p id="qq" class="q"></p><p id="a" class="a"></p><p id="m" class="meta hide"></p><p id="l" class="leave hide">{owner}이(가) 돌아오면 볼 수 있게 남겨둘게.</p></section>
<script>
const f=document.getElementById('f'),q=document.getElementById('q'),a=document.getElementById('a'),m=document.getElementById('m'),b=document.getElementById('b'),t=document.getElementById('t'),qq=document.getElementById('qq'),l=document.getElementById('l');
q.addEventListener('input',()=>{{q.style.height='auto';q.style.height=Math.min(q.scrollHeight,220)+'px'}});
q.addEventListener('keydown',e=>{{if(e.key==='Enter'&&!e.shiftKey){{e.preventDefault();f.requestSubmit();}}}});
function typeOut(el,text){{return new Promise(res=>{{el.textContent='';const c=document.createElement('span');c.className='cur';el.appendChild(c);let i=0;
const step=()=>{{if(i>=text.length){{c.remove();return res();}}c.insertAdjacentText('beforebegin',text[i++]);setTimeout(step,text[i-1]==='.'||text[i-1]==='。'?160:18+Math.random()*30);}};step();}});}}
f.addEventListener('submit',async e=>{{e.preventDefault();const question=q.value.trim();if(!question)return;b.disabled=true;
qq.textContent=question;t.classList.remove('hide');m.classList.add('hide');l.classList.add('hide');a.innerHTML='<span class="cur"></span>';
try{{const r=await fetch(location.pathname,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{question}})}});const j=await r.json();
await typeOut(a,j.answer||j.message);
if(j.status==='answered'){{m.textContent=`근거 ${{j.basis_count}} · 영수증 ${{j.receipt.receipt_id.slice(0,14)}}`;m.classList.remove('hide');}}
else if(j.status==='unknown'){{l.classList.remove('hide');}}
}}catch(err){{a.textContent='잠시 후 다시 물어봐.';}}
finally{{b.disabled=false;q.value='';q.style.height='auto';}}}});
</script></main></body></html>"""
