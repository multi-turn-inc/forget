import forgetExtension from "../.pi/extensions/forget.ts";

const tools = new Map<string, any>();
const handlers = new Map<string, (...args: any[]) => Promise<any>>();

const pi = {
  registerProvider: () => {},
  registerTool: (tool: any) => tools.set(String(tool.name), tool),
  on: (name: string, handler: (...args: any[]) => Promise<any>) => handlers.set(name, handler),
  appendEntry: () => {},
};

await forgetExtension(pi);

const noteTool = tools.get("team_note");
if (!noteTool) throw new Error("self-harness did not register team_note");
const noteResult = await noteTool.execute("live-selfharness-check", {
  kind: "decision",
  text: "self-harness authenticated extension receipt",
  idempotency_key: "selfharness-extension-live-v1",
});
const noteText = String(noteResult?.content?.[0]?.text ?? "");
if (!noteText.includes('"author":"selfharness"')) {
  throw new Error(`team_note did not bind selfharness principal: ${noteText.slice(0, 300)}`);
}

const wake = handlers.get("before_agent_start");
if (!wake) throw new Error("self-harness did not register before_agent_start");
const wakeResult = await wake({ systemPrompt: "base" }, {});
const systemPrompt = String(wakeResult?.systemPrompt ?? "");
if (!systemPrompt.includes("Team ledger") || !systemPrompt.includes("self-harness authenticated extension receipt")) {
  throw new Error("authenticated team_read did not reach the self-harness wake capsule");
}

console.log(JSON.stringify({
  registered_team_note: true,
  bound_principal: "selfharness",
  authenticated_team_read_injected: true,
  secret_printed: false,
}));
