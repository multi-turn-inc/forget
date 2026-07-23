import { readFile } from "node:fs/promises";
import readline from "node:readline/promises";
import { stdin, stdout, stderr } from "node:process";
import {
  DEFAULT_MCP_URL,
  HOSTED_MCP_URL,
  ConfigError,
  applyPlan,
  buildPlan,
  detectClients,
  getClients,
  inspectClients,
  normalizeUrl,
  redactUrlForDisplay,
  scopedMcpUrl,
  validateScopeId,
  validateApiKey,
} from "./core.js";
import { doctorRemote } from "./doctor.js";
import {
  connectHooksSettings,
  disconnectHooksSettings,
  hooksDirFor,
  inspectHooks,
  installHookScripts,
  removeHookScripts,
  settingsPathFor,
} from "./hooks.js";

const CLIENT_IDS = new Set(["claude-code", "codex", "claude-desktop"]);

function help() {
  return `forget-connect — connect your AI clients to Forget memory

Usage:
  forget-connect [connect] [options]
  forget-connect status [options]
  forget-connect doctor [options]
  forget-connect disconnect [options]

Options:
  --client <ids>       Comma-separated: claude-code,codex,claude-desktop,all
  --url <url>          MCP URL (default: ${DEFAULT_MCP_URL})
  --hosted             Use the managed Forget service (legacy) instead of a local server
  --user-id <id>       Memory user scope (pair with --app-id)
  --app-id <id>        Project/app scope (pair with --user-id)
  --no-auth            Connect without a Bearer token
  --no-rules           Do not manage CLAUDE.md or AGENTS.md instruction blocks
  --no-hooks           Do not install Claude Code memory hooks (session capsule,
                       per-turn recall, conflict alerts, session capture)
  --no-migrate-enacta  Keep matching legacy config and rules blocks
  --dry-run            Show the files that would change without writing them
  --timeout <seconds>  Doctor network timeout (default: 10)
  --json               Print doctor results as JSON
  -y, --yes            Use detected clients (or all if none are detected)
  -h, --help           Show help
  -v, --version        Show version

Authentication:
  The default local server needs no token. For --hosted (legacy) set
  FORGET_API_KEY, or run interactively and paste the key when prompted.
  Keys are intentionally not accepted as command-line arguments.

Examples:
  npx forget-connect                    # local server at ${DEFAULT_MCP_URL}
  npx forget-connect --client claude-code,codex
  FORGET_API_KEY=... npx forget-connect --hosted --user-id junghunkim --app-id Mem1
  npx forget-connect status
  npx forget-connect doctor --client codex
  npx forget-connect disconnect --client codex
`;
}

function requireValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith("-")) {
    throw new ConfigError(`${flag} requires a value.`);
  }
  return value;
}

function isHostedBaseUrl(value) {
  const candidate = new URL(value);
  const hosted = new URL(HOSTED_MCP_URL);
  const candidateHost = candidate.hostname.toLowerCase().replace(/\.+$/, "");
  const hostedHost = hosted.hostname.toLowerCase().replace(/\.+$/, "");
  if (candidateHost !== hostedHost) return false;
  if (candidate.protocol !== hosted.protocol || candidate.port !== hosted.port) {
    throw new ConfigError(
      "The hosted Forget service requires HTTPS on its standard port.",
    );
  }
  // Treat every URL on the managed service origin as hosted. Matching only a
  // pathname prefix is bypassable with percent-encoded route segments that an
  // HTTP server later decodes (for example /%6Dcp or /mcp%2Fproject).
  return true;
}

export function parseArgs(argv, env = process.env) {
  const options = {
    action: "connect",
    clientValues: [],
    url: env.FORGET_MCP_URL || DEFAULT_MCP_URL,
    urlExplicit: false,
    hostedFlag: false,
    userId: env.FORGET_USER_ID?.trim() || "",
    appId: env.FORGET_APP_ID?.trim() || "",
    auth: true,
    rules: true,
    hooks: true,
    migrateLegacy: true,
    dryRun: false,
    yes: false,
    help: false,
    version: false,
    timeoutMs: 10000,
    json: false,
  };

  let actionSeen = false;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (["connect", "disconnect", "status", "doctor"].includes(arg) && !actionSeen) {
      options.action = arg;
      actionSeen = true;
    } else if (arg === "--client") {
      options.clientValues.push(requireValue(argv, index, arg));
      index += 1;
    } else if (arg.startsWith("--client=")) {
      options.clientValues.push(arg.slice("--client=".length));
    } else if (arg === "--url") {
      options.url = requireValue(argv, index, arg);
      options.urlExplicit = true;
      index += 1;
    } else if (arg.startsWith("--url=")) {
      options.url = arg.slice("--url=".length);
      options.urlExplicit = true;
    } else if (arg === "--hosted") {
      options.hostedFlag = true;
    } else if (arg === "--user-id") {
      options.userId = requireValue(argv, index, arg);
      index += 1;
    } else if (arg.startsWith("--user-id=")) {
      options.userId = arg.slice("--user-id=".length);
    } else if (arg === "--app-id") {
      options.appId = requireValue(argv, index, arg);
      index += 1;
    } else if (arg.startsWith("--app-id=")) {
      options.appId = arg.slice("--app-id=".length);
    } else if (arg === "--no-auth") {
      options.auth = false;
    } else if (arg === "--no-rules") {
      options.rules = false;
    } else if (arg === "--no-hooks") {
      options.hooks = false;
    } else if (arg === "--no-migrate-enacta") {
      options.migrateLegacy = false;
    } else if (arg === "--dry-run") {
      options.dryRun = true;
    } else if (arg === "--timeout") {
      const seconds = Number(requireValue(argv, index, arg));
      if (!Number.isFinite(seconds) || seconds < 1 || seconds > 60) {
        throw new ConfigError("--timeout must be between 1 and 60 seconds.");
      }
      options.timeoutMs = Math.round(seconds * 1000);
      index += 1;
    } else if (arg.startsWith("--timeout=")) {
      const seconds = Number(arg.slice("--timeout=".length));
      if (!Number.isFinite(seconds) || seconds < 1 || seconds > 60) {
        throw new ConfigError("--timeout must be between 1 and 60 seconds.");
      }
      options.timeoutMs = Math.round(seconds * 1000);
    } else if (arg === "--json") {
      options.json = true;
    } else if (arg === "--yes" || arg === "-y") {
      options.yes = true;
    } else if (arg === "--help" || arg === "-h") {
      options.help = true;
    } else if (arg === "--version" || arg === "-v") {
      options.version = true;
    } else {
      throw new ConfigError(`Unknown argument: ${arg}`);
    }
  }
  if (options.hostedFlag) {
    if (options.urlExplicit) {
      throw new ConfigError("--hosted and --url are mutually exclusive.");
    }
    options.url = HOSTED_MCP_URL;
  }
  options.baseUrl = normalizeUrl(options.url);
  options.hosted = isHostedBaseUrl(options.baseUrl);
  if (Boolean(options.userId) !== Boolean(options.appId)) {
    throw new ConfigError("--user-id and --app-id must be provided together.");
  }
  options.scope = options.userId
    ? {
      userId: validateScopeId(options.userId, "user_id"),
      appId: validateScopeId(options.appId, "app_id"),
    }
    : null;
  options.url = options.scope
    ? scopedMcpUrl(options.baseUrl, options.scope)
    : options.baseUrl;
  return options;
}

function requestedClientIds(values) {
  const ids = values
    .flatMap((value) => value.split(","))
    .map((value) => value.trim())
    .filter(Boolean);
  if (ids.includes("all")) return ["claude-code", "codex", "claude-desktop"];
  for (const id of ids) {
    if (!CLIENT_IDS.has(id)) {
      throw new ConfigError(`Unknown client: ${id}`);
    }
  }
  return [...new Set(ids)];
}

async function promptForClients(allClients, detected) {
  const defaults = detected.length ? detected : allClients;
  stdout.write("\nWhere should Forget be connected?\n");
  allClients.forEach((client, index) => {
    const detectedLabel = detected.includes(client) ? " (detected)" : "";
    stdout.write(`  ${index + 1}. ${client.name}${detectedLabel}\n`);
  });
  const defaultIndexes = defaults.map((client) => allClients.indexOf(client) + 1);
  const rl = readline.createInterface({ input: stdin, output: stdout });
  let answer;
  try {
    answer = await rl.question(
      `Choose comma-separated numbers [${defaultIndexes.join(",")}]: `,
    );
  } finally {
    rl.close();
  }
  const values = answer.trim() ? answer.split(",") : defaultIndexes.map(String);
  const chosen = values.map((value) => {
    const index = Number.parseInt(value.trim(), 10) - 1;
    if (!Number.isInteger(index) || index < 0 || index >= allClients.length) {
      throw new ConfigError(`Invalid client selection: ${value}`);
    }
    return allClients[index];
  });
  return [...new Set(chosen)];
}

async function selectClients(options, allClients) {
  const explicitIds = requestedClientIds(options.clientValues);
  if (explicitIds.length) {
    return explicitIds.map((id) => allClients.find((client) => client.id === id));
  }
  if (options.action === "status" || options.action === "disconnect") return allClients;

  const detected = await detectClients(allClients);
  if (options.action === "doctor") {
    if (detected.length) return detected;
    throw new ConfigError("No supported client installation was detected. Pass --client <ids> to diagnose an explicit target.");
  }
  if (options.yes) return detected.length ? detected : allClients;
  if (stdin.isTTY && stdout.isTTY) return promptForClients(allClients, detected);
  throw new ConfigError(
    "No client was selected in a non-interactive shell. Pass --client <ids> or --yes.",
  );
}

async function promptHidden(question) {
  if (!stdin.isTTY || !stdout.isTTY || typeof stdin.setRawMode !== "function") {
    throw new ConfigError("Set FORGET_API_KEY when running non-interactively.");
  }
  stdout.write(question);
  const wasRaw = Boolean(stdin.isRaw);
  stdin.setRawMode(true);
  stdin.resume();
  let value = "";
  try {
    return await new Promise((resolve, reject) => {
      const onData = (chunk) => {
        for (const byte of chunk) {
          if (byte === 3) {
            stdin.off("data", onData);
            stdout.write("\n");
            reject(new ConfigError("Cancelled."));
            return;
          }
          if (byte === 10 || byte === 13) {
            stdin.off("data", onData);
            stdout.write("\n");
            resolve(value);
            return;
          }
          if (byte === 127 || byte === 8) {
            value = value.slice(0, -1);
            continue;
          }
          value += Buffer.from([byte]).toString("utf8");
        }
      };
      stdin.on("data", onData);
    });
  } finally {
    stdin.setRawMode(wasRaw);
    stdin.pause();
  }
}

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

function isLoopbackUrl(value) {
  return LOOPBACK_HOSTS.has(new URL(value).hostname.toLowerCase());
}

async function apiKeyFor(options, env) {
  if (!["connect", "doctor"].includes(options.action) || !options.auth || options.dryRun) return "";
  const fromEnv = env.FORGET_API_KEY?.trim();
  if (fromEnv) {
    if (new URL(options.url).protocol === "https:") return validateApiKey(fromEnv);
    if (!isLoopbackUrl(options.url)) {
      throw new ConfigError(
        "Bearer authentication requires HTTPS. Use --no-auth for a local HTTP server.",
      );
    }
    // A leftover hosted key must not block the local-first default flow, and
    // a loopback target never puts the secret on the wire anyway.
    stderr.write(
      "Note: FORGET_API_KEY is set but the target is a loopback HTTP server; connecting without a token.\n",
    );
  }
  if (!options.hosted) return "";
  const prompted = (await promptHidden("Paste your Forget API key: ")).trim();
  if (!prompted) {
    throw new ConfigError("An API key is required for the hosted Forget service.");
  }
  return validateApiKey(prompted);
}

function printStatus(statuses) {
  for (const status of statuses) {
    const config = status.config ? "connected" : "not connected";
    const rules = status.rules === null
      ? ""
      : status.rules
        ? ", rules installed"
        : ", rules missing";
    stdout.write(`${status.config ? "✓" : "○"} ${status.client.name}: ${config}${rules}\n`);
  }
}

function localDoctorResults(statuses, { requireRules = true } = {}) {
  return statuses.map((status) => ({
    id: status.client.id,
    name: status.client.name,
    config: status.config,
    rules: status.rules,
    transport_valid: status.transportValid,
    url_matches: status.urlMatches,
    auth_matches: status.authMatches,
    rules_current: status.rulesCurrent,
    ok: Boolean(
      status.config
      && status.transportValid
      && status.urlMatches
      && status.authMatches
      && (
        status.rules === null
        || !requireRules
        || (status.rules && status.rulesCurrent)
      )
    ),
  }));
}

function printDoctor(result) {
  stdout.write("Forget connection doctor\n");
  if (result.hooks) {
    const hooksDetail = result.hooks.registered
      ? `registered, scripts ${result.hooks.scripts_present ? "present" : "missing"}, python3 ${result.hooks.python3 ? "ok" : "missing"}`
      : "not installed (use connect without --no-hooks)";
    stdout.write(`${result.hooks.ok ? "✓" : "✗"} Hooks: ${hooksDetail}\n`);
  }
  for (const client of result.clients) {
    const details = [
      client.config ? "config found" : "config missing",
      client.transport_valid ? "transport valid" : "transport invalid",
      client.url_matches ? "URL matches" : "URL mismatch",
      client.auth_matches ? "auth matches" : "auth mismatch",
    ];
    if (client.rules !== null) {
      details.push(
        client.rules_current
          ? "rules current"
          : client.rules
            ? "rules stale"
            : "rules missing",
      );
    }
    stdout.write(`${client.ok ? "✓" : "✗"} ${client.name}: ${details.join(", ")}\n`);
  }
  if (result.remote.skipped) {
    stdout.write("○ MCP: not checked until local configuration is fixed\n");
    return;
  }
  const scopeProbe = result.remote.scope_probe;
  if (scopeProbe?.required || scopeProbe?.requested) {
    stdout.write(
      `${scopeProbe.ok ? "✓" : "✗"} Scope: ${scopeProbe.ok ? "verified" : "not verified"}\n`,
    );
  }
  stdout.write(
    `${result.remote.ok ? "✓" : "✗"} MCP: ${result.remote.server_name} · protocol ${result.remote.protocol_version} · ${result.remote.tool_count} tools\n`,
  );
  if (result.remote.missing_tools.length) {
    stdout.write(`  missing tools: ${result.remote.missing_tools.join(", ")}\n`);
  }
}

async function version() {
  const raw = await readFile(new URL("../package.json", import.meta.url), "utf8");
  return JSON.parse(raw).version;
}

export async function run(argv = process.argv.slice(2), env = process.env) {
  const options = parseArgs(argv, env);
  if (options.help) {
    stdout.write(help());
    return;
  }
  if (options.version) {
    stdout.write(`${await version()}\n`);
    return;
  }

  const allClients = getClients({ env });
  const clients = await selectClients(options, allClients);
  if (options.action === "status") {
    printStatus(await inspectClients(clients));
    return;
  }

  const apiKey = await apiKeyFor(options, env);
  if (options.action === "doctor") {
    const local = localDoctorResults(
      await inspectClients(clients, { url: options.url, apiKey }),
      { requireRules: options.rules },
    );
    const remote = local.every((client) => client.ok)
      ? await doctorRemote({
        url: options.url,
        apiKey,
        timeoutMs: options.timeoutMs,
        clientVersion: await version(),
        expectedScope: options.scope,
        requireScope: options.hosted,
      })
      : {
        ok: false,
        skipped: true,
        reason: "local_configuration_mismatch",
        server_name: "not checked",
        server_version: "not checked",
        protocol_version: "not checked",
        session_negotiated: false,
        tool_count: 0,
        required_tools: [],
        missing_tools: [],
        scope_probe: {
          requested: Boolean(options.scope),
          required: options.hosted,
          ok: false,
          skipped: true,
        },
      };
    const hooksStatus = clients.some((client) => client.id === "claude-code")
      ? await inspectHooks({ env })
      : null;
    const result = {
      ok: local.every((client) => client.ok) && remote.ok && (hooksStatus?.ok ?? true),
      url: redactUrlForDisplay(options.url),
      scope: { configured: Boolean(options.scope) },
      clients: local,
      hooks: hooksStatus,
      remote,
    };
    if (options.json) stdout.write(`${JSON.stringify(result)}\n`);
    else printDoctor(result);
    if (!result.ok) throw new ConfigError("Doctor checks failed.");
    return result;
  }
  const changes = await buildPlan(options.action, clients, {
    url: options.url,
    apiKey,
    installInstructionRules: options.rules,
    migrateLegacy: options.migrateLegacy,
    legacyUrls: [...new Set([options.url, options.baseUrl, HOSTED_MCP_URL])],
  });

  // Claude Code is the only client with a hook system today; the hooks are
  // what make memory arrive without being asked. Disconnect always cleans
  // them up, even when the install used --no-hooks.
  const claudeCode = clients.find((client) => client.id === "claude-code");
  const manageHooks = Boolean(claudeCode)
    && (options.action === "disconnect" || options.hooks);
  const hooksDir = manageHooks ? hooksDirFor({ env }) : "";
  if (manageHooks) {
    const settingsPath = settingsPathFor({ env });
    let settingsRaw = "";
    try {
      settingsRaw = await readFile(settingsPath, "utf8");
    } catch (error) {
      if (!error || error.code !== "ENOENT") throw error;
    }
    const settingsNext = options.action === "connect"
      ? connectHooksSettings(settingsRaw, { hooksDir, url: options.url })
      : disconnectHooksSettings(settingsRaw);
    if (settingsRaw !== settingsNext) {
      changes.push({
        client: claudeCode,
        filePath: settingsPath,
        before: settingsRaw,
        after: settingsNext,
        kind: "hooks",
        sensitive: false,
        backup: options.action === "connect",
      });
    }
  }

  if (options.dryRun) {
    if (!changes.length && !manageHooks) {
      stdout.write("No changes needed.\n");
      return;
    }
    for (const change of changes) {
      stdout.write(`Would update ${change.filePath} (${change.client.name} ${change.kind})\n`);
    }
    if (manageHooks && options.action === "connect") {
      stdout.write(`Would install hook scripts into ${hooksDir}\n`);
    }
    if (manageHooks && options.action === "disconnect") {
      stdout.write(`Would remove hook scripts from ${hooksDir}\n`);
    }
    return;
  }

  const result = await applyPlan(changes);
  let hookScriptPaths = [];
  if (manageHooks) {
    hookScriptPaths = options.action === "connect"
      ? await installHookScripts(hooksDir)
      : await removeHookScripts(hooksDir);
  }
  const verb = options.action === "connect" ? "Connected" : "Disconnected";
  if (!result.changed.length && !hookScriptPaths.length) {
    stdout.write("No changes needed.\n");
  } else {
    stdout.write(`${verb} ${clients.map((client) => client.name).join(", ")}.\n`);
    for (const filePath of result.changed) stdout.write(`  updated ${filePath}\n`);
    for (const filePath of result.backups) stdout.write(`  backup  ${filePath}\n`);
    const hookVerb = options.action === "connect" ? "installed" : "removed";
    for (const filePath of hookScriptPaths) stdout.write(`  ${hookVerb} ${filePath}\n`);
  }
  if (options.action === "connect") {
    if (manageHooks) {
      stdout.write("  hooks: session capsule, per-turn recall, conflict alerts, session capture (needs python3 on PATH)\n");
    }
    if (options.hosted && !options.scope) {
      stdout.write(
        "\nWarning: hosted continuity scope is not configured. Reconnect with --user-id and --app-id before relying on cross-client recall.\n",
      );
    }
    const restarts = [...new Set(clients.map((client) => client.restart))];
    stdout.write("\nNext:\n");
    restarts.forEach((message) => stdout.write(`  - ${message}\n`));
  }
}

export async function main() {
  await run();
}
