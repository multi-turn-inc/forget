import { ConfigError } from "./core.js";

export const MCP_PROTOCOL_VERSION = "2025-06-18";
export const REQUIRED_TOOLS = [
  "search_memories",
  "add_memory",
  "assemble_context",
  "prepare_context_autopilot",
  "record_context_outcome",
  "record_task_state",
  "get_task_state",
  "catalog_search",
  "product_quote",
  "grant_create",
  "agent_consult",
  "receipt_verify",
  "grant_revoke",
];
export const CODEX_REQUIRED_TOOLS = [
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
];

function addSensitiveValueVariants(variants, value) {
  const raw = String(value ?? "");
  if (!raw) return;

  const decoded = new Set([raw]);
  for (const candidate of [raw, raw.replace(/\+/g, " ")]) {
    try {
      decoded.add(decodeURIComponent(candidate));
    } catch {
      // Keep the exact raw value even when it contains malformed escapes.
    }
  }

  for (const candidate of decoded) {
    if (!candidate) continue;
    variants.add(candidate);
    variants.add(encodeURIComponent(candidate));
    const formEncoded = new URLSearchParams([["value", candidate]])
      .toString()
      .slice("value=".length);
    variants.add(formEncoded);
  }
}

function requestSensitiveValues(url, apiKey) {
  const variants = new Set();
  addSensitiveValueVariants(variants, apiKey);

  const source = String(url ?? "");
  const queryStart = source.indexOf("?");
  if (queryStart !== -1) {
    const fragmentStart = source.indexOf("#", queryStart + 1);
    const query = source.slice(
      queryStart + 1,
      fragmentStart === -1 ? undefined : fragmentStart,
    );
    for (const field of query.split("&")) {
      const equals = field.indexOf("=");
      if (equals !== -1) addSensitiveValueVariants(variants, field.slice(equals + 1));
    }
  }

  return [...variants]
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
}

function redactSensitiveText(value, sensitiveValues = []) {
  let text = String(value ?? "");
  for (const variant of sensitiveValues) {
    text = text.split(variant).join("[redacted]");
  }
  return text.replace(/\b(https?:\/\/[^\s?]+)\?[^\s]*/gi, "$1?redacted");
}

function safeErrorMessage(value, sensitiveValues = []) {
  return redactSensitiveText(value || "Unknown MCP error", sensitiveValues)
    .replace(/[\u0000-\u001f\u007f-\u009f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 240);
}

function safeServerText(value, fallback = "unknown", sensitiveValues = []) {
  const text = redactSensitiveText(value || "", sensitiveValues)
    .replace(/[\u0000-\u001f\u007f-\u009f]+/g, "")
    .trim()
    .slice(0, 120);
  return text || fallback;
}

function safeProtocolHeader(value, fallback = MCP_PROTOCOL_VERSION) {
  const text = String(value || "")
    .replace(/[\u0000-\u001f\u007f-\u009f]+/g, "")
    .trim()
    .slice(0, 120);
  return text || fallback;
}

function jsonRpcError(payload, method, sensitiveValues) {
  if (!payload || typeof payload !== "object") {
    throw new ConfigError(`MCP ${method} returned an invalid response.`);
  }
  if (payload.error) {
    const code = safeServerText(payload.error.code, "unknown", sensitiveValues);
    const message = safeErrorMessage(payload.error.message, sensitiveValues);
    throw new ConfigError(`MCP ${method} error ${code}: ${message}`);
  }
  return payload;
}

function matchingSsePayload(frame, requestId, method, sensitiveValues) {
  const dataLines = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (!dataLines.length) return null;
  let payload;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  if (payload.id !== requestId) return null;
  return jsonRpcError(payload, method, sensitiveValues);
}

async function parseSseResponse(response, requestId, method, sensitiveValues) {
  if (!response.body || typeof response.body.getReader !== "function") {
    throw new ConfigError(`MCP ${method} returned an unreadable event stream.`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() || "";
      for (const frame of frames) {
        const payload = matchingSsePayload(frame, requestId, method, sensitiveValues);
        if (payload) {
          await reader.cancel().catch(() => {});
          return payload;
        }
      }
      if (done) {
        const payload = matchingSsePayload(buffer, requestId, method, sensitiveValues);
        if (payload) return payload;
        break;
      }
    }
  } finally {
    reader.releaseLock();
  }
  throw new ConfigError(`MCP ${method} event stream ended without response id ${requestId}.`);
}

async function parseRpcResponse(response, requestId, method, sensitiveValues) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.toLowerCase().includes("text/event-stream")) {
    return parseSseResponse(response, requestId, method, sensitiveValues);
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new ConfigError(`MCP ${method} did not return JSON or an event stream.`);
  }
  if (payload.id !== requestId) {
    throw new ConfigError(
      `MCP ${method} returned response id ${safeServerText(payload.id, "unknown", sensitiveValues)} instead of ${requestId}.`,
    );
  }
  return jsonRpcError(payload, method, sensitiveValues);
}

async function postMcp({
  url,
  apiKey,
  sensitiveValues,
  payload,
  requestId,
  method,
  sessionId = "",
  protocolVersion = "",
  timeoutMs,
  fetchImpl,
  notification = false,
}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = {
    Accept: "application/json, text/event-stream",
    "Content-Type": "application/json",
  };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  if (protocolVersion) headers["MCP-Protocol-Version"] = protocolVersion;
  if (sessionId) headers["Mcp-Session-Id"] = sessionId;

  try {
    const response = await fetchImpl(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
      redirect: "error",
    });
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      throw new ConfigError(`MCP ${method} returned HTTP ${response.status}.`);
    }
    const returnedSessionId = response.headers.get("mcp-session-id") || sessionId;
    if (notification) {
      await response.body?.cancel().catch(() => {});
      return { payload: null, sessionId: returnedSessionId };
    }
    return {
      payload: await parseRpcResponse(response, requestId, method, sensitiveValues),
      sessionId: returnedSessionId,
    };
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new ConfigError(`MCP ${method} timed out after ${timeoutMs} ms.`);
    }
    if (error instanceof ConfigError) throw error;
    throw new ConfigError(`MCP ${method} request failed: ${safeErrorMessage(error?.message, sensitiveValues)}`);
  } finally {
    clearTimeout(timer);
  }
}

function emptyScopeProbe({ requested, required, ok }) {
  return {
    requested: Boolean(requested),
    required: Boolean(required),
    attempted: false,
    skipped: true,
    response_valid: false,
    user_id_matches: false,
    app_id_matches: false,
    ok: Boolean(ok),
  };
}

async function probeScope({
  url,
  apiKey,
  expectedScope,
  requireScope,
  timeoutMs,
  fetchImpl,
}) {
  const requested = Boolean(expectedScope);
  const expectedUserId = typeof expectedScope?.userId === "string"
    ? expectedScope.userId
    : "";
  const expectedAppId = typeof expectedScope?.appId === "string"
    ? expectedScope.appId
    : "";
  const hasExpectedScope = Boolean(expectedUserId && expectedAppId);

  if (!hasExpectedScope) {
    return emptyScopeProbe({
      requested,
      required: requireScope,
      ok: !requireScope && !requested,
    });
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = { Accept: "application/json" };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;

  try {
    const response = await fetchImpl(url, {
      method: "GET",
      headers,
      signal: controller.signal,
      redirect: "error",
    });
    if (!response.ok) {
      await response.body?.cancel().catch(() => {});
      throw new ConfigError(`Scope probe returned HTTP ${response.status}.`);
    }

    let payload;
    try {
      payload = await response.json();
    } catch {
      return {
        requested: true,
        required: Boolean(requireScope),
        attempted: true,
        skipped: false,
        response_valid: false,
        user_id_matches: false,
        app_id_matches: false,
        ok: false,
      };
    }

    const responseValid = Boolean(
      payload
      && typeof payload === "object"
      && !Array.isArray(payload)
      && typeof payload.user_id === "string"
      && typeof payload.client_name === "string"
    );
    const userIdMatches = responseValid && payload.user_id === expectedUserId;
    const appIdMatches = responseValid && payload.client_name === expectedAppId;
    return {
      requested: true,
      required: Boolean(requireScope),
      attempted: true,
      skipped: false,
      response_valid: responseValid,
      user_id_matches: userIdMatches,
      app_id_matches: appIdMatches,
      ok: userIdMatches && appIdMatches,
    };
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new ConfigError(`Scope probe timed out after ${timeoutMs} ms.`);
    }
    if (error instanceof ConfigError) throw error;
    throw new ConfigError("Scope probe request failed.");
  } finally {
    clearTimeout(timer);
  }
}

export async function doctorRemote({
  url,
  apiKey = "",
  timeoutMs = 10000,
  fetchImpl = globalThis.fetch,
  requiredTools = REQUIRED_TOOLS,
  clientVersion = "0.1.0",
  expectedScope = null,
  requireScope = false,
} = {}) {
  if (typeof fetchImpl !== "function") {
    throw new ConfigError("Node.js 18 or newer is required for the MCP doctor.");
  }
  const sensitiveValues = requestSensitiveValues(url, apiKey);
  const scopeProbe = await probeScope({
    url,
    apiKey,
    expectedScope,
    requireScope,
    timeoutMs,
    fetchImpl,
  });
  const initialize = await postMcp({
    url,
    apiKey,
    sensitiveValues,
    payload: {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: "forget-connect", version: clientVersion },
      },
    },
    requestId: 1,
    method: "initialize",
    timeoutMs,
    fetchImpl,
  });
  const result = initialize.payload.result || {};
  const negotiatedProtocolVersion = safeProtocolHeader(
    result.protocolVersion || MCP_PROTOCOL_VERSION,
    MCP_PROTOCOL_VERSION,
  );
  const protocolVersion = safeServerText(
    negotiatedProtocolVersion,
    MCP_PROTOCOL_VERSION,
    sensitiveValues,
  );
  let sessionId = initialize.sessionId || "";

  const notified = await postMcp({
    url,
    apiKey,
    sensitiveValues,
    payload: { jsonrpc: "2.0", method: "notifications/initialized" },
    method: "notifications/initialized",
    sessionId,
    protocolVersion: negotiatedProtocolVersion,
    timeoutMs,
    fetchImpl,
    notification: true,
  });
  sessionId = notified.sessionId || sessionId;

  const toolNameSet = new Set();
  const seenCursors = new Set();
  let cursor = "";
  let toolPageCount = 0;
  while (true) {
    toolPageCount += 1;
    if (toolPageCount > 100) {
      throw new ConfigError("MCP tools/list exceeded the 100-page safety limit.");
    }
    const requestId = toolPageCount + 1;
    const listed = await postMcp({
      url,
      apiKey,
      sensitiveValues,
      payload: {
        jsonrpc: "2.0",
        id: requestId,
        method: "tools/list",
        params: cursor ? { cursor } : {},
      },
      requestId,
      method: "tools/list",
      sessionId,
      protocolVersion: negotiatedProtocolVersion,
      timeoutMs,
      fetchImpl,
    });
    sessionId = listed.sessionId || sessionId;
    const tools = Array.isArray(listed.payload.result?.tools)
      ? listed.payload.result.tools
      : [];
    for (const tool of tools) {
      if (tool && typeof tool.name === "string" && tool.name) {
        toolNameSet.add(tool.name);
      }
    }
    const nextCursor = listed.payload.result?.nextCursor;
    if (nextCursor === undefined || nextCursor === null || nextCursor === "") break;
    if (typeof nextCursor !== "string") {
      throw new ConfigError("MCP tools/list returned an invalid nextCursor.");
    }
    if (seenCursors.has(nextCursor)) {
      throw new ConfigError("MCP tools/list returned a repeated nextCursor.");
    }
    seenCursors.add(nextCursor);
    cursor = nextCursor;
  }
  const toolNames = [...toolNameSet].sort();
  const missingTools = requiredTools.filter((name) => !toolNames.includes(name));
  return {
    ok: missingTools.length === 0 && scopeProbe.ok,
    server_name: safeServerText(result.serverInfo?.name, "unknown", sensitiveValues),
    server_version: safeServerText(result.serverInfo?.version, "unknown", sensitiveValues),
    protocol_version: protocolVersion,
    session_negotiated: Boolean(sessionId),
    tool_page_count: toolPageCount,
    tool_count: toolNames.length,
    required_tools: [...requiredTools],
    missing_tools: missingTools,
    scope_probe: scopeProbe,
  };
}
