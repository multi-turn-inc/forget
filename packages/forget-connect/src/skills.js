import { readFile, rmdir, unlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { atomicWrite } from "./core.js";

export const MEMORY_AGENT_SKILL = "memory-agent";
export const SKILL_MARKER = "forget-connect:skill";
const SKILL_FILES = ["SKILL.md", path.join("agents", "openai.yaml")];

function assetRoot() {
  return fileURLToPath(new URL(`../assets/skills/${MEMORY_AGENT_SKILL}/`, import.meta.url));
}

function homeFor(env = process.env) {
  return env.HOME ?? env.USERPROFILE ?? os.homedir();
}

export function skillDirFor(clientId, { env = process.env } = {}) {
  const home = homeFor(env);
  if (clientId === "codex") {
    const codexHome = env.CODEX_HOME ? path.resolve(env.CODEX_HOME) : path.join(home, ".codex");
    return path.join(codexHome, "skills", MEMORY_AGENT_SKILL);
  }
  if (clientId === "claude-code") {
    return path.join(home, ".claude", "skills", MEMORY_AGENT_SKILL);
  }
  return "";
}

async function readOptional(filePath) {
  try {
    return await readFile(filePath, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

async function ownedSkill(targetDir) {
  const entry = await readOptional(path.join(targetDir, "SKILL.md"));
  return entry === null || entry.includes(SKILL_MARKER);
}

export async function installMemoryAgentSkill(clientId, { env = process.env } = {}) {
  const targetDir = skillDirFor(clientId, { env });
  if (!targetDir) return { written: [], skipped: [] };
  if (!(await ownedSkill(targetDir))) {
    return { written: [], skipped: [targetDir] };
  }
  const written = [];
  for (const relative of SKILL_FILES) {
    const source = await readFile(path.join(assetRoot(), relative), "utf8");
    const target = path.join(targetDir, relative);
    const existing = await readOptional(target);
    if (existing === source) continue;
    await atomicWrite(target, source, 0o644);
    written.push(target);
  }
  return { written, skipped: [] };
}

export async function removeMemoryAgentSkill(clientId, { env = process.env } = {}) {
  const targetDir = skillDirFor(clientId, { env });
  if (!targetDir || !(await ownedSkill(targetDir))) return { removed: [], kept: targetDir ? [targetDir] : [] };
  const removed = [];
  for (const relative of [...SKILL_FILES].reverse()) {
    const target = path.join(targetDir, relative);
    try {
      await unlink(target);
      removed.push(target);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  await rmdir(path.join(targetDir, "agents")).catch((error) => {
    if (!error || !["ENOENT", "ENOTEMPTY"].includes(error.code)) throw error;
  });
  await rmdir(targetDir).catch((error) => {
    if (!error || !["ENOENT", "ENOTEMPTY"].includes(error.code)) throw error;
  });
  return { removed, kept: [] };
}

export async function inspectMemoryAgentSkill(clientId, { env = process.env } = {}) {
  const targetDir = skillDirFor(clientId, { env });
  if (!targetDir) return { installed: false, current: false, path: "" };
  const installed = await readOptional(path.join(targetDir, "SKILL.md"));
  if (installed === null || !installed.includes(SKILL_MARKER)) {
    return { installed: false, current: false, path: targetDir };
  }
  const expected = await readFile(path.join(assetRoot(), "SKILL.md"), "utf8");
  return { installed: true, current: installed === expected, path: targetDir };
}
