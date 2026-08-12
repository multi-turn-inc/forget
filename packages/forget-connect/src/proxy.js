// Zero-config capture proxy wiring (proxy-native redesign §1).
//
// The proxy is the data plane's spine: pointing Claude Code's
// ANTHROPIC_BASE_URL at a local passthrough proxy turns every LLM call into
// an out-of-band capture, no cooperation from the agent required. The user
// never has to know it exists — connect registers a launchd KeepAlive
// service (`ai.forget.proxy`, same convention as ai.forget.server) plus a
// health watchdog, and writes the env override into ~/.claude/settings.json.
//
// Three wiring rules, in priority order:
//   (a) an existing custom base URL is *chained* as the proxy's --upstream,
//       never discarded — the user's gateway keeps seeing their traffic;
//   (b) a value that is already our proxy is a no-op;
//   (c) anything unparseable or structurally odd skips the wiring entirely
//       with a warning. Zero-config must never mean silently broken.
// Disconnect and the watchdog are symmetric: they only ever remove the value
// *we* wrote, and they restore the original the user had.

import { execFile } from "node:child_process";
import { constants as fsConstants } from "node:fs";
import { access, readFile, unlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { atomicWrite, parseJsonStrict } from "./core.js";

export const PROXY_LABEL = "ai.forget.proxy";
export const WATCHDOG_LABEL = "ai.forget.proxy.watchdog";
export const PROXY_HOST = "127.0.0.1";
export const PROXY_PORT = 8377;
export const PROXY_BASE_URL = `http://${PROXY_HOST}:${PROXY_PORT}`;
export const WATCHDOG_SCRIPT = "forget_proxy_watchdog.py";
export const WATCHDOG_INTERVAL_SECONDS = 60;

const ENV_KEY = "ANTHROPIC_BASE_URL";
const LOOPBACK_HOSTS = new Set([PROXY_HOST, "localhost", "[::1]"]);

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// --- paths -------------------------------------------------------------------

function homeFor(options = {}) {
  const env = options.env ?? process.env;
  return options.home ?? env.HOME ?? env.USERPROFILE ?? os.homedir();
}

export function forgetHomeFor(options = {}) {
  const env = options.env ?? process.env;
  return env.FORGET_HOME || path.join(homeFor(options), ".forget");
}

export function proxyDirFor(options = {}) {
  return path.join(forgetHomeFor(options), "proxy");
}

export function wiringStatePathFor(options = {}) {
  return path.join(proxyDirFor(options), "wiring.json");
}

export function watchdogStatePathFor(options = {}) {
  return path.join(proxyDirFor(options), "watchdog-state.json");
}

export function watchdogScriptPathFor(options = {}) {
  return path.join(proxyDirFor(options), WATCHDOG_SCRIPT);
}

export function launchAgentsDirFor(options = {}) {
  return path.join(homeFor(options), "Library", "LaunchAgents");
}

export function plistPathFor(label, options = {}) {
  return path.join(launchAgentsDirFor(options), `${label}.plist`);
}

// --- settings.json env wiring (pure) ----------------------------------------

export function isProxyBaseUrl(value) {
  if (typeof value !== "string") return false;
  let parsed;
  try {
    parsed = new URL(value.trim());
  } catch {
    return false;
  }
  return (
    parsed.protocol === "http:"
    && LOOPBACK_HOSTS.has(parsed.hostname.toLowerCase())
    && (parsed.port || "80") === String(PROXY_PORT)
    && (parsed.pathname === "/" || parsed.pathname === "")
    && !parsed.search
  );
}

function chainableUpstream(value) {
  let parsed;
  try {
    parsed = new URL(value.trim());
  } catch {
    return null;
  }
  if (!["http:", "https:"].includes(parsed.protocol)) return null;
  return value.trim().replace(/\/+$/, "");
}

/**
 * Decide what connect does to the settings.json env block.
 * Returns { status: "wire"|"noop"|"skip", next, upstream, original, reason }.
 * Pure: never touches the filesystem, never throws on user data.
 */
export function wireProxyEnv(raw) {
  let config;
  try {
    config = parseJsonStrict(raw, "settings.json");
  } catch {
    // (c) a settings file we cannot parse is a settings file we do not edit.
    return {
      status: "skip",
      next: raw,
      upstream: null,
      original: null,
      reason: "settings.json is not valid JSON",
    };
  }
  if (config.env !== undefined && !isObject(config.env)) {
    return {
      status: "skip",
      next: raw,
      upstream: null,
      original: null,
      reason: "the existing env value in settings.json is not a JSON object",
    };
  }
  const env = config.env ?? {};
  const current = env[ENV_KEY];
  if (current === undefined || current === "") {
    // Fresh wire: no override existed; upstream stays the proxy's default.
    env[ENV_KEY] = PROXY_BASE_URL;
    config.env = env;
    return {
      status: "wire",
      next: `${JSON.stringify(config, null, 2)}\n`,
      upstream: null,
      original: null,
      reason: "",
    };
  }
  if (isProxyBaseUrl(current)) {
    // (b) already us — nothing to do.
    return { status: "noop", next: raw, upstream: null, original: null, reason: "" };
  }
  if (typeof current !== "string") {
    return {
      status: "skip",
      next: raw,
      upstream: null,
      original: null,
      reason: `the existing ${ENV_KEY} in settings.json is not a string`,
    };
  }
  const upstream = chainableUpstream(current);
  if (!upstream) {
    return {
      status: "skip",
      next: raw,
      upstream: null,
      original: null,
      reason: `the existing ${ENV_KEY} in settings.json is not an http(s) URL`,
    };
  }
  // (a) chain the user's gateway behind the proxy and take its place.
  env[ENV_KEY] = PROXY_BASE_URL;
  config.env = env;
  return {
    status: "wire",
    next: `${JSON.stringify(config, null, 2)}\n`,
    upstream,
    original: current,
    reason: "",
  };
}

/**
 * Remove the env override — only when the current value is ours — and put
 * back whatever the user originally had. Symmetric with wireProxyEnv.
 * Returns { status: "unwired"|"noop"|"skip", next, reason }.
 */
export function unwireProxyEnv(raw, { original = null } = {}) {
  let config;
  try {
    config = parseJsonStrict(raw, "settings.json");
  } catch {
    return { status: "skip", next: raw, reason: "settings.json is not valid JSON" };
  }
  if (!isObject(config.env) || !(ENV_KEY in config.env)) {
    return { status: "noop", next: raw, reason: "" };
  }
  if (!isProxyBaseUrl(config.env[ENV_KEY])) {
    // Not our value — the user owns it now; never touch.
    return { status: "noop", next: raw, reason: "" };
  }
  if (typeof original === "string" && original) {
    config.env[ENV_KEY] = original;
  } else {
    delete config.env[ENV_KEY];
    if (!Object.keys(config.env).length) delete config.env;
  }
  return { status: "unwired", next: `${JSON.stringify(config, null, 2)}\n`, reason: "" };
}

// --- launchd plists (same convention as forget/cli.py's ai.forget.server) ---

function xmlEscape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export function proxyPlist({ execPath, upstream = null, forgetHome, logPath }) {
  const args = [execPath, "--host", PROXY_HOST, "--port", String(PROXY_PORT)];
  // --upstream only when chaining a custom gateway; the default upstream
  // stays owned by the proxy binary so it cannot drift in a stale plist.
  if (upstream) args.push("--upstream", upstream);
  const argStrings = args
    .map((arg) => `    <string>${xmlEscape(arg)}</string>`)
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${PROXY_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
${argStrings}
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>FORGET_HOME</key><string>${xmlEscape(forgetHome)}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${xmlEscape(logPath)}</string>
  <key>StandardErrorPath</key><string>${xmlEscape(logPath)}</string>
</dict>
</plist>
`;
}

export function watchdogPlist({ python3, scriptPath, forgetHome, logPath }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${WATCHDOG_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${xmlEscape(python3)}</string>
    <string>${xmlEscape(scriptPath)}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>FORGET_HOME</key><string>${xmlEscape(forgetHome)}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>${WATCHDOG_INTERVAL_SECONDS}</integer>
  <key>StandardOutPath</key><string>${xmlEscape(logPath)}</string>
  <key>StandardErrorPath</key><string>${xmlEscape(logPath)}</string>
</dict>
</plist>
`;
}

// --- wiring state (what the watchdog and disconnect need to undo us) --------

export async function readWiringState(options = {}) {
  let raw;
  try {
    raw = await readFile(wiringStatePathFor(options), "utf8");
  } catch {
    return null;
  }
  try {
    const parsed = JSON.parse(raw);
    return isObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export async function writeWiringState(options, { upstream, original }) {
  const state = {
    proxy_url: PROXY_BASE_URL,
    original_base_url: original ?? null,
    upstream: upstream ?? null,
    wired_at: new Date().toISOString(),
  };
  await atomicWrite(
    wiringStatePathFor(options),
    `${JSON.stringify(state, null, 2)}\n`,
    0o600,
  );
  return state;
}

// --- executables -------------------------------------------------------------

export async function findExecutable(name, options = {}) {
  const env = options.env ?? process.env;
  for (const dir of (env.PATH ?? "").split(path.delimiter)) {
    if (!dir) continue;
    const candidate = path.join(dir, name);
    try {
      await access(candidate, fsConstants.X_OK);
      return candidate;
    } catch {
      // keep looking
    }
  }
  return null;
}

// --- launchd side effects -----------------------------------------------------

function launchctl(args) {
  // bootout of a not-loaded service and bootstrap of an already-running one
  // both fail by design; callers decide which failures matter.
  return new Promise((resolve) => {
    execFile("launchctl", args, (error, stdout, stderr) => {
      resolve({ ok: !error, stdout: String(stdout), stderr: String(stderr) });
    });
  });
}

export function launchctlEnabled(options = {}) {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  // FORGET_PROXY_LAUNCHCTL=skip is the test seam: file wiring is exercised
  // end-to-end while the real launchd is never touched from a test run.
  return platform === "darwin" && env.FORGET_PROXY_LAUNCHCTL !== "skip";
}

function watchdogAssetPath() {
  return fileURLToPath(new URL(`../assets/proxy/${WATCHDOG_SCRIPT}`, import.meta.url));
}

/**
 * Install everything except the settings.json edit (the caller owns that
 * through the normal change plan): watchdog script, both plists, launchd
 * registration. Returns { installed, written, reason }.
 */
export async function installProxyServices(options, { upstream = null } = {}) {
  const execPath = await findExecutable("forget-proxy", options);
  if (!execPath) {
    return {
      installed: false,
      written: [],
      reason: "forget-proxy executable not found on PATH (pip install 'forget-ai[server]')",
    };
  }
  const python3 = (await findExecutable("python3", options)) ?? "/usr/bin/python3";
  const forgetHome = forgetHomeFor(options);
  const written = [];

  const scriptPath = watchdogScriptPathFor(options);
  await atomicWrite(scriptPath, await readFile(watchdogAssetPath(), "utf8"), 0o755);
  written.push(scriptPath);

  const proxyPlistPath = plistPathFor(PROXY_LABEL, options);
  await atomicWrite(
    proxyPlistPath,
    proxyPlist({ execPath, upstream, forgetHome, logPath: path.join(forgetHome, "proxy.log") }),
    0o644,
  );
  written.push(proxyPlistPath);

  const watchdogPlistPath = plistPathFor(WATCHDOG_LABEL, options);
  await atomicWrite(
    watchdogPlistPath,
    watchdogPlist({
      python3,
      scriptPath,
      forgetHome,
      logPath: path.join(forgetHome, "proxy-watchdog.log"),
    }),
    0o644,
  );
  written.push(watchdogPlistPath);

  if (launchctlEnabled(options)) {
    const domain = `gui/${typeof process.getuid === "function" ? process.getuid() : 0}`;
    for (const [label, plistFile] of [
      [PROXY_LABEL, proxyPlistPath],
      [WATCHDOG_LABEL, watchdogPlistPath],
    ]) {
      await launchctl(["bootout", `${domain}/${label}`]);
      const boot = await launchctl(["bootstrap", domain, plistFile]);
      if (!boot.ok) {
        return {
          installed: false,
          written,
          reason: `launchctl bootstrap ${label} failed: ${boot.stderr.trim() || "unknown error"}`,
        };
      }
    }
  }
  return { installed: true, written, reason: "", execPath };
}

/** Symmetric teardown: bootout, then remove every file connect created. */
export async function removeProxyServices(options = {}) {
  if (launchctlEnabled(options)) {
    const domain = `gui/${typeof process.getuid === "function" ? process.getuid() : 0}`;
    await launchctl(["bootout", `${domain}/${WATCHDOG_LABEL}`]);
    await launchctl(["bootout", `${domain}/${PROXY_LABEL}`]);
  }
  const removed = [];
  for (const target of [
    plistPathFor(WATCHDOG_LABEL, options),
    plistPathFor(PROXY_LABEL, options),
    watchdogScriptPathFor(options),
    wiringStatePathFor(options),
    watchdogStatePathFor(options),
  ]) {
    try {
      await unlink(target);
      removed.push(target);
    } catch (error) {
      if (!error || error.code !== "ENOENT") throw error;
    }
  }
  return removed;
}
