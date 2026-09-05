import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  inspectMemoryAgentSkill,
  installMemoryAgentSkill,
  removeMemoryAgentSkill,
  skillDirFor,
} from "../src/skills.js";


test("one shared skill installs into Codex and Claude and removes cleanly", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-skills-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const env = { HOME: home, CODEX_HOME: path.join(home, ".codex") };

  const codex = await installMemoryAgentSkill("codex", { env });
  const claude = await installMemoryAgentSkill("claude-code", { env });
  assert.equal(codex.written.length, 2);
  assert.equal(claude.written.length, 2);
  const codexText = await readFile(path.join(skillDirFor("codex", { env }), "SKILL.md"), "utf8");
  const claudeText = await readFile(path.join(skillDirFor("claude-code", { env }), "SKILL.md"), "utf8");
  assert.equal(codexText, claudeText);
  assert.match(codexText, /catalog_search/);
  assert.match(codexText, /grant_create/);
  assert.match(codexText, /receipt_verify/);
  assert.deepEqual(await inspectMemoryAgentSkill("codex", { env }), {
    installed: true,
    current: true,
    path: skillDirFor("codex", { env }),
  });

  assert.equal((await removeMemoryAgentSkill("codex", { env })).removed.length, 2);
  assert.equal((await removeMemoryAgentSkill("claude-code", { env })).removed.length, 2);
  assert.equal((await inspectMemoryAgentSkill("codex", { env })).installed, false);
  assert.equal((await inspectMemoryAgentSkill("claude-code", { env })).installed, false);
});


test("installer never overwrites or removes an unowned skill", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-foreign-skill-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const env = { HOME: home, CODEX_HOME: path.join(home, ".codex") };
  const dir = skillDirFor("codex", { env });
  await mkdir(dir, { recursive: true });
  await writeFile(path.join(dir, "SKILL.md"), "---\nname: memory-agent\n---\nuser owned\n");

  const installed = await installMemoryAgentSkill("codex", { env });
  assert.equal(installed.written.length, 0);
  assert.deepEqual(installed.skipped, [dir]);
  const removed = await removeMemoryAgentSkill("codex", { env });
  assert.equal(removed.removed.length, 0);
  assert.deepEqual(removed.kept, [dir]);
  assert.equal(await readFile(path.join(dir, "SKILL.md"), "utf8"), "---\nname: memory-agent\n---\nuser owned\n");
});
