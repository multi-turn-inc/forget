// The hooks layer is the product thesis made real: memory that arrives
// without being asked. Claude Code and Codex share the same scripts and
// ownership rules, while each receives only lifecycle events its client
// actually emits. Desktop continues to rely on instruction rules.
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
  "forget_bstate.py", // compact structured working state shared by both clients
  "forget_project.py", // shared project-boundary detection (imported by the others)
  "forget_projecttag.py", // PreToolUse: stamps memory/task writes with the cwd's project
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
  if (options.clientId === "codex") {
    return path.join(env.CODEX_HOME ?? path.join(home, ".codex"), "hooks.json");
  }
  return path.join(home, ".claude", "settings.json");
}

export function hookCommand(script, { hooksDir, url }) {
  const scriptPath = path.join(hooksDir, script);
  return `FORGET_MCP_URL=${shellQuote(url)} python3 ${shellQuote(scriptPath)}`;
}

export function hookEntries({ hooksDir, url, clientId = "claude-code" }) {
  const shared = {
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
  };
  if (clientId === "codex") {
    return {
      ...shared,
      SessionStart: {
        ...shared.SessionStart,
        matcher: "startup|resume|compact",
      },
      Stop: {
        command: hookCommand("forget_capture.py", { hooksDir, url }),
        timeout: 10,
        statusMessage: "forget: capturing turn + outcome",
      },
    };
  }
  return {
    ...shared,
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
    PreToolUse: {
      command: hookCommand("forget_projecttag.py", { hooksDir, url }),
      timeout: 5,
      statusMessage: "forget: tagging project scope",
      matcher: "mcp__forget__add_memory|mcp__forget__record_task_state",
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

export function connectHooksSettings(raw, { hooksDir, url, clientId = "claude-code" }) {
  const label = clientId === "codex" ? "hooks.json" : "settings.json";
  const config = parseJsonStrict(raw, label);
  const hooks = validatedHooks(config, label);
  for (const [event, entry] of Object.entries(hookEntries({ hooksDir, url, clientId }))) {
    const groups = withoutOurHooks(hooks[event] ?? []);
    const group = {
      hooks: [{
        type: "command",
        command: entry.command,
        timeout: entry.timeout,
        statusMessage: entry.statusMessage,
      }],
    };
    if (entry.matcher) group.matcher = entry.matcher;
    groups.push(group);
    hooks[event] = groups;
  }
  config.hooks = hooks;
  return `${JSON.stringify(config, null, 2)}\n`;
}

export function disconnectHooksSettings(raw, { clientId = "claude-code" } = {}) {
  const label = clientId === "codex" ? "hooks.json" : "settings.json";
  const config = parseJsonStrict(raw, label);
  if (config.hooks === undefined) return raw;
  const hooks = validatedHooks(config, label);
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

export function hooksInstalled(raw, { hooksDir, clientId = "claude-code" } = {}) {
  let config;
  try {
    config = parseJsonStrict(raw, clientId === "codex" ? "hooks.json" : "settings.json");
  } catch {
    return false;
  }
  if (!isObject(config.hooks)) return false;
  const events = Object.keys(hookEntries({
    hooksDir: hooksDir ?? "",
    url: "http://x",
    clientId,
  }));
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

export async function inspectHooks({ env, clientId = "claude-code" } = {}) {
  const hooksDir = hooksDirFor({ env });
  const settingsPath = settingsPathFor({ env, clientId });
  let settingsRaw = "";
  try {
    settingsRaw = await readFile(settingsPath, "utf8");
  } catch {
    settingsRaw = "";
  }
  const registered = hooksInstalled(settingsRaw, { hooksDir, clientId });
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

// --- slash commands (/forget, /forget-settings) — the dial in the editor ---
//
// Same file-ownership rule as settings.json: a command file without our
// marker is the user's (hand-written or edited with the marker removed) and
// is never touched — not on connect, not on disconnect.

export const COMMAND_ASSETS = ["forget.md", "forget-settings.md"];
export const COMMAND_MARKER = "forget-connect:command";

export function commandsDirFor(options = {}) {
  const env = options.env ?? process.env;
  const home = options.home ?? env.HOME ?? env.USERPROFILE ?? os.homedir();
  return path.join(home, ".claude", "commands");
}

function commandAssetsDir() {
  return fileURLToPath(new URL("../assets/commands/", import.meta.url));
}

export async function installCommandAssets(commandsDir) {
  const written = [];
  for (const name of COMMAND_ASSETS) {
    const target = path.join(commandsDir, name);
    let existing = null;
    try {
      existing = await readFile(target, "utf8");
    } catch (error) {
      if (!error || error.code !== "ENOENT") throw error;
    }
    if (existing !== null && !existing.includes(COMMAND_MARKER)) continue;
    const content = await readFile(path.join(commandAssetsDir(), name), "utf8");
    if (existing === content) continue;
    await atomicWrite(target, content, 0o644);
    written.push(target);
  }
  return written;
}

export async function removeCommandAssets(commandsDir) {
  const removed = [];
  for (const name of COMMAND_ASSETS) {
    const target = path.join(commandsDir, name);
    try {
      const existing = await readFile(target, "utf8");
      if (!existing.includes(COMMAND_MARKER)) continue;
      await unlink(target);
      removed.push(target);
    } catch (error) {
      if (!error || error.code !== "ENOENT") throw error;
    }
  }
  return removed;
}
