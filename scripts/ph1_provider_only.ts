/**
 * P-H-1 팔 A 전용 미니 확장 — 로컬 프로바이더만 등록, 기억 개입 0.
 * (forget 확장을 끄면 local-qwen 프로바이더도 사라지므로, 대조군에는
 * 프로바이더만 있는 이 껍데기를 -e로 로드한다. 압축은 pi 기본 전량 요약.)
 */
export default async function providerOnly(pi: any) {
  const ENV: Record<string, string | undefined> = (globalThis as any).process?.env ?? {};
  const LLAMA = ENV.FORGET_LLAMA_URL ?? "http://127.0.0.1:18812/v1";
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
        name: "Local Qwen (provider-only, P-H-1 arm A)",
        baseUrl: LLAMA,
        apiKey: "sk-local-no-auth",
        api: "openai-completions",
        models,
      });
    }
  } catch { /* 터널 없으면 팔 A 실행 불가 — 호출측이 감지 */ }
}
