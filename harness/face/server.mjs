// 얼굴 — pi(rpc 모드)를 뒤에 두고 브라우저로 대화한다 (2026-09-07, 정훈 «pi 인터페이스 너무 구려»).
// 사용: node harness/face/server.mjs [--session <jsonl>] [--provider anthropic] [--model claude-fable-5-1] [--port 8030]
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFileSync, existsSync } from "node:fs";
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

const piArgs = ["--mode", "rpc", "--provider", PROVIDER, "--model", MODEL, "--approve"];
if (SESSION) piArgs.push("--session", SESSION); else piArgs.push("--name", `얼굴 ${new Date().toISOString().slice(5, 16).replace("T", " ")}`);
const pi = spawn("pi", piArgs, { cwd: process.cwd(), stdio: ["pipe", "pipe", "pipe"], env: process.env });
pi.stderr.on("data", (d) => process.stderr.write(`[pi] ${d}`));
pi.on("exit", (c) => { console.error(`pi exited ${c}`); process.exit(c ?? 0); });

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
  const id = `f${++seq}`;
  return new Promise((res) => {
    const t = setTimeout(() => { pending.delete(id); res({ success: false, error: "timeout" }); }, timeoutMs);
    pending.set(id, (r) => { clearTimeout(t); res(r); });
    send({ id, ...cmd });
  });
}
// 응답 가로채기: broadcast 전에 pending 매칭
const _b = broadcast;
function broadcastAndResolve(ev) { if (ev.type === "response" && ev.id && pending.has(ev.id)) { pending.get(ev.id)(ev); pending.delete(ev.id); } _b(ev); }
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
  res.writeHead(404); res.end();
});
server.listen(PORT, "127.0.0.1", () => console.error(`얼굴 http://127.0.0.1:${PORT}  (pi ${PROVIDER}/${MODEL}${SESSION ? " · session " + SESSION.split("/").pop() : ""})`));
