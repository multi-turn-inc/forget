import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseArgs } from "../src/cli.js";
import { getClients } from "../src/core.js";

const BIN = fileURLToPath(new URL("../bin/forget-connect.js", import.meta.url));
const SECRET = "integration-secret-must-not-print";

function invoke(home, args, extraEnv = {}) {
  const env = {
    ...process.env,
    HOME: home,
    CODEX_HOME: path.join(home, ".codex"),
    FORGET_API_KEY: SECRET,
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

test("Bearer authentication is never sent over a plaintext URL", async (t) => {
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
