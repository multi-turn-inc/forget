import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  PROXY_BASE_URL,
  PROXY_LABEL,
  WATCHDOG_LABEL,
  WATCHDOG_SCRIPT,
  isProxyBaseUrl,
  proxyPlist,
  unwireProxyEnv,
  watchdogPlist,
  wireProxyEnv,
} from "../src/proxy.js";

const BIN = fileURLToPath(new URL("../bin/forget-connect.js", import.meta.url));

function parse(text) {
  return JSON.parse(text);
}

// --- env wiring: branch (a) — chain an existing custom gateway ---------------

test("wire chains an existing custom base URL as the proxy upstream", () => {
  const raw = JSON.stringify({
    model: "opus",
    env: { ANTHROPIC_BASE_URL: "https://gateway.corp.example/v1", OTHER: "x" },
  });
  const plan = wireProxyEnv(raw);
  assert.equal(plan.status, "wire");
  assert.equal(plan.upstream, "https://gateway.corp.example/v1");
  assert.equal(plan.original, "https://gateway.corp.example/v1");
  const next = parse(plan.next);
  assert.equal(next.env.ANTHROPIC_BASE_URL, PROXY_BASE_URL);
  // Everything that is not ours survives byte-identical in value.
  assert.equal(next.env.OTHER, "x");
  assert.equal(next.model, "opus");
});

test("wire on a fresh settings file adds the override with no upstream", () => {
  for (const raw of ["", "{}", JSON.stringify({ env: {} })]) {
    const plan = wireProxyEnv(raw);
    assert.equal(plan.status, "wire", `raw=${JSON.stringify(raw)}`);
    assert.equal(plan.upstream, null);
    assert.equal(plan.original, null);
    assert.equal(parse(plan.next).env.ANTHROPIC_BASE_URL, PROXY_BASE_URL);
  }
});

// --- branch (b) — already us is a no-op --------------------------------------

test("wire is a no-op when the base URL is already our proxy", () => {
  for (const value of [
    PROXY_BASE_URL,
    "http://127.0.0.1:8377/",
    "http://localhost:8377",
  ]) {
    const raw = JSON.stringify({ env: { ANTHROPIC_BASE_URL: value } });
    const plan = wireProxyEnv(raw);
    assert.equal(plan.status, "noop", value);
    assert.equal(plan.next, raw, "a no-op must not rewrite the file");
  }
});

// --- branch (c) — anything odd skips the wiring entirely ---------------------

test("wire skips broken or structurally odd configurations untouched", () => {
  const cases = [
    ["{not json", /not valid JSON/],
    [JSON.stringify({ env: ["not", "an", "object"] }), /not a JSON object/],
    [JSON.stringify({ env: { ANTHROPIC_BASE_URL: 8377 } }), /not a string/],
    [JSON.stringify({ env: { ANTHROPIC_BASE_URL: "not a url" } }), /not an http\(s\) URL/],
    [JSON.stringify({ env: { ANTHROPIC_BASE_URL: "file:///etc/passwd" } }), /not an http\(s\) URL/],
  ];
  for (const [raw, reason] of cases) {
    const plan = wireProxyEnv(raw);
    assert.equal(plan.status, "skip", raw);
    assert.equal(plan.next, raw, "skip must leave the file untouched");
    assert.match(plan.reason, reason);
  }
});

test("isProxyBaseUrl rejects lookalikes", () => {
  assert.equal(isProxyBaseUrl("http://127.0.0.1:8378"), false);
  assert.equal(isProxyBaseUrl("https://127.0.0.1:8377"), false);
  assert.equal(isProxyBaseUrl("http://evil.example:8377"), false);
  assert.equal(isProxyBaseUrl("http://127.0.0.1:8377/v1"), false);
  assert.equal(isProxyBaseUrl(8377), false);
});

// --- unwire: symmetric removal ----------------------------------------------

test("unwire restores the recorded original and removes ours otherwise", () => {
  const ours = JSON.stringify({ env: { ANTHROPIC_BASE_URL: PROXY_BASE_URL, KEEP: "1" } });
  const restored = unwireProxyEnv(ours, { original: "https://gateway.corp.example/v1" });
  assert.equal(restored.status, "unwired");
  assert.equal(parse(restored.next).env.ANTHROPIC_BASE_URL, "https://gateway.corp.example/v1");
  assert.equal(parse(restored.next).env.KEEP, "1");

  const removed = unwireProxyEnv(ours, { original: null });
  assert.equal(removed.status, "unwired");
  assert.equal(parse(removed.next).env.ANTHROPIC_BASE_URL, undefined);
  assert.equal(parse(removed.next).env.KEEP, "1");

  // A now-empty env object disappears entirely.
  const bare = JSON.stringify({ env: { ANTHROPIC_BASE_URL: PROXY_BASE_URL } });
  assert.equal(parse(unwireProxyEnv(bare, {}).next).env, undefined);
});

test("unwire never touches a value the user changed and skips broken JSON", () => {
  const theirs = JSON.stringify({ env: { ANTHROPIC_BASE_URL: "https://their.gateway/v1" } });
  assert.equal(unwireProxyEnv(theirs, {}).status, "noop");
  assert.equal(unwireProxyEnv(theirs, {}).next, theirs);
  const absent = JSON.stringify({ env: { OTHER: "x" } });
  assert.equal(unwireProxyEnv(absent, {}).status, "noop");
  assert.equal(unwireProxyEnv("{broken", {}).status, "skip");
  assert.equal(unwireProxyEnv("{broken", {}).next, "{broken");
});

test("wire then unwire round-trips a chained gateway", () => {
  const raw = JSON.stringify({ env: { ANTHROPIC_BASE_URL: "https://gw.example" } }, null, 2);
  const plan = wireProxyEnv(raw);
  const back = unwireProxyEnv(plan.next, { original: plan.original });
  assert.equal(parse(back.next).env.ANTHROPIC_BASE_URL, "https://gw.example");
});

// --- launchd plists ----------------------------------------------------------

test("proxy plist follows the ai.forget.server convention", () => {
  const plist = proxyPlist({
    execPath: "/venv/bin/forget-proxy",
    upstream: "https://gateway.corp.example/v1?a=1&b=2",
    forgetHome: "/home/user/.forget",
    logPath: "/home/user/.forget/proxy.log",
  });
  assert.match(plist, new RegExp(`<key>Label</key><string>${PROXY_LABEL}</string>`));
  assert.match(plist, /<key>KeepAlive<\/key><true\/>/);
  assert.match(plist, /<key>RunAtLoad<\/key><true\/>/);
  assert.match(plist, /<string>--port<\/string>\n\s*<string>8377<\/string>/);
  assert.match(plist, /<string>--upstream<\/string>/);
  // XML-escaped: a query string with & must not corrupt the plist.
  assert.match(plist, /a=1&amp;b=2/);
  assert.match(plist, /<key>FORGET_HOME<\/key><string>\/home\/user\/\.forget<\/string>/);

  // Without a custom gateway the upstream stays owned by the binary.
  const plain = proxyPlist({
    execPath: "/venv/bin/forget-proxy",
    forgetHome: "/home/user/.forget",
    logPath: "/home/user/.forget/proxy.log",
  });
  assert.doesNotMatch(plain, /--upstream/);
});

test("watchdog plist runs every 60 seconds, not KeepAlive", () => {
  const plist = watchdogPlist({
    python3: "/usr/bin/python3",
    scriptPath: "/home/user/.forget/proxy/forget_proxy_watchdog.py",
    forgetHome: "/home/user/.forget",
    logPath: "/home/user/.forget/proxy-watchdog.log",
  });
  assert.match(plist, new RegExp(`<key>Label</key><string>${WATCHDOG_LABEL}</string>`));
  assert.match(plist, /<key>StartInterval<\/key><integer>60<\/integer>/);
  assert.doesNotMatch(plist, /KeepAlive/);
});

// --- end to end through the CLI (files only; launchctl skipped) --------------

const darwinOnly = process.platform === "darwin" ? test : test.skip;

darwinOnly("connect wires proxy files end-to-end and disconnect restores the gateway", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-proxy-cli-"));
  t.after(() => rm(home, { recursive: true, force: true }));

  // A fake forget-proxy on PATH: wiring must not depend on a real install.
  const binDir = path.join(home, "fakebin");
  await mkdir(binDir, { recursive: true });
  const fakeProxy = path.join(binDir, "forget-proxy");
  await writeFile(fakeProxy, "#!/bin/sh\nexit 0\n");
  await chmod(fakeProxy, 0o755);

  // The user already routes through a custom gateway.
  const settingsPath = path.join(home, ".claude", "settings.json");
  await mkdir(path.dirname(settingsPath), { recursive: true });
  await writeFile(settingsPath, `${JSON.stringify({
    env: { ANTHROPIC_BASE_URL: "https://gateway.corp.example/v1" },
  }, null, 2)}\n`);

  const invoke = (args) => spawnSync(process.execPath, [BIN, ...args], {
    encoding: "utf8",
    env: {
      ...process.env,
      HOME: home,
      PATH: `${binDir}${path.delimiter}${process.env.PATH ?? ""}`,
      FORGET_PROXY_LAUNCHCTL: "skip",
    },
  });

  const connected = invoke(["connect", "--client", "claude-code", "-y", "--no-auth"]);
  assert.equal(connected.status, 0, connected.stderr);

  const settings = parse(await readFile(settingsPath, "utf8"));
  assert.equal(settings.env.ANTHROPIC_BASE_URL, PROXY_BASE_URL);

  const wiring = parse(await readFile(path.join(home, ".forget", "proxy", "wiring.json"), "utf8"));
  assert.equal(wiring.original_base_url, "https://gateway.corp.example/v1");
  assert.equal(wiring.upstream, "https://gateway.corp.example/v1");

  const proxyPlistRaw = await readFile(
    path.join(home, "Library", "LaunchAgents", `${PROXY_LABEL}.plist`),
    "utf8",
  );
  assert.match(proxyPlistRaw, /--upstream/);
  assert.match(proxyPlistRaw, /gateway\.corp\.example/);
  await readFile(path.join(home, "Library", "LaunchAgents", `${WATCHDOG_LABEL}.plist`), "utf8");
  const watchdog = await readFile(path.join(home, ".forget", "proxy", WATCHDOG_SCRIPT), "utf8");
  assert.ok(watchdog.startsWith("#!/usr/bin/env python3"));

  // Reconnect is a settings no-op and must not lose the original record.
  const again = invoke(["connect", "--client", "claude-code", "-y", "--no-auth"]);
  assert.equal(again.status, 0, again.stderr);
  const wiringAgain = parse(await readFile(path.join(home, ".forget", "proxy", "wiring.json"), "utf8"));
  assert.equal(wiringAgain.original_base_url, "https://gateway.corp.example/v1");

  const off = invoke(["disconnect", "--client", "claude-code"]);
  assert.equal(off.status, 0, off.stderr);
  const settingsOff = parse(await readFile(settingsPath, "utf8"));
  assert.equal(settingsOff.env.ANTHROPIC_BASE_URL, "https://gateway.corp.example/v1");
  await assert.rejects(
    readFile(path.join(home, "Library", "LaunchAgents", `${PROXY_LABEL}.plist`)),
    /ENOENT/,
  );
  await assert.rejects(
    readFile(path.join(home, ".forget", "proxy", "wiring.json")),
    /ENOENT/,
  );
});

darwinOnly("a broken settings.json skips proxy wiring without touching anything", async (t) => {
  const home = await mkdtemp(path.join(os.tmpdir(), "forget-proxy-broken-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const binDir = path.join(home, "fakebin");
  await mkdir(binDir, { recursive: true });
  await writeFile(path.join(binDir, "forget-proxy"), "#!/bin/sh\nexit 0\n");
  await chmod(path.join(binDir, "forget-proxy"), 0o755);

  const settingsPath = path.join(home, ".claude", "settings.json");
  await mkdir(path.dirname(settingsPath), { recursive: true });
  const broken = '{"env": {"ANTHROPIC_BASE_URL": ["odd"]}}';
  await writeFile(settingsPath, broken);

  const result = spawnSync(
    process.execPath,
    // --no-hooks isolates the branch: hooks would edit settings.json too.
    [BIN, "connect", "--client", "claude-code", "-y", "--no-auth", "--no-hooks", "--no-rules"],
    {
      encoding: "utf8",
      env: {
        ...process.env,
        HOME: home,
        PATH: `${binDir}${path.delimiter}${process.env.PATH ?? ""}`,
        FORGET_PROXY_LAUNCHCTL: "skip",
      },
    },
  );
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stderr, /skipping proxy wiring/);
  assert.equal(await readFile(settingsPath, "utf8"), broken, "odd config stays byte-identical");
  await assert.rejects(
    readFile(path.join(home, "Library", "LaunchAgents", `${PROXY_LABEL}.plist`)),
    /ENOENT/,
  );
});
