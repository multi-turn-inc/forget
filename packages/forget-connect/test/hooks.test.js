import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  HOOK_SCRIPTS,
  connectHooksSettings,
  disconnectHooksSettings,
  hookCommand,
  hooksInstalled,
  readHookAssets,
} from "../src/hooks.js";

const HOOKS_DIR = "/home/user/.forget/hooks";
const MCP_URL = "http://127.0.0.1:8000/mcp/myapp/http/me";

// A foreign hook that must survive everything we do — mirrors real-world
// setups where other tools (e.g. Orca) already own entries in settings.json.
const FOREIGN = {
  matcher: "*",
  hooks: [{ type: "command", command: "/bin/sh /opt/other-tool/hook.sh", timeout: 10 }],
};

function parse(text) {
  return JSON.parse(text);
}

test("connect on an empty settings file registers all four events", () => {
  const next = parse(connectHooksSettings("", { hooksDir: HOOKS_DIR, url: MCP_URL }));
  for (const event of ["SessionStart", "UserPromptSubmit", "PreCompact", "SessionEnd"]) {
    const groups = next.hooks[event];
    assert.equal(groups.length, 1);
    const hook = groups[0].hooks[0];
    assert.equal(hook.type, "command");
    assert.ok(hook.command.includes("forget_"));
    assert.ok(hook.command.includes(`FORGET_MCP_URL='${MCP_URL}'`));
  }
});

test("connect preserves foreign hooks and reconnect stays idempotent", () => {
  const existing = JSON.stringify({
    model: "opus",
    hooks: { UserPromptSubmit: [FOREIGN], Stop: [FOREIGN] },
  });
  const once = connectHooksSettings(existing, { hooksDir: HOOKS_DIR, url: MCP_URL });
  const twice = connectHooksSettings(once, { hooksDir: HOOKS_DIR, url: MCP_URL });
  const config = parse(twice);
  // foreign entries intact, ours present exactly once
  assert.deepEqual(config.hooks.Stop, [FOREIGN]);
  assert.equal(config.hooks.UserPromptSubmit.length, 2);
  assert.deepEqual(config.hooks.UserPromptSubmit[0], FOREIGN);
  const ours = config.hooks.UserPromptSubmit.filter((group) =>
    group.hooks.some((hook) => hook.command.includes("forget_")));
  assert.equal(ours.length, 1);
  // unrelated settings untouched
  assert.equal(config.model, "opus");
});

test("connect replaces hand-installed variants recognized by path marker", () => {
  const handInstalled = JSON.stringify({
    hooks: {
      SessionStart: [{
        hooks: [{ type: "command", command: "python3 /Users/x/.forget/hooks/forget_sessionstart.py", timeout: 12 }],
      }],
    },
  });
  const next = parse(connectHooksSettings(handInstalled, { hooksDir: HOOKS_DIR, url: MCP_URL }));
  assert.equal(next.hooks.SessionStart.length, 1);
  assert.ok(next.hooks.SessionStart[0].hooks[0].command.includes(`FORGET_MCP_URL='${MCP_URL}'`));
});

test("disconnect removes only ours and cleans empty structures", () => {
  const existing = JSON.stringify({
    theme: "dark",
    hooks: { UserPromptSubmit: [FOREIGN], Stop: [FOREIGN] },
  });
  const connected = connectHooksSettings(existing, { hooksDir: HOOKS_DIR, url: MCP_URL });
  const disconnected = parse(disconnectHooksSettings(connected));
  assert.deepEqual(disconnected.hooks.UserPromptSubmit, [FOREIGN]);
  assert.deepEqual(disconnected.hooks.Stop, [FOREIGN]);
  assert.equal(disconnected.hooks.SessionStart, undefined);
  assert.equal(disconnected.hooks.PreCompact, undefined);
  assert.equal(disconnected.theme, "dark");
  // fully-ours file collapses back to no hooks key
  const onlyOurs = connectHooksSettings("", { hooksDir: HOOKS_DIR, url: MCP_URL });
  const emptied = parse(disconnectHooksSettings(onlyOurs));
  assert.equal(emptied.hooks, undefined);
});

test("disconnect on a file without our hooks is a byte-level no-op", () => {
  const raw = JSON.stringify({ hooks: { Stop: [FOREIGN] } });
  assert.equal(disconnectHooksSettings(raw), raw);
});

test("hooksInstalled detects a complete install and rejects partial ones", () => {
  const connected = connectHooksSettings("", { hooksDir: HOOKS_DIR, url: MCP_URL });
  assert.equal(hooksInstalled(connected, { hooksDir: HOOKS_DIR }), true);
  const partial = parse(connected);
  delete partial.hooks.SessionEnd;
  assert.equal(hooksInstalled(JSON.stringify(partial), { hooksDir: HOOKS_DIR }), false);
  assert.equal(hooksInstalled("", { hooksDir: HOOKS_DIR }), false);
});

test("hook command shell-quotes URL and path against injection", () => {
  const command = hookCommand("forget_capture.py", {
    hooksDir: "/home/we ird/.forget/hooks",
    url: "http://127.0.0.1:8000/mcp/a'b/http/u",
  });
  assert.ok(command.includes(`'http://127.0.0.1:8000/mcp/a'\\''b/http/u'`));
  assert.ok(command.includes(`'/home/we ird/.forget/hooks/forget_capture.py'`));
});

test("packaged hook assets stay in sync with the repository hooks", async (t) => {
  const repoHooksDir = fileURLToPath(new URL("../../../hooks/", import.meta.url));
  let repoAvailable = true;
  try {
    await readFile(path.join(repoHooksDir, HOOK_SCRIPTS[0]), "utf8");
  } catch {
    repoAvailable = false;
  }
  if (!repoAvailable) {
    t.skip("repository layout not present (published package)");
    return;
  }
  for (const asset of await readHookAssets()) {
    const repoContent = await readFile(path.join(repoHooksDir, asset.name), "utf8");
    assert.equal(asset.content, repoContent, `${asset.name} drifted from repo hooks/`);
  }
});

test("hook scripts carry no hardcoded personal scope", async () => {
  for (const asset of await readHookAssets()) {
    assert.ok(!asset.content.includes("junghunkim"), `${asset.name} contains a personal scope`);
  }
});

test("command assets: install, respect user-owned files, remove only ours", async (t) => {
  const { mkdtemp, rm, writeFile } = await import("node:fs/promises");
  const os = await import("node:os");
  const { COMMAND_ASSETS, COMMAND_MARKER, installCommandAssets, removeCommandAssets } =
    await import("../src/hooks.js");

  const dir = await mkdtemp(path.join(os.tmpdir(), "forget-cmd-"));
  t.after(() => rm(dir, { recursive: true, force: true }));

  // fresh install writes both commands, marker included
  const written = await installCommandAssets(dir);
  assert.equal(written.length, COMMAND_ASSETS.length);
  for (const name of COMMAND_ASSETS) {
    const content = await readFile(path.join(dir, name), "utf8");
    assert.ok(content.includes(COMMAND_MARKER), `${name} lacks ownership marker`);
  }

  // an identical re-install is a no-op
  assert.equal((await installCommandAssets(dir)).length, 0);

  // a user-owned file (no marker) is never overwritten, never removed
  const userFile = path.join(dir, COMMAND_ASSETS[0]);
  await writeFile(userFile, "my own /forget command\n");
  assert.equal((await installCommandAssets(dir)).length, 0);
  const removed = await removeCommandAssets(dir);
  assert.equal(removed.length, COMMAND_ASSETS.length - 1);
  assert.equal(await readFile(userFile, "utf8"), "my own /forget command\n");
});

test("command assets carry no hardcoded personal scope or dogfood env", async () => {
  const { COMMAND_ASSETS } = await import("../src/hooks.js");
  const assetsDir = fileURLToPath(new URL("../assets/commands/", import.meta.url));
  for (const name of COMMAND_ASSETS) {
    const content = await readFile(path.join(assetsDir, name), "utf8");
    assert.ok(!content.includes("junghunkim"), `${name} contains a personal scope`);
    assert.ok(!content.includes("MEM1_DB_PATH"), `${name} pins the dogfood database`);
  }
});
