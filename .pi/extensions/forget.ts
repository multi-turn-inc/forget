/**
 * forget 자기 하네스 확장 — pi 껍질과 forget 기관(Python, :8000)의 접착제.
 * 헌장: docs/self-harness-design.md (개정 3). 최소 표면 원칙: 이벤트 3 + 도구 3.
 *
 *  1) before_agent_start  → 기상 재수화: 캡슐+[전망]+유언장을 시스템에 주입
 *  2) session_before_compact → 응고화가 압축을 대체 (fail-open: forget이
 *     죽어 있으면 pi 기본 압축이 그대로 돈다 — 캡슐 없는 압축 > 압축 실패)
 *  3) session_start(resume) → 연속성 계기: 기상 보고를 stderr·세션에 남긴다
 *  도구: forget_search(계기 동봉) · arm_hand · release_hand
 */
import { Type } from "typebox";

const FORGET = process.env.FORGET_URL ?? "http://localhost:8000";
const USER = process.env.FORGET_USER ?? "junghunkim";

async function forgetPost(path: string, body: unknown, timeoutMs = 20000): Promise<any> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(`${FORGET}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function forgetGet(path: string, timeoutMs = 10000): Promise<any> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(`${FORGET}${path}`, { signal: ctl.signal });
    if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/** pi 메시지를 기관의 turns[{role, content}] 규격으로 — 방어적 직렬화. */
function toTurns(messages: any[]): { role: string; content: string }[] {
  return (messages ?? []).map((m) => ({
    role: String(m?.role ?? "unknown"),
    content: typeof m?.content === "string" ? m.content : JSON.stringify(m?.content ?? ""),
  }));
}

export default async function forgetExtension(pi: any) {
  // ── 0) 로컬 프로바이더: 터널 27B (E2EE 정공로 — $0, 데이터 불출) ──────
  const LLAMA = process.env.FORGET_LLAMA_URL ?? "http://127.0.0.1:18812/v1";
  try {
    const res = await fetch(`${LLAMA}/models`, { signal: AbortSignal.timeout(4000) });
    const payload: any = await res.json();
    const models = (payload?.data ?? []).map((m: any) => ({
      id: String(m.id),
      name: String(m.id).split("/").pop(),
      reasoning: false,
      input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 24576,
      maxTokens: 4096,
    }));
    if (models.length) {
      pi.registerProvider("local-qwen", {
        name: "Local Qwen (tunnel 4090)",
        baseUrl: LLAMA,
        apiKey: "sk-local-no-auth",
        api: "openai-completions",
        models,
      });
    }
  } catch { /* 터널이 죽어 있으면 로컬 프로바이더 없이 기동 — fail-open */ }

  // ── 1) 기상 재수화 ────────────────────────────────────────────────────
  pi.on("before_agent_start", async (event: any, _ctx: any) => {
    let block = "";
    try {
      const capsule = await forgetPost("/v1/context/assemble/", {
        query: "현재 작업 맥락", filters: { user_id: USER },
        budget_tokens: 900, include_prospection: true,
        record_trace: false, disable_resume_workspace: true,
      });
      if (capsule?.context) block += `\n\n## State capsule (forget)\n${capsule.context}`;
    } catch { /* fail-open: 기관 없이도 기상은 된다 */ }
    try {
      const hands = (await forgetGet("/v1/worldmodel/hands/"))?.hands ?? [];
      if (hands.length) {
        block += "\n\n## Standing hands (inherited — re-judge each: is its 'why' still true?)";
        for (const h of hands) {
          block += `\n- (${h.kind}) ${h.what} — why: ${h.why}${h.expired ? " [EXPIRED — release or re-arm]" : ""}`;
        }
      }
    } catch { /* fail-open */ }
    if (!block) return;
    return { systemPrompt: `${event.systemPrompt ?? ""}${block}` };
  });

  // ── 2) 응고화가 압축을 대체 ──────────────────────────────────────────
  pi.on("session_before_compact", async (event: any, _ctx: any) => {
    try {
      const prep = event.preparation;
      const turns = toTurns(prep?.messagesToSummarize ?? []);
      if (!turns.length) return; // 요약할 것 없음 — pi 기본에 맡긴다
      const res = await forgetPost("/v1/harness/consolidate/", { turns }, 120000);
      if (!res?.summary) return;
      const prior = prep?.previousSummary ? `${prep.previousSummary}\n\n---\n\n` : "";
      return {
        compaction: {
          summary: `${prior}${res.summary}`,
          firstKeptEntryId: prep.firstKeptEntryId,
          tokensBefore: prep.tokensBefore,
          details: { distilled: res.distilled, by: "forget-consolidate-v0" },
        },
      };
    } catch {
      return; // fail-open: 기관이 죽으면 pi의 전량 요약이 그대로 — 압축 실패보다 낫다
    }
  });

  // ── 3) 연속성 계기의 원자료: 기상 보고 ───────────────────────────────
  pi.on("session_start", async (event: any, _ctx: any) => {
    if (event.reason !== "resume") return;
    try {
      const hands = (await forgetGet("/v1/worldmodel/hands/"))?.hands ?? [];
      pi.appendEntry("forget_wake_report", {
        woke_at: new Date().toISOString(),
        reason: event.reason,
        hands_inherited: hands.length,
      });
    } catch { /* 계기 실패가 기상을 죽이면 안 된다 */ }
  });

  // ── 도구 ──────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "forget_search",
    label: "forget search",
    description:
      "Search the forget memory ledger. Returns results plus the instrument " +
      "(top_score/strength/evidence_span_days/pool_exhausted) — use it to decide " +
      "whether to keep groping or stop.",
    parameters: Type.Object({
      query: Type.String(),
      top_k: Type.Optional(Type.Number()),
    }),
    async execute(_id: string, params: any) {
      const data = await forgetPost("/v1/memories/search/", {
        query: params.query, filters: { user_id: USER }, top_k: params.top_k ?? 5,
      });
      const lines = [`[instrument] ${JSON.stringify(data.instrument)}`];
      for (const m of data.results ?? []) {
        lines.push(`- (${m.score}) ${String(m.memory ?? "").slice(0, 200)}`);
      }
      return { content: [{ type: "text", text: lines.join("\n").slice(0, 8000) }] };
    },
  });

  pi.registerTool({
    name: "arm_hand",
    label: "arm standing hand",
    description:
      "Register a standing hand (watch|intent|resume) so the NEXT wake inherits it. " +
      "Required whenever you leave something running or unfinished. 'why' is mandatory.",
    parameters: Type.Object({
      id: Type.String(),
      kind: Type.String(),
      what: Type.String(),
      why: Type.String(),
      source_ref: Type.String(),
    }),
    async execute(_id: string, params: any) {
      const out = await forgetPost("/v1/worldmodel/hands/", params);
      return { content: [{ type: "text", text: JSON.stringify(out) }] };
    },
  });

  pi.registerTool({
    name: "release_hand",
    label: "release standing hand",
    description: "Release a standing hand with a reason (no empty releases).",
    parameters: Type.Object({ id: Type.String(), reason: Type.String() }),
    async execute(_id: string, params: any) {
      const out = await forgetPost("/v1/worldmodel/hands/release/", params);
      return { content: [{ type: "text", text: JSON.stringify(out) }] };
    },
  });
}
