import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

import { ConfigError } from "../src/core.js";
import { CODEX_REQUIRED_TOOLS, MCP_PROTOCOL_VERSION, REQUIRED_TOOLS, doctorRemote } from "../src/doctor.js";

test("Codex doctor expects only the Codex profile surface", () => {
  assert.deepEqual(CODEX_REQUIRED_TOOLS, [
    "prepare_codex_context",
    "search_memories",
    "add_memory",
    "supersede_memory",
    "confirm_memory",
    "get_event_status",
    "record_context_outcome",
    "team_read",
    "team_note",
    "catalog_search",
    "product_quote",
    "grant_create",
    "agent_consult",
    "receipt_verify",
    "grant_revoke",
  ]);
  assert.equal(CODEX_REQUIRED_TOOLS.includes("prepare_context_autopilot"), false);
});

async function withServer(t, handler) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const address = server.address();
  return `http://127.0.0.1:${address.port}/mcp`;
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function respondWithCompleteMcp(body, res, { serverName = "scoped-forget" } = {}) {
  if (body.method === "notifications/initialized") {
    res.writeHead(202, { "content-type": "application/json" });
    res.end("{}");
    return;
  }
  res.setHeader("content-type", "application/json");
  if (body.method === "initialize") {
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: body.id,
      result: {
        protocolVersion: MCP_PROTOCOL_VERSION,
        serverInfo: { name: serverName, version: "1" },
      },
    }));
    return;
  }
  res.end(JSON.stringify({
    jsonrpc: "2.0",
    id: body.id,
    result: { tools: REQUIRED_TOOLS.map((name) => ({ name })) },
  }));
}

test("doctor negotiates session headers and parses SSE tools/list without leaking auth", async (t) => {
  const calls = [];
  const url = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    calls.push({
      method: body.method,
      authorization: req.headers.authorization,
      protocol: req.headers["mcp-protocol-version"],
      session: req.headers["mcp-session-id"],
    });
    if (body.method === "initialize") {
      res.writeHead(200, {
        "content-type": "application/json",
        "mcp-session-id": "session-123",
      });
      res.end(JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: {
          protocolVersion: MCP_PROTOCOL_VERSION,
          capabilities: { tools: {} },
          serverInfo: { name: "test-forget", version: "1" },
        },
      }));
    } else if (body.method === "notifications/initialized") {
      res.writeHead(202, { "content-type": "application/json" });
      res.end("{}");
    } else {
      res.writeHead(200, { "content-type": "text/event-stream" });
      res.write(`event: message\ndata: ${JSON.stringify({
        jsonrpc: "2.0",
        id: 2,
        result: { tools: REQUIRED_TOOLS.map((name) => ({ name })) },
      })}\n\n`);
    }
  });

  const result = await doctorRemote({ url, apiKey: "doctor-secret-value", timeoutMs: 2000 });
  assert.equal(result.ok, true);
  assert.equal(result.server_name, "test-forget");
  assert.equal(result.session_negotiated, true);
  assert.equal(result.tool_count, REQUIRED_TOOLS.length);
  assert.deepEqual(result.missing_tools, []);
  assert.equal(calls.length, 3);
  assert.equal(calls[0].authorization, "Bearer doctor-secret-value");
  assert.equal(calls[0].protocol, undefined);
  assert.equal(calls[1].protocol, MCP_PROTOCOL_VERSION);
  assert.equal(calls[1].session, "session-123");
  assert.equal(JSON.stringify(result).includes("doctor-secret-value"), false);
});

test("doctor reports missing continuity tools", async (t) => {
  const url = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    if (body.method === "notifications/initialized") {
      res.writeHead(202).end();
      return;
    }
    res.setHeader("content-type", "application/json");
    if (body.method === "initialize") {
      res.end(JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: { protocolVersion: MCP_PROTOCOL_VERSION, serverInfo: { name: "partial" } },
      }));
    } else {
      res.end(JSON.stringify({
        jsonrpc: "2.0",
        id: 2,
        result: { tools: [{ name: "search_memories" }] },
      }));
    }
  });
  const result = await doctorRemote({ url, timeoutMs: 2000 });
  assert.equal(result.ok, false);
  assert.equal(result.missing_tools.includes("add_memory"), true);
  assert.equal(result.missing_tools.includes("record_task_state"), true);
});

test("doctor follows tools/list pagination and strips terminal controls", async (t) => {
  const url = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    if (body.method === "notifications/initialized") {
      res.writeHead(202).end();
      return;
    }
    res.setHeader("content-type", "application/json");
    if (body.method === "initialize") {
      res.end(JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        result: {
          protocolVersion: MCP_PROTOCOL_VERSION,
          serverInfo: { name: "\u001b[31mforget-test", version: "1\u0007" },
        },
      }));
      return;
    }
    const secondPage = body.params?.cursor === "page-2";
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: body.id,
      result: {
        tools: (secondPage ? REQUIRED_TOOLS.slice(2) : REQUIRED_TOOLS.slice(0, 2))
          .map((name) => ({ name })),
        ...(secondPage ? {} : { nextCursor: "page-2" }),
      },
    }));
  });
  const result = await doctorRemote({ url, timeoutMs: 2000 });
  assert.equal(result.ok, true);
  assert.equal(result.tool_page_count, 2);
  assert.equal(result.tool_count, REQUIRED_TOOLS.length);
  assert.equal(result.server_name.includes("\u001b"), false);
  assert.equal(result.server_version.includes("\u0007"), false);
});

test("doctor verifies the configured scoped URL with auth before MCP", async (t) => {
  const calls = [];
  const baseUrl = await withServer(t, async (req, res) => {
    calls.push({
      method: req.method,
      authorization: req.headers.authorization,
      path: req.url,
    });
    if (req.method === "GET") {
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({
        transport: "streamable-http",
        user_id: "scope-user-private",
        client_name: "scope-app-private",
      }));
      return;
    }
    respondWithCompleteMcp(await readJson(req), res);
  });
  const url = `${baseUrl}/scope-app-private/http/scope-user-private`;

  const result = await doctorRemote({
    url,
    apiKey: "scope-key-private",
    expectedScope: { userId: "scope-user-private", appId: "scope-app-private" },
    requireScope: true,
    timeoutMs: 2000,
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.scope_probe, {
    requested: true,
    required: true,
    attempted: true,
    skipped: false,
    response_valid: true,
    user_id_matches: true,
    app_id_matches: true,
    ok: true,
  });
  assert.equal(Object.values(result.scope_probe).every((value) => typeof value === "boolean"), true);
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].authorization, "Bearer scope-key-private");
  assert.equal(calls[0].path, "/mcp/scope-app-private/http/scope-user-private");
  assert.equal(calls.slice(1).every((call) => call.authorization === "Bearer scope-key-private"), true);
  const serialized = JSON.stringify(result);
  assert.doesNotMatch(serialized, /scope-user-private|scope-app-private|scope-key-private/);
});

test("doctor reports scoped identity mismatches using booleans only", async (t) => {
  const baseUrl = await withServer(t, async (req, res) => {
    if (req.method === "GET") {
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify({
        user_id: "returned-user-private",
        client_name: "returned-app-private",
      }));
      return;
    }
    respondWithCompleteMcp(await readJson(req), res);
  });

  const result = await doctorRemote({
    url: `${baseUrl}/expected-app-private/http/expected-user-private`,
    apiKey: "mismatch-key-private",
    expectedScope: { userId: "expected-user-private", appId: "expected-app-private" },
    requireScope: true,
    timeoutMs: 2000,
  });

  assert.equal(result.ok, false);
  assert.equal(result.missing_tools.length, 0);
  assert.equal(result.scope_probe.response_valid, true);
  assert.equal(result.scope_probe.user_id_matches, false);
  assert.equal(result.scope_probe.app_id_matches, false);
  assert.equal(result.scope_probe.ok, false);
  assert.equal(Object.values(result.scope_probe).every((value) => typeof value === "boolean"), true);
  const serialized = JSON.stringify(result);
  for (const secret of [
    "returned-user-private",
    "returned-app-private",
    "expected-user-private",
    "expected-app-private",
    "mismatch-key-private",
  ]) {
    assert.equal(serialized.includes(secret), false);
  }
});

test("doctor fails safely when scope is required but no expected scope is configured", async (t) => {
  const methods = [];
  const url = await withServer(t, async (req, res) => {
    methods.push(req.method);
    respondWithCompleteMcp(await readJson(req), res);
  });

  const result = await doctorRemote({
    url,
    apiKey: "required-key-private",
    requireScope: true,
    timeoutMs: 2000,
  });

  assert.equal(result.ok, false);
  assert.deepEqual(result.scope_probe, {
    requested: false,
    required: true,
    attempted: false,
    skipped: true,
    response_valid: false,
    user_id_matches: false,
    app_id_matches: false,
    ok: false,
  });
  assert.equal(methods.includes("GET"), false);
  assert.equal(JSON.stringify(result).includes("required-key-private"), false);
});

test("doctor treats an incomplete expected scope as an unverified request without a GET", async (t) => {
  const methods = [];
  const url = await withServer(t, async (req, res) => {
    methods.push(req.method);
    respondWithCompleteMcp(await readJson(req), res);
  });

  const result = await doctorRemote({
    url,
    expectedScope: { userId: "partial-user-private" },
    timeoutMs: 2000,
  });

  assert.equal(result.ok, false);
  assert.equal(result.scope_probe.requested, true);
  assert.equal(result.scope_probe.required, false);
  assert.equal(result.scope_probe.attempted, false);
  assert.equal(result.scope_probe.skipped, true);
  assert.equal(result.scope_probe.ok, false);
  assert.equal(methods.includes("GET"), false);
  assert.equal(JSON.stringify(result).includes("partial-user-private"), false);
});

test("doctor handles a non-JSON scope response as a safe verification failure", async (t) => {
  const baseUrl = await withServer(t, async (req, res) => {
    if (req.method === "GET") {
      res.writeHead(200, { "content-type": "text/plain" });
      res.end("private-user private-app private-key");
      return;
    }
    respondWithCompleteMcp(await readJson(req), res);
  });

  const result = await doctorRemote({
    url: `${baseUrl}/private-app/http/private-user`,
    apiKey: "private-key",
    expectedScope: { userId: "private-user", appId: "private-app" },
    requireScope: true,
    timeoutMs: 2000,
  });

  assert.equal(result.ok, false);
  assert.equal(result.scope_probe.attempted, true);
  assert.equal(result.scope_probe.response_valid, false);
  assert.equal(result.scope_probe.ok, false);
  assert.doesNotMatch(JSON.stringify(result), /private-user|private-app|private-key/);
});

test("scope probe HTTP and network failures never echo credentials or scope values", async (t) => {
  const baseUrl = await withServer(t, async (_req, res) => {
    res.writeHead(403, { "content-type": "application/json" });
    res.end(JSON.stringify({
      detail: "scope-key-secret scope-user-secret scope-app-secret",
    }));
  });
  await assert.rejects(
    doctorRemote({
      url: `${baseUrl}/scope-app-secret/http/scope-user-secret`,
      apiKey: "scope-key-secret",
      expectedScope: { userId: "scope-user-secret", appId: "scope-app-secret" },
      timeoutMs: 2000,
    }),
    (error) => error instanceof ConfigError
      && /Scope probe returned HTTP 403/.test(error.message)
      && !/scope-key-secret|scope-user-secret|scope-app-secret/.test(error.message),
  );

  await assert.rejects(
    doctorRemote({
      url: "https://example.invalid/mcp/scope-app-secret/http/scope-user-secret",
      apiKey: "scope-key-secret",
      expectedScope: { userId: "scope-user-secret", appId: "scope-app-secret" },
      timeoutMs: 2000,
      fetchImpl: async () => {
        throw new Error("scope-key-secret scope-user-secret scope-app-secret");
      },
    }),
    (error) => error instanceof ConfigError
      && error.message === "Scope probe request failed.",
  );
});

test("doctor turns timeout and HTTP auth failures into safe errors", async (t) => {
  const url = await withServer(t, async (_req, res) => {
    res.writeHead(401, { "content-type": "application/json" });
    res.end('{"detail":"Bearer should-not-be-echoed"}');
  });
  await assert.rejects(
    doctorRemote({ url, apiKey: "should-not-be-echoed", timeoutMs: 1000 }),
    (error) => error instanceof ConfigError && /HTTP 401/.test(error.message) && !error.message.includes("should-not-be-echoed"),
  );
});

test("doctor redacts an API key reflected in server metadata and protocol", async (t) => {
  const apiKey = "metadata-secret-key";
  const url = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    if (body.method === "notifications/initialized") {
      res.writeHead(202).end();
      return;
    }
    res.setHeader("content-type", "application/json");
    if (body.method === "initialize") {
      res.end(JSON.stringify({
        jsonrpc: "2.0",
        id: body.id,
        result: {
          protocolVersion: `protocol-${apiKey}`,
          serverInfo: {
            name: `server-${apiKey}`,
            version: `version-${apiKey}`,
          },
        },
      }));
      return;
    }
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: body.id,
      result: { tools: REQUIRED_TOOLS.map((name) => ({ name })) },
    }));
  });

  const result = await doctorRemote({ url, apiKey, timeoutMs: 2000 });
  const serialized = JSON.stringify(result);
  assert.equal(result.ok, true);
  assert.equal(serialized.includes(apiKey), false);
  assert.match(result.protocol_version, /\[redacted\]/);
  assert.match(result.server_name, /\[redacted\]/);
  assert.match(result.server_version, /\[redacted\]/);
});

test("doctor redacts query value variants reflected alone in server metadata", async (t) => {
  const decodedQuerySecret = "metadata secret/value+plus";
  const rawQuerySecret = "metadata+secret%2Fvalue%2Bplus";
  const encodedQuerySecret = encodeURIComponent(decodedQuerySecret);
  const baseUrl = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    if (body.method === "notifications/initialized") {
      res.writeHead(202).end();
      return;
    }
    res.setHeader("content-type", "application/json");
    if (body.method === "initialize") {
      res.end(JSON.stringify({
        jsonrpc: "2.0",
        id: body.id,
        result: {
          protocolVersion: encodedQuerySecret,
          serverInfo: {
            name: decodedQuerySecret,
            version: rawQuerySecret,
          },
        },
      }));
      return;
    }
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: body.id,
      result: { tools: REQUIRED_TOOLS.map((name) => ({ name })) },
    }));
  });

  const result = await doctorRemote({
    url: `${baseUrl}?token=${rawQuerySecret}`,
    apiKey: "unrelated-api-key",
    timeoutMs: 2000,
  });
  const serialized = JSON.stringify(result);
  assert.equal(result.ok, true);
  for (const secret of [decodedQuerySecret, rawQuerySecret, encodedQuerySecret]) {
    assert.equal(serialized.includes(secret), false);
  }
  assert.equal(result.protocol_version, "[redacted]");
  assert.equal(result.server_name, "[redacted]");
  assert.equal(result.server_version, "[redacted]");
});

test("doctor keeps the negotiated protocol header separate from redacted display text", async (t) => {
  const protocolHeaders = [];
  const baseUrl = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    if (body.method !== "initialize") {
      protocolHeaders.push(req.headers["mcp-protocol-version"]);
    }
    if (body.method === "notifications/initialized") {
      res.writeHead(202).end();
      return;
    }
    res.setHeader("content-type", "application/json");
    if (body.method === "initialize") {
      res.end(JSON.stringify({
        jsonrpc: "2.0",
        id: body.id,
        result: {
          protocolVersion: "2025-06-18",
          serverInfo: { name: "forget-test", version: "1" },
        },
      }));
      return;
    }
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: body.id,
      result: { tools: REQUIRED_TOOLS.map((name) => ({ name })) },
    }));
  });

  const result = await doctorRemote({
    url: `${baseUrl}?mode=2`,
    timeoutMs: 2000,
  });

  assert.equal(result.ok, true);
  assert.deepEqual(protocolHeaders, ["2025-06-18", "2025-06-18"]);
  assert.match(result.protocol_version, /\[redacted\]/);
});

test("doctor redacts an API key reflected in JSON-RPC error code and message", async (t) => {
  const apiKey = "rpc-error-secret-key";
  const url = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: body.id,
      error: {
        code: `code-${apiKey}`,
        message: `message-${apiKey}`,
      },
    }));
  });

  await assert.rejects(
    doctorRemote({ url, apiKey, timeoutMs: 2000 }),
    (error) => error instanceof ConfigError
      && error.message.includes("[redacted]")
      && !error.message.includes(apiKey),
  );
});

test("doctor redacts query value variants reflected alone in JSON-RPC errors", async (t) => {
  const decodedQuerySecret = "rpc error/value+plus";
  const rawQuerySecret = "rpc+error%2Fvalue%2Bplus";
  const encodedQuerySecret = encodeURIComponent(decodedQuerySecret);
  const baseUrl = await withServer(t, async (req, res) => {
    const body = await readJson(req);
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: body.id,
      error: {
        code: rawQuerySecret,
        message: `${decodedQuerySecret}|${encodedQuerySecret}`,
      },
    }));
  });

  await assert.rejects(
    doctorRemote({
      url: `${baseUrl}?token=${rawQuerySecret}`,
      apiKey: "unrelated-api-key",
      timeoutMs: 2000,
    }),
    (error) => {
      if (!(error instanceof ConfigError) || !error.message.includes("[redacted]")) return false;
      return [decodedQuerySecret, rawQuerySecret, encodedQuerySecret]
        .every((secret) => !error.message.includes(secret));
    },
  );
});

test("doctor redacts an API key reflected in a mismatched response id", async (t) => {
  const apiKey = "response-id-secret-key";
  const url = await withServer(t, async (_req, res) => {
    res.setHeader("content-type", "application/json");
    res.end(JSON.stringify({
      jsonrpc: "2.0",
      id: `id-${apiKey}`,
      result: {},
    }));
  });

  await assert.rejects(
    doctorRemote({ url, apiKey, timeoutMs: 2000 }),
    (error) => error instanceof ConfigError
      && error.message.includes("[redacted]")
      && !error.message.includes(apiKey),
  );
});

test("doctor redacts query values from invalid URL request errors", async () => {
  const querySecret = "query-token-secret";
  const url = `https://[invalid.test/mcp?token=${querySecret}`;

  await assert.rejects(
    doctorRemote({
      url,
      apiKey: "different-api-key",
      timeoutMs: 2000,
      fetchImpl: async (requestUrl) => {
        throw new TypeError(`Failed to parse URL from ${requestUrl}`);
      },
    }),
    (error) => error instanceof ConfigError
      && error.message.includes("?redacted")
      && !error.message.includes(querySecret),
  );
});
