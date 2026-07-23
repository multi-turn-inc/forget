import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  ConfigError,
  MEMORY_RULES,
  RULES_START,
  applyPlan,
  buildPlan,
  connectJson,
  connectToml,
  disconnectJson,
  disconnectToml,
  getClients,
  inspectClients,
  installRules,
  normalizeUrl,
  redactUrlForDisplay,
  removeRules,
  scopedMcpUrl,
  validateScopeId,
} from "../src/core.js";

const URL = "https://api.multi-turn.ai/mcp";

test("JSON connect preserves other state and is idempotent", () => {
  const input = JSON.stringify({
    theme: "dark",
    mcpServers: { other: { command: "other-server" } },
  });
  const once = connectJson(input, {
    clientId: "claude-code",
    url: URL,
    apiKey: "secret-key",
  });
  const parsed = JSON.parse(once);
  assert.equal(parsed.theme, "dark");
  assert.deepEqual(parsed.mcpServers.other, { command: "other-server" });
  assert.deepEqual(parsed.mcpServers.forget, {
    type: "http",
    url: URL,
    headers: { Authorization: "Bearer secret-key" },
  });
  assert.equal(
    connectJson(once, {
      clientId: "claude-code",
      url: URL,
      apiKey: "secret-key",
    }),
    once,
  );
});

test("JSON connect upgrades only a matching legacy entry", () => {
  const matching = connectJson(
    JSON.stringify({
      mcpServers: {
        enacta: { type: "http", url: URL },
        other: { url: "https://example.test/mcp" },
      },
    }),
    { clientId: "claude-code", url: URL, apiKey: "" },
  );
  const matchingServers = JSON.parse(matching).mcpServers;
  assert.equal("enacta" in matchingServers, false);
  assert.equal("forget" in matchingServers, true);
  assert.equal("other" in matchingServers, true);

  const unrelated = connectJson(
    JSON.stringify({ mcpServers: { enacta: { url: "https://example.test/mcp" } } }),
    { clientId: "claude-code", url: URL, apiKey: "" },
  );
  assert.equal("enacta" in JSON.parse(unrelated).mcpServers, true);
});

test("scoped MCP URLs validate and encode user and app identity", () => {
  assert.equal(
    scopedMcpUrl(URL, { userId: "user+one@example.test", appId: "Project One" }),
    "https://api.multi-turn.ai/mcp/Project%20One/http/user%2Bone%40example.test",
  );
  assert.equal(
    scopedMcpUrl(URL, { userId: "%2Fadmin", appId: "%2e%2e" }),
    "https://api.multi-turn.ai/mcp/%252e%252e/http/%252Fadmin",
  );
  assert.equal(
    scopedMcpUrl(URL, { userId: "사용자", appId: "프로젝트" }),
    "https://api.multi-turn.ai/mcp/%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8/http/%EC%82%AC%EC%9A%A9%EC%9E%90",
  );
  assert.equal(validateScopeId("  Mem1  ", "app_id"), "Mem1");
  assert.throws(
    () => scopedMcpUrl("https://example.test/custom", { userId: "u", appId: "a" }),
    /ending in \/mcp/,
  );
  assert.throws(
    () => scopedMcpUrl(URL, { userId: "../escape", appId: "a" }),
    /unsupported path/,
  );
  assert.throws(
    () => scopedMcpUrl(URL, { userId: "\ud800", appId: "a" }),
    /unsupported Unicode/,
  );
});

test("scoped connect migrates a matching legacy bare endpoint", () => {
  const scoped = scopedMcpUrl(URL, { userId: "junghunkim", appId: "Mem1" });
  const json = connectJson(
    JSON.stringify({ mcpServers: { enacta: { type: "http", url: URL } } }),
    {
      clientId: "claude-code",
      url: scoped,
      apiKey: "secret-key",
      legacyUrls: [scoped, URL],
    },
  );
  assert.equal("enacta" in JSON.parse(json).mcpServers, false);
  assert.equal(JSON.parse(json).mcpServers.forget.url, scoped);

  const toml = connectToml(
    `[mcp_servers.enacta]\nurl = ${JSON.stringify(URL)}\n`,
    { url: scoped, apiKey: "secret-key", legacyUrls: [scoped, URL] },
  );
  assert.doesNotMatch(toml, /mcp_servers\.enacta/);
  assert.match(toml, new RegExp(scoped.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
});

test("invalid JSON and an invalid mcpServers shape fail closed", () => {
  assert.throws(
    () => connectJson("{oops", { clientId: "claude-code", url: URL, apiKey: "" }),
    ConfigError,
  );
  assert.throws(
    () => connectJson('{"mcpServers":[]}', {
      clientId: "claude-code",
      url: URL,
      apiKey: "",
    }),
    ConfigError,
  );
});

test("TOML connect preserves other sections, upgrades legacy, and disconnects cleanly", () => {
  const input = [
    'model = "gpt-5"',
    "",
    "[mcp_servers.other]",
    'url = "https://example.test/mcp"',
    "",
    "[mcp_servers.enacta]",
    `url = "${URL}"`,
    "http_headers = { Authorization = \"Bearer old\" }",
    "",
  ].join("\n");
  const connected = connectToml(input, { url: URL, apiKey: "new-key" });
  assert.match(connected, /\[mcp_servers\.other\]/);
  assert.doesNotMatch(connected, /\[mcp_servers\.enacta\]/);
  assert.match(connected, /\[mcp_servers\.forget\]/);
  assert.match(connected, /Bearer new-key/);
  assert.equal(connectToml(connected, { url: URL, apiKey: "new-key" }), connected);

  const disconnected = disconnectToml(connected);
  assert.match(disconnected, /\[mcp_servers\.other\]/);
  assert.doesNotMatch(disconnected, /\[mcp_servers\.forget\]/);
});

test("managed rules preserve user text, upgrade legacy, and remove cleanly", () => {
  const legacy = [
    "# Personal rules",
    "",
    "Keep this paragraph.",
    "",
    "<!-- enacta:memory:start -->",
    `# Memory (${"En"}acta)`,
    "old rule",
    "<!-- enacta:memory:end -->",
    "",
    "Tail text.",
    "",
  ].join("\n");
  const installed = installRules(legacy);
  assert.match(installed, /# Personal rules/);
  assert.match(installed, /Keep this paragraph\./);
  assert.match(installed, /Tail text\./);
  assert.doesNotMatch(installed, /enacta:memory/);
  assert.match(installed, new RegExp(RULES_START.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.equal(installRules(installed), installed);
  assert.doesNotMatch(removeRules(installed), /forget:memory/);
  assert.match(removeRules(installed), /Keep this paragraph\./);
});

test("doctor inspection verifies transport, URL, auth, and the full rules body", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-inspect-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const apiKey = "inspection-secret-must-not-print";
  const clients = getClients({
    home,
    platform: "darwin",
    env: { CODEX_HOME: path.join(home, ".codex") },
  });

  await applyPlan(await buildPlan("connect", clients, { url: URL, apiKey }));
  const healthy = await inspectClients(clients, { url: URL, apiKey });
  for (const status of healthy) {
    assert.equal(status.config, true);
    assert.equal(status.transportValid, true);
    assert.equal(status.urlMatches, true);
    assert.equal(status.authMatches, true);
    assert.equal(status.rulesCurrent, status.client.rulesPath ? true : null);
  }
  assert.equal(JSON.stringify(healthy).includes(apiKey), false);

  const claude = clients.find((client) => client.id === "claude-code");
  await writeFile(
    claude.configPath,
    connectJson("{}", {
      clientId: "claude-code",
      url: "https://wrong.example/mcp",
      apiKey: "wrong-key",
    }),
  );
  await writeFile(claude.rulesPath, MEMORY_RULES.replace("Trust recent", "Trust every"));
  const mismatched = (await inspectClients([claude], { url: URL, apiKey }))[0];
  assert.equal(mismatched.config, true);
  assert.equal(mismatched.transportValid, true);
  assert.equal(mismatched.urlMatches, false);
  assert.equal(mismatched.authMatches, false);
  assert.equal(mismatched.rules, true);
  assert.equal(mismatched.rulesCurrent, false);

  await writeFile(
    claude.configPath,
    connectJson("{}", { clientId: "claude-code", url: URL, apiKey: "" }),
  );
  const missingAuth = (await inspectClients([claude], { url: URL, apiKey }))[0];
  assert.equal(missingAuth.urlMatches, true);
  assert.equal(missingAuth.authMatches, false);

  await writeFile(claude.configPath, JSON.stringify({
    mcpServers: {
      forget: {
        type: "http",
        url: URL,
        headers: {
          Authorization: `Bearer ${apiKey}`,
          authorization: "Bearer conflicting-key",
        },
      },
    },
  }));
  const conflictingAuth = (await inspectClients([claude], { url: URL, apiKey }))[0];
  assert.equal(conflictingAuth.transportValid, true);
  assert.equal(conflictingAuth.urlMatches, true);
  assert.equal(conflictingAuth.authMatches, false);

  const desktop = clients.find((client) => client.id === "claude-desktop");
  await writeFile(desktop.configPath, JSON.stringify({
    mcpServers: {
      forget: {
        command: "npx",
        args: [
          "-y",
          "mcp-remote@latest",
          "https://wrong.example/mcp",
          URL,
          `Authorization: Bearer ${apiKey}`,
        ],
      },
    },
  }));
  const tamperedDesktop = (await inspectClients([desktop], { url: URL, apiKey }))[0];
  assert.equal(tamperedDesktop.transportValid, false);
  assert.equal(tamperedDesktop.urlMatches, false);
  assert.equal(tamperedDesktop.authMatches, false);

  const codex = clients.find((client) => client.id === "codex");
  const validCodex = await readFile(codex.configPath, "utf8");
  const duplicateCodex = `${validCodex}\n[mcp_servers.forget]\nurl = "https://wrong.example/mcp"\n`;
  await writeFile(codex.configPath, duplicateCodex);
  const duplicateStatus = (await inspectClients([codex], { url: URL, apiKey }))[0];
  assert.equal(duplicateStatus.config, false);
  assert.equal(duplicateStatus.transportValid, false);
  assert.equal(duplicateStatus.urlMatches, false);
  assert.equal(duplicateStatus.authMatches, false);
  assert.throws(
    () => connectToml(duplicateCodex, { url: URL, apiKey }),
    /more than one \[mcp_servers\.forget\]/,
  );
  assert.throws(
    () => disconnectToml(duplicateCodex),
    /more than one \[mcp_servers\.forget\]/,
  );
});

test("display URLs redact query values", () => {
  const display = redactUrlForDisplay(`${URL}?token=query-secret&mode=doctor`);
  assert.equal(display, `${URL}?redacted`);
  assert.doesNotMatch(display, /query-secret|mode=doctor/);
});

test("invalid URL errors never reflect query credentials", () => {
  const secret = "invalid-url-query-secret";
  assert.throws(
    () => normalizeUrl(`https://[invalid.test/mcp?token=${secret}`),
    (error) => error instanceof ConfigError
      && error.message === "Invalid MCP URL."
      && !error.message.includes(secret),
  );
});

test("a damaged rule marker fails closed", () => {
  assert.throws(() => installRules(`${RULES_START}\nmissing end\n`), ConfigError);
});

test("plan and apply create one-time backups and private config files", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-core-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const clients = getClients({ home, platform: "darwin", env: {} });
  const claude = clients.find((client) => client.id === "claude-code");
  await mkdir(path.dirname(claude.rulesPath), { recursive: true });
  const originalConfig = '{"mcpServers":{"other":{"command":"other"}}}\n';
  const originalRules = "# My rules\n";
  await writeFile(claude.configPath, originalConfig, { mode: 0o644 });
  await writeFile(claude.rulesPath, originalRules, { mode: 0o644 });

  const firstPlan = await buildPlan("connect", [claude], {
    url: URL,
    apiKey: "secret-key",
  });
  const first = await applyPlan(firstPlan);
  assert.equal(first.changed.length, 2);
  assert.equal(first.backups.length, 2);
  assert.equal(await readFile(`${claude.configPath}.forget-backup`, "utf8"), originalConfig);
  assert.equal(await readFile(`${claude.rulesPath}.forget-backup`, "utf8"), originalRules);
  assert.equal((await stat(claude.configPath)).mode & 0o777, 0o600);
  assert.match(await readFile(claude.rulesPath, "utf8"), /# My rules/);
  assert.match(await readFile(claude.rulesPath, "utf8"), /# Memory \(Forget\)/);

  const secondPlan = await buildPlan("connect", [claude], {
    url: URL,
    apiKey: "secret-key",
  });
  assert.equal(secondPlan.length, 0);

  const disconnectPlan = await buildPlan("disconnect", [claude]);
  await applyPlan(disconnectPlan);
  const disconnected = JSON.parse(await readFile(claude.configPath, "utf8"));
  assert.deepEqual(disconnected.mcpServers.other, { command: "other" });
  assert.equal("forget" in disconnected.mcpServers, false);
  assert.equal(await readFile(claude.rulesPath, "utf8"), originalRules);
});

test("disconnect JSON keeps unrelated servers", () => {
  const raw = JSON.stringify({
    mcpServers: {
      other: { command: "other" },
      forget: { type: "http", url: URL },
    },
  });
  assert.deepEqual(JSON.parse(disconnectJson(raw)).mcpServers, {
    other: { command: "other" },
  });
});

test("disconnect never creates a new backup containing the managed credential", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-no-backup-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const codex = getClients({ home, platform: "darwin", env: {} })
    .find((client) => client.id === "codex");
  await applyPlan(await buildPlan("connect", [codex], {
    url: URL,
    apiKey: "must-not-enter-a-disconnect-backup",
  }));
  await applyPlan(await buildPlan("disconnect", [codex]));
  await assert.rejects(readFile(`${codex.configPath}.forget-backup`), /ENOENT/);
  await assert.rejects(readFile(`${codex.rulesPath}.forget-backup`), /ENOENT/);
});

test("exported rule text teaches the required first-memory behavior", () => {
  assert.match(MEMORY_RULES, /ALWAYS call `search_memories` on `forget` FIRST/);
  assert.match(MEMORY_RULES, /call `prepare_context_autopilot` once/);
  assert.match(MEMORY_RULES, /call `get_task_state` for active work/);
  assert.match(MEMORY_RULES, /save it with `add_memory`/);
  // the traffic-light permission contract must travel with every client
  assert.match(MEMORY_RULES, /green \(user-stated or tool-observed\) = safe to act on/);
  assert.match(MEMORY_RULES, /unlabeled = treat as yellow/);
  // and so must the ledger's closing semantics
  assert.match(MEMORY_RULES, /`supersede_memory` and always pass `superseded_by`/);
  assert.match(MEMORY_RULES, /`confirm_memory` with evidence/);
  assert.match(MEMORY_RULES, /Never record a planned action as completed/);
});

test("scopeFromUrl recovers the scope a connect wrote, and rejects non-scoped URLs", async () => {
  const { scopeFromUrl } = await import("../src/core.js");
  const scoped = scopedMcpUrl("http://localhost:8000/mcp", { userId: "reh-user", appId: "reh-app" });
  assert.deepEqual(scopeFromUrl(scoped), {
    userId: "reh-user",
    appId: "reh-app",
    baseUrl: "http://localhost:8000/mcp",
  });
  assert.equal(scopeFromUrl("http://localhost:8000/mcp"), null);
  assert.equal(scopeFromUrl(""), null);
  assert.equal(scopeFromUrl("not a url"), null);
  // percent-encoded components round-trip through validation
  const encoded = scopedMcpUrl("https://api.multi-turn.ai/mcp", { userId: "u.1", appId: "a-2" });
  assert.deepEqual(scopeFromUrl(encoded), {
    userId: "u.1",
    appId: "a-2",
    baseUrl: "https://api.multi-turn.ai/mcp",
  });
});

test("configuredServerUrl reads the installed forget URL per client kind", async () => {
  const { configuredServerUrl } = await import("../src/core.js");
  const jsonRaw = JSON.stringify({
    mcpServers: { forget: { type: "http", url: "http://localhost:8000/mcp/a/http/u" } },
  });
  assert.equal(
    configuredServerUrl({ id: "claude-code", kind: "json" }, jsonRaw),
    "http://localhost:8000/mcp/a/http/u",
  );
  const tomlRaw = '[mcp_servers.forget]\nurl = "http://localhost:8000/mcp/a/http/u"\n';
  assert.equal(
    configuredServerUrl({ id: "codex", kind: "toml" }, tomlRaw),
    "http://localhost:8000/mcp/a/http/u",
  );
  assert.equal(configuredServerUrl({ id: "claude-code", kind: "json" }, ""), "");
  assert.equal(configuredServerUrl({ id: "claude-code", kind: "json" }, "{}"), "");
});

test("detectInstalledScope finds the first scoped client config", async (t) => {
  const { detectInstalledScope } = await import("../src/core.js");
  const dir = await mkdtemp(path.join(os.tmpdir(), "forget-scope-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const configPath = path.join(dir, ".claude.json");
  await writeFile(configPath, JSON.stringify({
    mcpServers: { forget: { type: "http", url: "http://localhost:8000/mcp/my-app/http/my-user" } },
  }));
  const scope = await detectInstalledScope([
    { id: "claude-code", kind: "json", configPath: path.join(dir, "missing.json") },
    { id: "claude-code", kind: "json", configPath },
  ]);
  assert.deepEqual(scope, {
    userId: "my-user",
    appId: "my-app",
    baseUrl: "http://localhost:8000/mcp",
  });
});
