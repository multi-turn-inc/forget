// The hooks layer is the product thesis made real: memory that arrives
// without being asked. Claude Code gets four harness hooks — a session-start
// context capsule, per-turn push recall with conflict-zone alerts, and
// session capture feeding the outcome flywheel. Other clients (Codex,
// Desktop) rely on instruction rules until they grow hook systems.
//
// First rule of touching ~/.claude/settings.json: it is the user's file.
// Foreign hooks (other tools register there too) must survive connect,
// reconnect, and disconnect byte-for-byte. Ownership is recognized by the
// command path marker, never by position.

import { execFile } from "node:child_process";
import { readFile, unlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ConfigError, atomicWrite, parseJsonStrict } from "./core.js";

export const HOOK_SCRIPTS = [
  "forget_sessionstart.py",
  "forget_turnrecall.py",
  "forget_capture.py",
];

// Ownership marker: every command we install invokes a script whose path
// contains this fragment. Recognizes hand-installed variants too.
export const HOOK_MARKER = `${path.join(".forget", "hooks", "forget_")}`;

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function shellQuote(value) {
  // POSIX single-quote escaping: closes the quote, emits an escaped quote,
  // reopens. Safe for every byte except NUL.
  return `'${String(value).replaceAll("'", `'\\''`)}'`;
}

export function hooksDirFor(options = {}) {
  const env = options.env ?? process.env;
  const home = options.home ?? env.HOME ?? env.USERPROFILE ?? os.homedir();
  return path.join(home, ".forget", "hooks");
}

export function settingsPathFor(options = {}) {
  const env = options.env ?? process.env;
  const home = options.home ?? env.HOME ?? env.USERPROFILE ?? os.homedir();
  return path.join(home, ".claude", "settings.json");
}

export function hookCommand(script, { hooksDir, url }) {
  const scriptPath = path.join(hooksDir, script);
  return `FORGET_MCP_URL=${shellQuote(url)} python3 ${shellQuote(scriptPath)}`;
}

export function hookEntries({ hooksDir, url }) {
  return {
    SessionStart: {
      command: hookCommand("forget_sessionstart.py", { hooksDir, url }),
      timeout: 12,
      statusMessage: "forget: assembling context capsule",
    },
    UserPromptSubmit: {
      command: hookCommand("forget_turnrecall.py", { hooksDir, url }),
      timeout: 6,
      statusMessage: "forget: checking relevant memories",
    },
    PreCompact: {
      command: hookCommand("forget_capture.py", { hooksDir, url }),
      timeout: 10,
      statusMessage: "forget: capturing session",
    },
    SessionEnd: {
      command: hookCommand("forget_capture.py", { hooksDir, url }),
      timeout: 10,
      statusMessage: "forget: capturing session + outcome",
    },
  };
}

function ownsHook(hook) {
  return isObject(hook)
    && typeof hook.command === "string"
    && hook.command.includes(HOOK_MARKER);
}

function withoutOurHooks(groups) {
  const cleaned = [];
  for (const group of groups) {
    if (!isObject(group) || !Array.isArray(group.hooks)) {
      cleaned.push(group);
      continue;
    }
    const foreign = group.hooks.filter((hook) => !ownsHook(hook));
    if (foreign.length === group.hooks.length) {
      cleaned.push(group);
    } else if (foreign.length) {
      cleaned.push({ ...group, hooks: foreign });
    }
    // groups that held only our hooks are dropped entirely
  }
  return cleaned;
}

function validatedHooks(config, label) {
  if (config.hooks !== undefined && !isObject(config.hooks)) {
    throw new ConfigError(
      `The existing hooks value in ${label} is not a JSON object. Nothing was changed.`,
    );
  }
  const hooks = config.hooks ?? {};
  for (const [event, groups] of Object.entries(hooks)) {
    if (!Array.isArray(groups)) {
      throw new ConfigError(
        `hooks.${event} in ${label} is not an array. Nothing was changed.`,
      );
    }
  }
  return hooks;
}

export function connectHooksSettings(raw, { hooksDir, url }) {
  const config = parseJsonStrict(raw, "settings.json");
  const hooks = validatedHooks(config, "settings.json");
  for (const [event, entry] of Object.entries(hookEntries({ hooksDir, url }))) {
    const groups = withoutOurHooks(hooks[event] ?? []);
    groups.push({
      hooks: [{
        type: "command",
        command: entry.command,
        timeout: entry.timeout,
        statusMessage: entry.statusMessage,
      }],
    });
    hooks[event] = groups;
  }
  config.hooks = hooks;
  return `${JSON.stringify(config, null, 2)}\n`;
}

export function disconnectHooksSettings(raw) {
  const config = parseJsonStrict(raw, "settings.json");
  if (config.hooks === undefined) return raw;
  const hooks = validatedHooks(config, "settings.json");
  let touched = false;
  for (const [event, groups] of Object.entries(hooks)) {
    const cleaned = withoutOurHooks(groups);
    if (cleaned.length !== groups.length
      || JSON.stringify(cleaned) !== JSON.stringify(groups)) {
      touched = true;
    }
    if (cleaned.length) hooks[event] = cleaned;
    else delete hooks[event];
  }
  if (!touched) return raw;
  if (Object.keys(hooks).length) config.hooks = hooks;
  else delete config.hooks;
  return `${JSON.stringify(config, null, 2)}\n`;
}

export function hooksInstalled(raw, { hooksDir } = {}) {
  let config;
  try {
    config = parseJsonStrict(raw, "settings.json");
  } catch {
    return false;
  }
  if (!isObject(config.hooks)) return false;
  const events = Object.keys(hookEntries({ hooksDir: hooksDir ?? "", url: "http://x" }));
  return events.every((event) => {
    const groups = config.hooks[event];
    return Array.isArray(groups) && groups.some(
      (group) => isObject(group)
        && Array.isArray(group.hooks)
        && group.hooks.some((hook) => ownsHook(hook)),
    );
  });
}

function assetsDir() {
  return fileURLToPath(new URL("../assets/hooks/", import.meta.url));
}

export async function readHookAssets() {
  const dir = assetsDir();
  const assets = [];
  for (const script of HOOK_SCRIPTS) {
    assets.push({
      name: script,
      content: await readFile(path.join(dir, script), "utf8"),
    });
  }
  return assets;
}

export async function installHookScripts(hooksDir) {
  const assets = await readHookAssets();
  const written = [];
  for (const asset of assets) {
    const target = path.join(hooksDir, asset.name);
    await atomicWrite(target, asset.content, 0o755);
    written.push(target);
  }
  return written;
}

export async function inspectHooks({ env } = {}) {
  const hooksDir = hooksDirFor({ env });
  const settingsPath = settingsPathFor({ env });
  let settingsRaw = "";
  try {
    settingsRaw = await readFile(settingsPath, "utf8");
  } catch {
    settingsRaw = "";
  }
  const registered = hooksInstalled(settingsRaw, { hooksDir });
  let scriptsPresent = true;
  for (const script of HOOK_SCRIPTS) {
    try {
      await readFile(path.join(hooksDir, script), "utf8");
    } catch {
      scriptsPresent = false;
    }
  }
  const python3 = await new Promise((resolve) => {
    execFile("python3", ["--version"], (error) => resolve(!error));
  });
  return {
    registered,
    scripts_present: scriptsPresent,
    python3,
    // registered-but-broken is a failure; absent hooks are a legitimate
    // choice (--no-hooks), so they don't fail the check
    ok: !registered || (scriptsPresent && python3),
  };
}

export async function removeHookScripts(hooksDir) {
  const removed = [];
  for (const script of HOOK_SCRIPTS) {
    const target = path.join(hooksDir, script);
    try {
      await unlink(target);
      removed.push(target);
    } catch (error) {
      if (!error || error.code !== "ENOENT") throw error;
    }
  }
  return removed;
}
