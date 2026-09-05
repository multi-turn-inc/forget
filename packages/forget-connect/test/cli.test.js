import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseArgs, urlForClient } from "../src/cli.js";
import { getClients, scopedMcpUrl } from "../src/core.js";

const BIN = fileURLToPath(new URL("../bin/forget-connect.js", import.meta.url));
const SECRET = "integration-secret-must-not-print";

function invoke(home, args, extraEnv = {}) {
  const env = {
    ...process.env,
    HOME: home,
    CODEX_HOME: path.join(home, ".codex"),
    FORGET_API_KEY: SECRET,
    // Proxy wiring writes plists and settings into the fixture HOME, but the
    // real launchd is a machine-global registry: tests must never bootstrap
    // into it. This seam skips only the launchctl calls.
    FORGET_PROXY_LAUNCHCTL: "skip",
    ...extraEnv,
  };
  return spawnSync(process.execPath, [BIN, ...args], {
    env,
    encoding: "utf8",
  });
}

test("doctor timeout enforces the documented 1 to 60 second range", () => {
  assert.throws(() => parseArgs(["doctor", "--timeout", "0.5"], {}), /between 1 and 60/);
  assert.throws(() => parseArgs(["doctor", "--timeout=0.5"], {}), /between 1 and 60/);
  assert.equal(parseArgs(["doctor", "--timeout=1"], {}).timeoutMs, 1000);
});

test("the default endpoint is the local server; --hosted opts into the managed service", () => {
  const defaults = parseArgs([], {});
  assert.equal(defaults.baseUrl, "http://localhost:8000/mcp");
  assert.equal(defaults.hosted, false);

  const hosted = parseArgs(["connect", "--hosted"], {});
  assert.equal(hosted.baseUrl, "https://api.multi-turn.ai/mcp");
  assert.equal(hosted.hosted, true);

  const hostedOverridesEnv = parseArgs(["connect", "--hosted"], {
    FORGET_MCP_URL: "http://localhost:9999/mcp",
  });
  assert.equal(hostedOverridesEnv.baseUrl, "https://api.multi-turn.ai/mcp");

  assert.throws(
    () => parseArgs(["connect", "--hosted", "--url", "https://example.test/mcp"], {}),
    /mutually exclusive/,
  );
});

test("scope flags and environment build the scoped endpoint", () => {
  const flags = parseArgs([
    "connect",
    "--hosted",
    "--user-id",
    "junghunkim",
    "--app-id=Mem1",
  ], {});
  assert.equal(flags.baseUrl, "https://api.multi-turn.ai/mcp");
  assert.equal(flags.url, "https://api.multi-turn.ai/mcp/Mem1/http/junghunkim");
  assert.deepEqual(flags.scope, { userId: "junghunkim", appId: "Mem1" });
  assert.equal(flags.hosted, true);

  const fromEnv = parseArgs(["doctor"], {
    FORGET_USER_ID: "user-env",
    FORGET_APP_ID: "app-env",
  });
  assert.equal(fromEnv.url, "http://localhost:8000/mcp/app-env/http/user-env");
  assert.equal(fromEnv.hosted, false);
  assert.throws(
    () => parseArgs(["connect", "--user-id", "lonely"], {}),
    /must be provided together/,
  );

  const directHostedScope = parseArgs([
    "doctor",
    "--url",
    "https://api.multi-turn.ai/mcp/Wrong/http/Wrong",
  ], {});
  assert.equal(directHostedScope.hosted, true);
  assert.equal(directHostedScope.scope, null);

  const sameOriginUnknownPath = parseArgs([
    "doctor",
    "--url",
    "https://api.multi-turn.ai/mcp-lookalike/Wrong/http/Wrong",
  ], {});
  assert.equal(sameOriginUnknownPath.hosted, true);

  for (const encodedPath of [
    "https://api.multi-turn.ai/%6Dcp/Mem1/http/junghunkim",
    "https://api.multi-turn.ai/mcp%2FMem1/http/junghunkim",
  ]) {
    const encodedHostedScope = parseArgs(["doctor", "--url", encodedPath], {});
    assert.equal(encodedHostedScope.hosted, true);
    assert.equal(encodedHostedScope.scope, null);
  }

  const differentOrigin = parseArgs([
    "doctor",
    "--url",
    "https://example.test/mcp/Mem1/http/junghunkim",
  ], {});
  assert.equal(differentOrigin.hosted, false);

  for (const insecureManagedUrl of [
    "http://api.multi-turn.ai/mcp/Mem1/http/junghunkim",
    "https://api.multi-turn.ai:8443/mcp/Mem1/http/junghunkim",
    "http://api.multi-turn.ai./mcp/Mem1/http/junghunkim",
  ]) {
    assert.throws(
      () => parseArgs(["doctor", "--url", insecureManagedUrl], {}),
      /requires HTTPS on its standard port/,
    );
  }
});

test("local connect defaults to the canonical scoped endpoint (issue #27)", () => {
  const osUser = os.userInfo().username;
  const clients = getClients({ home: "/tmp/forget-connect-scope-unit", env: {} });
  const claude = clients.find((client) => client.id === "claude-code");
  const codex = clients.find((client) => client.id === "codex");

  const defaults = parseArgs([], {});
  assert.deepEqual(defaults.defaultScope, { userId: osUser });
  assert.equal(
    urlForClient(defaults, claude),
    `${scopedMcpUrl("http://localhost:8000/mcp", { userId: osUser, appId: "forget" })}?profile=claude`,
  );
  assert.equal(
    urlForClient(defaults, codex),
    `${scopedMcpUrl("http://localhost:8000/mcp", { userId: osUser, appId: "forget" })}?profile=codex`,
  );

  // Opt-outs: --no-scope, an explicit --url (installed verbatim), and hosted
  // (the OS username is not a hosted account identity).
  assert.equal(parseArgs(["connect", "--no-scope"], {}).defaultScope, null);
  const verbatim = parseArgs(["connect", "--url", "http://localhost:8001/mcp"], {});
  assert.equal(verbatim.defaultScope, null);
  assert.equal(urlForClient(verbatim, claude), "http://localhost:8001/mcp?profile=claude");
  assert.equal(parseArgs(["connect", "--hosted"], {}).defaultScope, null);
  assert.throws(
    () => parseArgs(["connect", "--no-scope", "--user-id", "u", "--app-id", "a"], {}),
    /mutually exclusive/,
  );

  // An explicit scope pins one endpoint for every client.
  const explicit = parseArgs(["connect", "--user-id", "u1", "--app-id", "a1"], {});
  assert.equal(explicit.defaultScope, null);
  assert.equal(urlForClient(explicit, claude), "http://localhost:8000/mcp/a1/http/u1?profile=claude");
});

test("default connect writes the canonical scoped endpoint for every client; --no-scope opts out", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-default-scope-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const osUser = encodeURIComponent(os.userInfo().username);

  const connected = invoke(home, ["connect", "--client", "all"]);
  assert.equal(connected.status, 0, connected.stderr);
  assert.match(connected.stdout, /scope: user .* canonical pool/);

  const clients = getClients({
    home,
    platform: process.platform,
    env: { CODEX_HOME: path.join(home, ".codex") },
  });
  for (const client of clients) {
    const config = await readFile(client.configPath, "utf8");
    // One canonical pool for every client: a per-client app pool made each
    // tool's writes invisible to the others (issue #27, field report).
    const endpoint = `http://localhost:8000/mcp/forget/http/${osUser}`;
    assert.match(
      config,
      new RegExp(endpoint.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      `${client.id} must share the canonical pool`,
    );
  }
  const settings = JSON.parse(
    await readFile(path.join(home, ".claude", "settings.json"), "utf8"),
  );
  assert.match(
    JSON.stringify(settings.hooks),
    new RegExp(`/mcp/forget/http/${osUser.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`),
    "hooks must talk to the same scoped endpoint as the client",
  );

  const optOut = invoke(home, ["connect", "--client", "codex", "--no-scope"]);
  assert.equal(optOut.status, 0, optOut.stderr);
  const codexConfig = await readFile(path.join(home, ".codex", "config.toml"), "utf8");
  assert.match(codexConfig, /url = "http:\/\/localhost:8000\/mcp\?profile=codex"/);
});

test("bare doctor adopts each client's own installed scope", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-doctor-scopes-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  // Two clients share a vault but retain provider-specific tool profiles. Base
  // 127.0.0.1:1 guarantees the remote probe fails fast without a live server.
  await mkdir(path.join(home, ".codex"), { recursive: true });
  await writeFile(
    path.join(home, ".codex", "config.toml"),
    '[mcp_servers.forget]\nurl = "http://127.0.0.1:1/mcp/forget/http/user-one?profile=codex"\n',
  );
  await writeFile(
    path.join(home, ".claude.json"),
    `${JSON.stringify({
      mcpServers: {
        forget: { type: "http", url: "http://127.0.0.1:1/mcp/forget/http/user-one?profile=claude" },
      },
    })}\n`,
  );

  // Rules are intentionally absent: the local mismatch keeps doctor off the
  // network, so the assertions below cover only per-client URL adoption.
  const result = invoke(home, [
    "doctor",
    "--client",
    "claude-code,codex",
    "--timeout",
    "1",
    "--json",
  ]);
  const report = JSON.parse(result.stdout);
  assert.equal(report.scope.configured, true);
  for (const client of report.clients) {
    assert.equal(client.url_matches, true, `${client.id} must match its own installed scope`);
  }
});

test("Bearer authentication blocks remote plaintext and requires local opt-in", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-http-auth-"));
  t.after(() => rm(home, { recursive: true, force: true }));

  const blocked = invoke(home, [
    "connect",
    "--client",
    "codex",
    "--url",
    "http://192.168.0.10:8000/mcp",
  ]);
  assert.equal(blocked.status, 1);
  assert.match(blocked.stderr, /Bearer authentication requires HTTPS/);
  assert.doesNotMatch(blocked.stdout + blocked.stderr, new RegExp(SECRET));

  // A leftover hosted key must not break the loopback default: connect
  // proceeds without a token and says so.
  const loopback = invoke(home, ["connect", "--client", "codex"]);
  assert.equal(loopback.status, 0, loopback.stderr);
  assert.match(loopback.stderr, /connecting without a token/);
  assert.doesNotMatch(loopback.stdout + loopback.stderr, new RegExp(SECRET));
  const loopbackConfig = await readFile(
    path.join(home, ".codex", "config.toml"),
    "utf8",
  );
  assert.doesNotMatch(loopbackConfig, new RegExp(SECRET));

  const localAuth = invoke(home, [
    "connect",
    "--client",
    "codex",
    "--local-auth",
  ]);
  assert.equal(localAuth.status, 0, localAuth.stderr);
  assert.doesNotMatch(localAuth.stdout + localAuth.stderr, new RegExp(SECRET));
  const localAuthConfig = await readFile(
    path.join(home, ".codex", "config.toml"),
    "utf8",
  );
  assert.match(localAuthConfig, /Authorization = "Bearer integration-secret-must-not-print"/);
  assert.throws(
    () => parseArgs(["connect", "--local-auth", "--no-auth"], {}),
    /mutually exclusive/,
  );
  assert.throws(
    () => parseArgs(["connect", "--local-auth", "--url", "https:\/\/example.test\/mcp"], {}),
    /only allowed for a loopback/,
  );

  const noAuth = invoke(home, [
    "connect",
    "--client",
    "codex",
    "--url",
    "http://localhost:8000/mcp",
    "--no-auth",
  ]);
  assert.equal(noAuth.status, 0, noAuth.stderr);
  assert.doesNotMatch(noAuth.stdout + noAuth.stderr, new RegExp(SECRET));
});

test("CLI connects, reports status, and disconnects all clients without leaking the key", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-cli-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const clients = getClients({
    home,
    platform: process.platform,
    env: { CODEX_HOME: path.join(home, ".codex") },
  });
  for (const client of clients) {
    await mkdir(path.dirname(client.configPath), { recursive: true });
    const existing = client.kind === "toml"
      ? '[mcp_servers.other]\nurl = "https://example.test/mcp"\n'
      : '{"mcpServers":{"other":{"command":"other"}}}\n';
    await writeFile(client.configPath, existing);
    if (client.rulesPath) {
      await mkdir(path.dirname(client.rulesPath), { recursive: true });
      await writeFile(client.rulesPath, `# ${client.name} personal rules\n`);
    }
  }

  const connected = invoke(home, ["connect", "--client", "all"]);
  assert.equal(connected.status, 0, connected.stderr);
  assert.doesNotMatch(connected.stdout, new RegExp(SECRET));
  assert.doesNotMatch(connected.stderr, new RegExp(SECRET));
  assert.match(connected.stdout, /Connected Claude Code, Codex, Claude Desktop/);

  for (const client of clients) {
    const config = await readFile(client.configPath, "utf8");
    assert.match(config, /forget/);
    assert.match(config, /localhost:8000\/mcp/);
    assert.doesNotMatch(config, new RegExp(SECRET));
    assert.equal(await readFile(`${client.configPath}.forget-backup`, "utf8").then(Boolean), true);
    if (client.rulesPath) {
      const rules = await readFile(client.rulesPath, "utf8");
      assert.match(rules, new RegExp(`# ${client.name} personal rules`));
      assert.match(rules, /forget:memory:start/);
    }
  }

  const status = invoke(home, ["status"]);
  assert.equal(status.status, 0, status.stderr);
  assert.equal((status.stdout.match(/connected/g) ?? []).length >= 3, true);
  assert.doesNotMatch(status.stdout, new RegExp(SECRET));

  const disconnected = invoke(home, ["disconnect"]);
  assert.equal(disconnected.status, 0, disconnected.stderr);
  assert.doesNotMatch(disconnected.stdout, new RegExp(SECRET));
  for (const client of clients) {
    const config = await readFile(client.configPath, "utf8");
    assert.doesNotMatch(config, /mcp_servers\.forget|"forget"/);
    assert.match(config, /other/);
    if (client.rulesPath) {
      const rules = await readFile(client.rulesPath, "utf8");
      assert.doesNotMatch(rules, /forget:memory/);
      assert.match(rules, new RegExp(`# ${client.name} personal rules`));
    }
  }
});

test("dry-run lists paths but writes nothing", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-dry-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const result = invoke(home, ["connect", "--client", "codex", "--dry-run"]);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Would update .*config\.toml/);
  assert.doesNotMatch(result.stdout, new RegExp(SECRET));
  await assert.rejects(readFile(path.join(home, ".codex", "config.toml")), /ENOENT/);
});

test("hosted connect writes the Bearer token to client configs", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-hosted-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const result = invoke(home, ["connect", "--client", "codex", "--hosted"]);
  assert.equal(result.status, 0, result.stderr);
  assert.doesNotMatch(result.stdout, new RegExp(SECRET));
  const config = await readFile(path.join(home, ".codex", "config.toml"), "utf8");
  assert.match(config, /api\.multi-turn\.ai\/mcp/);
  assert.match(config, new RegExp(SECRET));
});

test("scoped CLI writes the same encoded endpoint for every client", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-scoped-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const result = invoke(home, [
    "connect",
    "--client",
    "all",
    "--hosted",
    "--user-id",
    "user-one",
    "--app-id",
    "project-one",
  ]);
  assert.equal(result.status, 0, result.stderr);
  assert.doesNotMatch(result.stdout + result.stderr, new RegExp(SECRET));
  assert.doesNotMatch(result.stdout, /continuity scope is not configured/);

  const endpoint = "https://api.multi-turn.ai/mcp/project-one/http/user-one";
  const clients = getClients({
    home,
    platform: process.platform,
    env: { CODEX_HOME: path.join(home, ".codex") },
  });
  for (const client of clients) {
    const config = await readFile(client.configPath, "utf8");
    assert.match(config, new RegExp(endpoint.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("doctor --json keeps an auto-detected scope notice off stdout", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-connect-doctor-json-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const configPath = path.join(home, ".codex", "config.toml");
  await mkdir(path.dirname(configPath), { recursive: true });
  await writeFile(
    configPath,
    '[mcp_servers.forget]\nurl = "http://127.0.0.1:1/mcp/project-one/http/user-one"\n',
  );

  const result = invoke(home, [
    "doctor",
    "--client",
    "codex",
    "--timeout",
    "1",
    "--json",
  ]);

  const report = JSON.parse(result.stdout);
  assert.equal(report.scope.configured, true);
  assert.match(result.stderr, /Scope detected from installed config/);
  assert.doesNotMatch(result.stdout, /Scope detected from installed config/);
});

test("clean-room: connect installs the full memory experience, disconnect removes it", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-cleanroom-"));
  try {
    const connect = invoke(home, ["connect", "--client", "claude-code", "-y"]);
    assert.equal(connect.status, 0, connect.stderr);

    const config = JSON.parse(await readFile(path.join(home, ".claude.json"), "utf8"));
    assert.ok(config.mcpServers.forget, "MCP server registered");
    const rules = await readFile(path.join(home, ".claude", "CLAUDE.md"), "utf8");
    assert.match(rules, /trust/, "traffic-light contract installed");
    const settingsPath = path.join(home, ".claude", "settings.json");
    const settings = JSON.parse(await readFile(settingsPath, "utf8"));
    for (const event of ["SessionStart", "UserPromptSubmit", "PreCompact", "SessionEnd"]) {
      assert.ok(settings.hooks[event], `${event} hook registered`);
    }
    for (const script of ["forget_sessionstart.py", "forget_turnrecall.py", "forget_capture.py"]) {
      const body = await readFile(path.join(home, ".forget", "hooks", script), "utf8");
      assert.ok(body.startsWith("#!/usr/bin/env python3"), `${script} installed`);
    }

    const again = invoke(home, ["connect", "--client", "claude-code", "-y"]);
    assert.equal(again.status, 0, again.stderr);
    const settingsAgain = JSON.parse(await readFile(settingsPath, "utf8"));
    assert.equal(settingsAgain.hooks.SessionStart.length, 1, "reconnect is idempotent");

    const off = invoke(home, ["disconnect", "--client", "claude-code"]);
    assert.equal(off.status, 0, off.stderr);
    const settingsOff = JSON.parse(await readFile(settingsPath, "utf8"));
    assert.equal(settingsOff.hooks, undefined, "hooks fully removed");
    await assert.rejects(
      readFile(path.join(home, ".forget", "hooks", "forget_capture.py")),
      /ENOENT/,
      "scripts removed",
    );
    const configOff = JSON.parse(await readFile(path.join(home, ".claude.json"), "utf8"));
    assert.ok(!configOff.mcpServers?.forget, "MCP server removed");
  } finally {
    await rm(home, { recursive: true, force: true });
  }
});

test("clean-room: Codex and Claude share scripts but retain profiles and safe removal", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-both-clients-"));
  try {
    const connect = invoke(home, [
      "connect",
      "--client",
      "claude-code,codex",
      "-y",
      "--no-proxy",
    ]);
    assert.equal(connect.status, 0, connect.stderr);

    const claudeConfig = JSON.parse(await readFile(path.join(home, ".claude.json"), "utf8"));
    assert.match(claudeConfig.mcpServers.forget.url, /profile=claude/);
    assert.match(await readFile(path.join(home, ".codex", "config.toml"), "utf8"), /profile=codex/);
    const codexHooks = JSON.parse(await readFile(path.join(home, ".codex", "hooks.json"), "utf8"));
    assert.deepEqual(Object.keys(codexHooks.hooks), ["SessionStart", "UserPromptSubmit", "Stop"]);
    await readFile(path.join(home, ".codex", "skills", "memory-agent", "SKILL.md"), "utf8");
    await readFile(path.join(home, ".claude", "skills", "memory-agent", "SKILL.md"), "utf8");

    const removeCodex = invoke(home, ["disconnect", "--client", "codex", "--no-proxy"]);
    assert.equal(removeCodex.status, 0, removeCodex.stderr);
    const codexHooksOff = JSON.parse(await readFile(path.join(home, ".codex", "hooks.json"), "utf8"));
    assert.equal(codexHooksOff.hooks, undefined);
    await readFile(path.join(home, ".forget", "hooks", "forget_capture.py"), "utf8");
    await readFile(path.join(home, ".claude", "skills", "memory-agent", "SKILL.md"), "utf8");
    await assert.rejects(
      readFile(path.join(home, ".codex", "skills", "memory-agent", "SKILL.md")),
      /ENOENT/,
    );

    const removeClaude = invoke(home, ["disconnect", "--client", "claude-code", "--no-proxy"]);
    assert.equal(removeClaude.status, 0, removeClaude.stderr);
    await assert.rejects(
      readFile(path.join(home, ".forget", "hooks", "forget_capture.py")),
      /ENOENT/,
    );
  } finally {
    await rm(home, { recursive: true, force: true });
  }
});
