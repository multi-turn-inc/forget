import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ASSETS = new URL("../assets/", import.meta.url);
const SHARED_SKILL = new URL("skills/memory-agent/", ASSETS);
const PLUGIN = new URL("plugins/memory-agent/", ASSETS);

async function text(relative, base) {
  return readFile(fileURLToPath(new URL(relative, base)), "utf8");
}

test("Codex and Claude manifests expose the same provider-neutral skill", async () => {
  const codex = JSON.parse(await text(".codex-plugin/plugin.json", PLUGIN));
  const claude = JSON.parse(await text(".claude-plugin/plugin.json", PLUGIN));
  assert.equal(codex.name, "memory-agent");
  assert.equal(claude.name, codex.name);
  assert.equal(claude.version, codex.version);
  assert.equal(codex.skills, "./skills/");
  assert.equal(
    await text("SKILL.md", SHARED_SKILL),
    await text("skills/memory-agent/SKILL.md", PLUGIN),
  );
  assert.equal(
    await text("agents/openai.yaml", SHARED_SKILL),
    await text("skills/memory-agent/agents/openai.yaml", PLUGIN),
  );
});

test("distributable manifests never bake in a vault URL, credential, or hook path", async () => {
  for (const manifest of [".codex-plugin/plugin.json", ".claude-plugin/plugin.json"]) {
    const body = await text(manifest, PLUGIN);
    assert.doesNotMatch(body, /https?:\/\//);
    assert.doesNotMatch(body, /FORGET_API_KEY|Authorization|hooks\.json/);
  }
});
