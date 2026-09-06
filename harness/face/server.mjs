// 얼굴 — pi(rpc 모드)를 뒤에 두고 브라우저로 대화한다 (2026-09-07, 정훈 «pi 인터페이스 너무 구려»).
// 사용: node harness/face/server.mjs [--session <jsonl>] [--provider anthropic] [--model claude-fable-5-1] [--port 8030]
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
import { homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const PORT = Number(opt("--port", 8030));
const SESSION = opt("--session", null);
const PROVIDER = opt("--provider", process.env.FORGET_FACE_PROVIDER || "anthropic");
const MODEL = opt("--model", process.env.FORGET_FACE_MODEL || "claude-fable-5-1");
const ATTN = process.env.FORGET_ATTENTION_DIR || join(homedir(), ".forget", "attention");
const HERE = dirname(fileURLToPath(import.meta.url));

const BACKEND = opt("--backend", process.env.FORGET_FACE_BACKEND || "pi");   // pi | claude
// claude 백엔드: «나는 원래 여기 있었다»(2026-09-07) — Claude Code 세션을 포크해 이어 간다. 옮기지 않고 얼굴만 씌운다.
let child;
if (BACKEND === "claude") {
  const cArgs = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--include-partial-messages", "--verbose",
                 "--permission-mode", process.env.FORGET_FACE_PERMISSION || "bypassPermissions"];
  if (SESSION) cArgs.push("--resume", SESSION, "--fork-session");
  if (MODEL && MODEL !== "claude-fable-5-1") cArgs.push("--model", MODEL);
  child = spawn("claude", cArgs, { cwd: process.cwd(), stdio: ["pipe", "pipe", "pipe"], env: process.env });
} else {
  const piArgs = ["--mode", "rpc", "--provider", PROVIDER, "--model", MODEL, "--approve"];
  if (SESSION) piArgs.push("--session", SESSION); else piArgs.push("--name", `얼굴 ${new Date().toISOString().slice(5, 16).replace("T", " ")}`);
  child = spawn("pi", piArgs, { cwd: process.cwd(), stdio: ["pipe", "pipe", "pipe"], env: process.env });
}
const pi = child;
pi.stderr.on("data", (d) => process.stderr.write(`[${BACKEND}] ${d}`));
pi.on("exit", (c) => { console.error(`${BACKEND} exited ${c}`); process.exit(c ?? 0); });

const clients = new Set();
const history = [];               // 최근 이벤트 링(새 클라이언트 재생용)
let seq = 0, buf = "";
function broadcast(ev) {
  ev._seq = ++seq; history.push(ev); if (history.length > 400) history.shift();
  const line = `data: ${JSON.stringify(ev)}\n\n`;
  for (const c of clients) c.write(line);
}
pi.stdout.on("data", (d) => {
  buf += d.toString("utf8");
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i).replace(/\r$/, ""); buf = buf.slice(i + 1);
    if (!line.trim()) continue;
    try { broadcast(JSON.parse(line)); } catch { broadcast({ type: "raw", line }); }
  }
});
const send = (cmd) => pi.stdin.write(JSON.stringify(cmd) + "\n");
const pending = new Map();
function ask(cmd, timeoutMs = 8000) {   // 요청/응답 상관
  if (BACKEND === "claude") {
    if (cmd.type === "prompt") { send({ type: "user", message: { role: "user", content: cmd.message } }); return Promise.resolve({ success: true }); }
    if (cmd.type === "get_state") return Promise.resolve({ success: true, data: { model: { provider: "anthropic", id: MODEL }, sessionName: claudeState.session ? `claude ${claudeState.session.slice(0, 8)}` : "claude" } });
    if (cmd.type === "get_messages") return Promise.resolve({ success: true, data: { messages: claudeHistory(SESSION) } });
    return Promise.resolve({ success: false, error: "claude 백엔드는 " + cmd.type + " 미지원" });
  }
  const id = `f${++seq}`;
  return new Promise((res) => {
    const t = setTimeout(() => { pending.delete(id); res({ success: false, error: "timeout" }); }, timeoutMs);
    pending.set(id, (r) => { clearTimeout(t); res(r); });
    send({ id, ...cmd });
  });
}
// 응답 가로채기: broadcast 전에 pending 매칭
const _b = broadcast;
let claudeState = { session: null, busy: false, tools: new Map() };
function translateClaude(ev) {            // Claude Code stream-json → pi 모양 이벤트(페이지는 하나의 어휘만 안다)
  const out = [];
  if (ev.type === "system" && ev.subtype === "init") { claudeState.session = ev.session_id; out.push({ type: "claude_init", session: ev.session_id, model: ev.model }); }
  else if (ev.type === "stream_event" && ev.event) {
    const e = ev.event;
    if (!claudeState.busy) { claudeState.busy = true; out.push({ type: "agent_start" }); }
    if (e.type === "content_block_delta" && e.delta?.type === "text_delta") out.push({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: e.delta.text } });
    if (e.type === "content_block_start" && e.content_block?.type === "tool_use") { claudeState.tools.set(e.index, e.content_block); }
  }
  else if (ev.type === "assistant" && ev.message?.content) {
    for (const c of ev.message.content) if (c.type === "tool_use") out.push({ type: "tool_execution_start", toolCallId: c.id, toolName: c.name, args: c.input });
    if (ev.message.content.some((c) => c.type === "text")) out.push({ type: "message_end", message: { role: "assistant" } });
  }
  else if (ev.type === "user" && ev.message?.content) {
    for (const c of Array.isArray(ev.message.content) ? ev.message.content : []) if (c.type === "tool_result") {
      const txt = typeof c.content === "string" ? c.content : (c.content || []).map((x) => x.text || "").join("\n");
      out.push({ type: "tool_execution_end", toolCallId: c.tool_use_id, result: { content: [{ type: "text", text: txt }] } });
    }
  }
  else if (ev.type === "result") {
    if (!claudeState.busy && !ev.num_turns) return out;          // 기동 직후의 빈 result — 턴이 아니다
    claudeState.busy = false; out.push({ type: "agent_settled", cost: ev.total_cost_usd, turns: ev.num_turns });
  }
  return out;
}
function broadcastAndResolve(ev) {
  if (BACKEND === "claude") { for (const t of translateClaude(ev)) _b(t); return; }
  if (ev.type === "response" && ev.id && pending.has(ev.id)) { pending.get(ev.id)(ev); pending.delete(ev.id); } _b(ev);
}
pi.stdout.removeAllListeners("data");
pi.stdout.on("data", (d) => {
  buf += d.toString("utf8");
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i).replace(/\r$/, ""); buf = buf.slice(i + 1);
    if (!line.trim()) continue;
    try { broadcastAndResolve(JSON.parse(line)); } catch { broadcastAndResolve({ type: "raw", line }); }
  }
});

function claudeHistory(sid, max = 40) {
  try {
    const dir = join(homedir(), ".claude", "projects");
    const { readdirSync } = require("node:fs");
    let file = null;
    for (const d of readdirSync(dir)) { const f = join(dir, d, `${sid}.jsonl`); if (existsSync(f)) { file = f; break; } }
    if (!file) return [];
    const out = [];
    for (const line of readFileSync(file, "utf8").split("\n")) {
      if (!line) continue; let d; try { d = JSON.parse(line); } catch { continue; }
      if (d.isSidechain || d.isCompactSummary || !d.message) continue;
      const c = d.message.content;
      if (d.type === "user") { const t = typeof c === "string" ? c : (Array.isArray(c) && c[0]?.type === "text") ? c.map((p) => p.text || "").join("") : ""; if (t && !t.startsWith("<") && !t.startsWith("[Request")) out.push({ role: "user", content: t }); }
      else if (d.type === "assistant" && Array.isArray(c)) { const t = c.filter((p) => p.type === "text").map((p) => p.text).join(""); if (t.trim()) out.push({ role: "assistant", content: [{ type: "text", text: t }] }); }
    }
    return out.slice(-max);
  } catch { return []; }
}
function readJson(p) { try { return JSON.parse(readFileSync(p, "utf8")); } catch { return null; } }
function body(req) { return new Promise((r) => { let s = ""; req.on("data", (c) => (s += c)); req.on("end", () => { try { r(JSON.parse(s || "{}")); } catch { r({}); } }); }); }
function sidecar() {
  const st = readJson(join(ATTN, "state.json")) || {};
  const logp = join(ATTN, "log.jsonl");
  let last = null, silence = 0;
  if (existsSync(logp)) {
    const lines = readFileSync(logp, "utf8").trim().split("\n").slice(-30).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
    last = lines.filter((l) => l.kind === "judge").pop() || null; silence = lines.filter((l) => l.kind === "silence").length;
  }
  const pp = join(ATTN, "proposals.jsonl");
  let observed = [];
  if (existsSync(pp)) observed = readFileSync(pp, "utf8").trim().split("\n").slice(-3).map((l) => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
  return { block: st.block || [], updated_at: st.updated_at || null, source: (st.source || "").split("/").pop(), last, silence, observed };
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const json = (o, code = 200) => { res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" }); res.end(JSON.stringify(o)); };
  if (url.pathname === "/") { res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); return res.end(readFileSync(join(HERE, "index.html"))); }
  if (url.pathname === "/events") {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" });
    const since = Number(url.searchParams.get("since") || 0);
    for (const ev of history) if (ev._seq > since) res.write(`data: ${JSON.stringify(ev)}\n\n`);
    clients.add(res); req.on("close", () => clients.delete(res)); return;
  }
  if (url.pathname === "/prompt" && req.method === "POST") {
    const b = await body(req); if (!b.message) return json({ success: false, error: "empty" }, 400);
    return json(await ask({ type: "prompt", message: b.message, ...(b.streaming ? { streamingBehavior: b.streaming } : {}) }));
  }
  if (url.pathname === "/abort" && req.method === "POST") return json(await ask({ type: "abort" }));
  if (url.pathname === "/model" && req.method === "POST") { const b = await body(req); return json(await ask({ type: "set_model", provider: b.provider, modelId: b.modelId })); }
  if (url.pathname === "/state") return json(await ask({ type: "get_state" }));
  if (url.pathname === "/messages") return json(await ask({ type: "get_messages" }, 15000));
  if (url.pathname === "/sidecar") return json(sidecar());
  if (url.pathname === "/observe" && req.method === "POST") {         // 정훈의 «맞아»/«아니야» → 원장(green 승격 / supersede)
    const b = await body(req);
    const mcp = async (name, args) => { const r = await fetch(process.env.FORGET_MCP_URL || "http://localhost:8000/mcp/forget/http/junghunkim", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }) }); const d = await r.json(); return d.result?.content?.[0]?.text || ""; };
    if (!b.id) return json({ ok: false, error: "id" }, 400);
    if (b.verdict === "yes") return json({ ok: true, r: (await mcp("confirm_memory", { memory_id: b.id, evidence: "정훈이 얼굴에서 «맞아» (" + new Date().toISOString() + ")" })).slice(0, 200) });
    if (b.verdict === "no") return json({ ok: true, r: (await mcp("delete_memory", { memory_id: b.id })).slice(0, 200) });   // «아니야» = 정훈이 직접 잊으라는 요청
    return json({ ok: false }, 400);
  }
  if (url.pathname === "/recent_observations") {                        // 원장에서 최근 관찰(id 포함)
    try {
      const r = await fetch(process.env.FORGET_MCP_URL || "http://localhost:8000/mcp/forget/http/junghunkim", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" }, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "search_memories", arguments: { query: "[관찰·", limit: 12 } } }) });
      const d = await r.json(); const t = JSON.parse(d.result?.content?.[0]?.text || "{}");
      const items = (t.results || []).filter((m) => String(m.memory || "").startsWith("[관찰·") && !(m.trust && m.trust.light === "red")).map((m) => ({ id: m.id, text: m.memory, light: m.trust?.light || "yellow", at: m.created_at }));
      items.sort((a, b) => String(b.at).localeCompare(String(a.at)));
      return json({ items: items.slice(0, 6) });
    } catch (e) { return json({ items: [], error: String(e) }); }
  }
  res.writeHead(404); res.end();
});
server.listen(PORT, "127.0.0.1", () => console.error(`얼굴 http://127.0.0.1:${PORT}  (${BACKEND} ${PROVIDER}/${MODEL}${SESSION ? " · session " + SESSION.split("/").pop() : ""})`));
