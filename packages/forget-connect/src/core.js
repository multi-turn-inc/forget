import { randomBytes } from "node:crypto";
import {
  access,
  chmod,
  lstat,
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  stat,
  unlink,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export const DEFAULT_MCP_URL = "http://localhost:8000/mcp";
export const HOSTED_MCP_URL = "https://api.multi-turn.ai/mcp";
export const SERVER_KEY = "forget";
export const BACKUP_SUFFIX = ".forget-backup";

export const RULES_START = "<!-- forget:memory:start -->";
export const RULES_END = "<!-- forget:memory:end -->";
const LEGACY_RULES_START = "<!-- enacta:memory:start -->";
const LEGACY_RULES_END = "<!-- enacta:memory:end -->";
const LEGACY_SERVER_KEY = "enacta";

export const MEMORY_RULES = [
  RULES_START,
  "# Memory (Forget)",
  "You have the user's long-term memory via the `forget` MCP server.",
  "ALWAYS call `search_memories` on `forget` FIRST — before any shell command or file search — whenever the user refers to their own past decisions, preferences, plans, or anything previously discussed. Trust recent memories over old ones.",
  "At session start and on resume/continue requests, call `prepare_context_autopilot` once and treat its capsule as a suggestion (open tasks, next actions, constraints); call `get_task_state` for active work.",
  "Results may carry a `trust` label — treat it as a permission, not a decoration: green (user-stated or tool-observed) = safe to act on; yellow (agent-inferred or self-summarized) = confirm with the user before real-world action; red (superseded) = reference only; unlabeled = treat as yellow.",
  "When the user states a durable decision, preference, or lasting fact, save it with `add_memory`. Never record a planned action as completed — completion claims without evidence stay unverified.",
  "To retire a fact that turned out wrong, use `supersede_memory` and always pass `superseded_by` to link the replacement. When a true-but-unverified claim gets its receipt, use `confirm_memory` with evidence instead.",
  RULES_END,
].join("\n");

export class ConfigError extends Error {
  constructor(message) {
    super(message);
    this.name = "ConfigError";
  }
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function normalizeUrl(value) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    // The supplied URL can contain credentials or query tokens. Never reflect
    // an invalid value into terminal-visible configuration errors.
    throw new ConfigError("Invalid MCP URL.");
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new ConfigError("The MCP URL must use http:// or https://.");
  }
  if (parsed.username || parsed.password) {
    throw new ConfigError("Put credentials in FORGET_API_KEY, not in the MCP URL.");
  }
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

export function redactUrlForDisplay(value) {
  const parsed = new URL(normalizeUrl(value));
  const hadQuery = Boolean(parsed.search);
  parsed.search = "";
  const clean = parsed.toString().replace(/\/$/, "");
  return hadQuery ? `${clean}?redacted` : clean;
}

export function validateScopeId(value, label) {
  const text = String(value ?? "").trim();
  if (!text) throw new ConfigError(`${label} must not be empty.`);
  if (text.length > 200) throw new ConfigError(`${label} must be at most 200 characters.`);
  if (text === "." || text === ".." || /[\u0000-\u001f\u007f/\\?#]/.test(text)) {
    throw new ConfigError(`${label} contains unsupported path or control characters.`);
  }
  return text;
}

function encodeScopeComponent(value, label) {
  const text = validateScopeId(value, label);
  try {
    // Encode the whole identity as one path component. In particular, encoding
    // '%' prevents inputs such as "%2f" or "%2e%2e" from becoming a path
    // separator or dot segment when a downstream HTTP stack decodes the URL.
    return encodeURIComponent(text);
  } catch {
    throw new ConfigError(`${label} contains unsupported Unicode characters.`);
  }
}

export function scopedMcpUrl(baseUrl, { userId, appId }) {
  const normalized = normalizeUrl(baseUrl);
  const parsed = new URL(normalized);
  const pathname = parsed.pathname.replace(/\/+$/, "");
  if (!pathname.endsWith("/mcp")) {
    throw new ConfigError("Scoped connections require an MCP URL ending in /mcp.");
  }
  const safeUserId = encodeScopeComponent(userId, "user_id");
  const safeAppId = encodeScopeComponent(appId, "app_id");
  parsed.pathname = `${pathname}/${safeAppId}/http/${safeUserId}`;
  return parsed.toString().replace(/\/$/, "");
}

export function validateApiKey(value) {
  if (!value) return "";
  if (/[\u0000-\u001f\u007f]/.test(value)) {
    throw new ConfigError("The API key contains unsupported control characters.");
  }
  return value;
}

function tomlString(value) {
  return JSON.stringify(value);
}

export function jsonServerBlock(clientId, url, apiKey) {
  if (clientId === "claude-desktop") {
    const args = ["-y", "mcp-remote@latest", url];
    if (apiKey) args.push("--header", `Authorization: Bearer ${apiKey}`);
    return { command: "npx", args };
  }

  const block = { type: "http", url };
  if (apiKey) block.headers = { Authorization: `Bearer ${apiKey}` };
  return block;
}

export function tomlServerBlock(url, apiKey) {
  const lines = [`[mcp_servers.${SERVER_KEY}]`, `url = ${tomlString(url)}`];
  if (apiKey) {
    lines.push(
      `http_headers = { Authorization = ${tomlString(`Bearer ${apiKey}`)} }`,
    );
  }
  return lines.join("\n");
}

export function parseJsonStrict(raw, label = "JSON config") {
  if (!raw.trim()) return {};
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new ConfigError(
      `${label} is not valid JSON. Nothing was changed; repair it and retry.`,
    );
  }
  if (!isObject(parsed)) {
    throw new ConfigError(`${label} must contain a JSON object. Nothing was changed.`);
  }
  return parsed;
}

function serverUsesUrl(server, expectedUrl) {
  if (!isObject(server)) return false;
  if (typeof server.url === "string") {
    try {
      return normalizeUrl(server.url) === normalizeUrl(expectedUrl);
    } catch {
      return false;
    }
  }
  return Array.isArray(server.args) && server.args.some((arg) => {
    if (typeof arg !== "string") return false;
    try {
      return normalizeUrl(arg) === normalizeUrl(expectedUrl);
    } catch {
      return false;
    }
  });
}

function serverUsesAnyUrl(server, expectedUrls) {
  return expectedUrls.some((expectedUrl) => serverUsesUrl(server, expectedUrl));
}

export function connectJson(
  raw,
  { clientId, url, apiKey, migrateLegacy = true, legacyUrls = [url] },
) {
  const config = parseJsonStrict(raw);
  if (config.mcpServers !== undefined && !isObject(config.mcpServers)) {
    throw new ConfigError(
      "The existing mcpServers value is not a JSON object. Nothing was changed.",
    );
  }
  const servers = config.mcpServers ?? {};
  if (migrateLegacy && serverUsesAnyUrl(servers[LEGACY_SERVER_KEY], legacyUrls)) {
    delete servers[LEGACY_SERVER_KEY];
  }
  servers[SERVER_KEY] = jsonServerBlock(clientId, url, apiKey);
  config.mcpServers = servers;
  return `${JSON.stringify(config, null, 2)}\n`;
}

export function disconnectJson(raw) {
  const config = parseJsonStrict(raw);
  if (config.mcpServers === undefined) return raw;
  if (!isObject(config.mcpServers)) {
    throw new ConfigError(
      "The existing mcpServers value is not a JSON object. Nothing was changed.",
    );
  }
  if (!(SERVER_KEY in config.mcpServers)) return raw;
  delete config.mcpServers[SERVER_KEY];
  return `${JSON.stringify(config, null, 2)}\n`;
}

function sectionBounds(text, serverKey) {
  const lines = text.split(/\r?\n/);
  const header = `[mcp_servers.${serverKey}]`;
  const starts = lines
    .map((line, index) => line.trim() === header ? index : -1)
    .filter((index) => index !== -1);
  const start = starts[0] ?? -1;
  if (start === -1) return { lines, start: -1, end: -1, count: 0 };
  let end = start + 1;
  while (end < lines.length && !lines[end].trim().startsWith("[")) end += 1;
  return { lines, start, end, count: starts.length };
}

function removeTomlSection(text, serverKey) {
  const { lines, start, end, count } = sectionBounds(text, serverKey);
  if (start === -1) return { text, removed: false, section: "" };
  if (count !== 1) {
    throw new ConfigError(
      `Found more than one [mcp_servers.${serverKey}] section. Nothing was changed.`,
    );
  }
  const section = lines.slice(start, end).join("\n");
  const output = [...lines.slice(0, start), ...lines.slice(end)]
    .join("\n")
    .replace(/\n{3,}/g, "\n\n");
  return { text: output, removed: true, section };
}

function tomlSectionUsesUrl(section, expectedUrl) {
  const match = section.match(/^\s*url\s*=\s*("(?:[^"\\]|\\.)*")\s*$/m);
  if (!match) return false;
  try {
    return normalizeUrl(JSON.parse(match[1])) === normalizeUrl(expectedUrl);
  } catch {
    return false;
  }
}

export function connectToml(
  raw,
  { url, apiKey, migrateLegacy = true, legacyUrls = [url] },
) {
  let base = removeTomlSection(raw, SERVER_KEY).text;
  if (migrateLegacy) {
    const legacy = removeTomlSection(base, LEGACY_SERVER_KEY);
    if (legacy.removed && legacyUrls.some((legacyUrl) => tomlSectionUsesUrl(legacy.section, legacyUrl))) {
      base = legacy.text;
    }
  }
  base = base.replace(/\s+$/, "");
  return `${base ? `${base}\n\n` : ""}${tomlServerBlock(url, apiKey)}\n`;
}

export function disconnectToml(raw) {
  const result = removeTomlSection(raw, SERVER_KEY);
  return result.removed ? result.text.replace(/\s+$/, "") + "\n" : raw;
}

function findManagedBlock(text, startMarker, endMarker) {
  const start = text.indexOf(startMarker);
  const endOnly = text.indexOf(endMarker);
  if (start === -1) {
    if (endOnly !== -1) {
      throw new ConfigError(`Found ${endMarker} without its start marker.`);
    }
    return null;
  }
  const end = text.indexOf(endMarker, start + startMarker.length);
  if (end === -1) {
    throw new ConfigError(`Found ${startMarker} without its end marker.`);
  }
  if (text.indexOf(startMarker, start + startMarker.length) !== -1) {
    throw new ConfigError(`Found more than one ${startMarker} block.`);
  }
  return { start, end: end + endMarker.length };
}

function removeRulesBlock(text, startMarker, endMarker) {
  const bounds = findManagedBlock(text, startMarker, endMarker);
  if (!bounds) return text;
  const before = text.slice(0, bounds.start);
  const after = text.slice(bounds.end);
  // installRules appends exactly one separator newline and one final newline.
  // Recognizing that shape lets disconnect restore the pre-install bytes.
  if (after === "\n") {
    return before.endsWith("\n") ? before.slice(0, -1) : before;
  }
  if (!(before + after).trim()) return "";
  const left = before.replace(/\n+$/, "");
  const right = after.replace(/^\n+/, "");
  if (left && right) return `${left}\n\n${right}`;
  return left || right;
}

export function installRules(raw, { migrateLegacy = true } = {}) {
  let next = raw;
  if (migrateLegacy) {
    next = removeRulesBlock(next, LEGACY_RULES_START, LEGACY_RULES_END);
  }
  const bounds = findManagedBlock(next, RULES_START, RULES_END);
  if (bounds) {
    return next.slice(0, bounds.start) + MEMORY_RULES + next.slice(bounds.end);
  }
  return next ? `${next}\n${MEMORY_RULES}\n` : `${MEMORY_RULES}\n`;
}

export function removeRules(raw) {
  return removeRulesBlock(raw, RULES_START, RULES_END);
}

function desktopConfigPath(home, platform, env) {
  if (platform === "win32") {
    const appData = env.APPDATA || path.join(home, "AppData", "Roaming");
    return path.join(appData, "Claude", "claude_desktop_config.json");
  }
  if (platform === "darwin") {
    return path.join(
      home,
      "Library",
      "Application Support",
      "Claude",
      "claude_desktop_config.json",
    );
  }
  return path.join(home, ".config", "Claude", "claude_desktop_config.json");
}

export function getClients(options = {}) {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const home = options.home ?? env.HOME ?? env.USERPROFILE ?? os.homedir();
  const codexHome = env.CODEX_HOME
    ? path.resolve(env.CODEX_HOME)
    : path.join(home, ".codex");
  return [
    {
      id: "claude-code",
      name: "Claude Code",
      kind: "json",
      configPath: path.join(home, ".claude.json"),
      rulesPath: path.join(home, ".claude", "CLAUDE.md"),
      restart: "Restart every open Claude Code session.",
    },
    {
      id: "codex",
      name: "Codex",
      kind: "toml",
      configPath: path.join(codexHome, "config.toml"),
      rulesPath: path.join(codexHome, "AGENTS.md"),
      restart: "Restart every open Codex session.",
    },
    {
      id: "claude-desktop",
      name: "Claude Desktop",
      kind: "json",
      configPath: desktopConfigPath(home, platform, env),
      restart: "Quit Claude Desktop completely and reopen it.",
    },
  ];
}

async function pathExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function readOptional(filePath) {
  try {
    return await readFile(filePath, "utf8");
  } catch (error) {
    if (error && error.code === "ENOENT") return "";
    throw error;
  }
}

export async function detectClients(clients) {
  const detected = [];
  for (const client of clients) {
    const configParent = path.dirname(client.configPath);
    const rulesParent = client.rulesPath ? path.dirname(client.rulesPath) : "";
    if (
      (await pathExists(client.configPath)) ||
      (await pathExists(configParent)) ||
      (rulesParent && (await pathExists(rulesParent)))
    ) {
      detected.push(client);
    }
  }
  return detected;
}

function configConnected(client, raw) {
  if (!raw) return false;
  if (client.kind === "toml") {
    const bounds = sectionBounds(raw, SERVER_KEY);
    return bounds.start !== -1 && bounds.count === 1;
  }
  try {
    const config = parseJsonStrict(raw, client.configPath);
    return isObject(config.mcpServers) && SERVER_KEY in config.mcpServers;
  } catch {
    return false;
  }
}

function jsonAuthorizationMatches(client, server, apiKey) {
  const expected = apiKey ? `Bearer ${apiKey}` : "";
  if (client.id === "claude-desktop") {
    if (!Array.isArray(server.args)) return false;
    return expected
      ? server.args.length === 5
        && server.args[3] === "--header"
        && server.args[4] === `Authorization: ${expected}`
      : server.args.length === 3;
  }
  const headers = isObject(server.headers) ? server.headers : {};
  const entries = Object.entries(headers)
    .filter(([name]) => name.toLowerCase() === "authorization");
  const actual = entries.length === 1 && typeof entries[0][1] === "string"
    ? entries[0][1]
    : "";
  return expected
    ? entries.length === 1 && actual === expected
    : entries.length === 0;
}

function jsonTransportValid(client, server, apiKey) {
  if (!isObject(server)) return false;
  if (client.id === "claude-desktop") {
    const baseValid = server.command === "npx"
      && Array.isArray(server.args)
      && server.args[0] === "-y"
      && server.args[1] === "mcp-remote@latest"
      && typeof server.args[2] === "string";
    return apiKey
      ? baseValid
        && server.args.length === 5
        && server.args[3] === "--header"
        && typeof server.args[4] === "string"
        && /^Authorization\s*:\s*Bearer\s+/.test(server.args[4])
      : baseValid && server.args.length === 3;
  }
  return server.type === "http" && typeof server.url === "string";
}

function tomlAuthorizationMatches(section, apiKey) {
  const hasAuthorization = /\bAuthorization\s*=/.test(section);
  if (!apiKey) return !hasAuthorization;
  const match = section.match(/\bAuthorization\s*=\s*("(?:[^"\\]|\\.)*")/);
  if (!match) return false;
  try {
    return JSON.parse(match[1]) === `Bearer ${apiKey}`;
  } catch {
    return false;
  }
}

function inspectExpectedConfig(client, raw, url, apiKey) {
  if (client.kind === "toml") {
    const bounds = sectionBounds(raw, SERVER_KEY);
    if (bounds.start === -1 || bounds.count !== 1) {
      return { transportValid: false, urlMatches: false, authMatches: false };
    }
    const section = bounds.lines.slice(bounds.start, bounds.end).join("\n");
    return {
      transportValid: tomlSectionUsesUrl(section, url),
      urlMatches: tomlSectionUsesUrl(section, url),
      authMatches: tomlAuthorizationMatches(section, apiKey),
    };
  }
  try {
    const config = parseJsonStrict(raw, client.configPath);
    const server = isObject(config.mcpServers) ? config.mcpServers[SERVER_KEY] : null;
    const urlMatches = client.id === "claude-desktop"
      ? Array.isArray(server?.args)
        && typeof server.args[2] === "string"
        && serverUsesUrl({ url: server.args[2] }, url)
      : serverUsesUrl(server, url);
    return {
      transportValid: jsonTransportValid(client, server, apiKey),
      urlMatches,
      authMatches: isObject(server) && jsonAuthorizationMatches(client, server, apiKey),
    };
  } catch {
    return { transportValid: false, urlMatches: false, authMatches: false };
  }
}

function rulesConnected(raw) {
  try {
    return Boolean(findManagedBlock(raw, RULES_START, RULES_END));
  } catch {
    return false;
  }
}

function rulesCurrent(raw) {
  try {
    const bounds = findManagedBlock(raw, RULES_START, RULES_END);
    return Boolean(bounds && raw.slice(bounds.start, bounds.end) === MEMORY_RULES);
  } catch {
    return false;
  }
}

export async function inspectClients(clients, { url = "", apiKey = "" } = {}) {
  const expectedUrl = url ? normalizeUrl(url) : "";
  return Promise.all(
    clients.map(async (client) => {
      const configRaw = await readOptional(client.configPath);
      const rulesRaw = client.rulesPath ? await readOptional(client.rulesPath) : "";
      const expected = expectedUrl
        ? inspectExpectedConfig(client, configRaw, expectedUrl, apiKey)
        : { transportValid: null, urlMatches: null, authMatches: null };
      return {
        client,
        config: configConnected(client, configRaw),
        rules: client.rulesPath ? rulesConnected(rulesRaw) : null,
        rulesCurrent: client.rulesPath ? rulesCurrent(rulesRaw) : null,
        ...expected,
      };
    }),
  );
}

function addChange(changes, client, filePath, before, after, kind, sensitive, backup) {
  if (before === after) return;
  changes.push({ client, filePath, before, after, kind, sensitive, backup });
}

export async function buildPlan(
  action,
  clients,
  {
    url = DEFAULT_MCP_URL,
    apiKey = "",
    installInstructionRules = true,
    migrateLegacy = true,
    legacyUrls = [url],
  } = {},
) {
  if (!['connect', 'disconnect'].includes(action)) {
    throw new ConfigError(`Unsupported action: ${action}`);
  }
  const changes = [];
  for (const client of clients) {
    const configRaw = await readOptional(client.configPath);
    let configNext;
    if (client.kind === "toml") {
      configNext = action === "connect"
        ? connectToml(configRaw, { url, apiKey, migrateLegacy, legacyUrls })
        : disconnectToml(configRaw);
    } else {
      configNext = action === "connect"
        ? connectJson(configRaw, {
          clientId: client.id,
          url,
          apiKey,
          migrateLegacy,
          legacyUrls,
        })
        : disconnectJson(configRaw);
    }
    addChange(
      changes,
      client,
      client.configPath,
      configRaw,
      configNext,
      "config",
      true,
      action === "connect",
    );

    if (client.rulesPath && installInstructionRules) {
      const rulesRaw = await readOptional(client.rulesPath);
      const rulesNext = action === "connect"
        ? installRules(rulesRaw, { migrateLegacy })
        : removeRules(rulesRaw);
      addChange(
        changes,
        client,
        client.rulesPath,
        rulesRaw,
        rulesNext,
        "rules",
        false,
        action === "connect",
      );
    }
  }
  return changes;
}

async function resolvedWritePath(filePath) {
  try {
    const info = await lstat(filePath);
    return info.isSymbolicLink() ? await realpath(filePath) : filePath;
  } catch (error) {
    if (error && error.code === "ENOENT") return filePath;
    throw error;
  }
}

async function sourceMode(filePath, fallback) {
  try {
    return (await stat(filePath)).mode & 0o777;
  } catch (error) {
    if (error && error.code === "ENOENT") return fallback;
    throw error;
  }
}

export async function atomicWrite(filePath, content, mode) {
  const target = await resolvedWritePath(filePath);
  await mkdir(path.dirname(target), { recursive: true });
  const temp = `${target}.forget-connect-${process.pid}-${randomBytes(5).toString("hex")}`;
  const handle = await open(temp, "wx", mode);
  try {
    await handle.writeFile(content, "utf8");
    await handle.sync();
  } catch (error) {
    await handle.close();
    await unlink(temp).catch(() => {});
    throw error;
  } finally {
    if (handle.fd !== -1) await handle.close();
  }
  try {
    await rename(temp, target);
    await chmod(target, mode);
  } catch (error) {
    await unlink(temp).catch(() => {});
    throw error;
  }
}

async function backupOnce(filePath, raw) {
  if (!raw) return null;
  const backupPath = `${filePath}${BACKUP_SUFFIX}`;
  if (await pathExists(backupPath)) return null;
  await atomicWrite(backupPath, raw, 0o600);
  return backupPath;
}

export async function applyPlan(changes, { dryRun = false } = {}) {
  if (dryRun) return { changed: [], backups: [] };
  const changed = [];
  const backups = [];
  for (const change of changes) {
    const backup = change.backup
      ? await backupOnce(change.filePath, change.before)
      : null;
    if (backup) backups.push(backup);
    const mode = change.sensitive
      ? 0o600
      : await sourceMode(change.filePath, 0o644);
    await atomicWrite(change.filePath, change.after, mode);
    changed.push(change.filePath);
  }
  return { changed, backups };
}
