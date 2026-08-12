"""forget-proxy — capture-only local passthrough proxy for the Anthropic API.

Why a proxy: the write path so far depends on the agent choosing to call
add_memory, or on a Claude-Code-only hook. An agent that is busy simply
doesn't record, and traffic from other tools (Cursor, raw SDK scripts)
never reaches us at all. Pointing a client's base URL here
(`ANTHROPIC_BASE_URL=http://127.0.0.1:8377`) turns every LLM call into an
out-of-band capture — no cooperation from the agent required.

Two hard rules, in priority order:
  * transparent — bytes in, bytes out. Requests and responses are relayed
    without modification (no injection; an explicit v0 non-goal). Streaming
    (SSE) and non-streaming are both relayed chunk-for-chunk as received.
  * fail-open — no capture error (disk full, bad JSON, unknown encoding)
    may block, alter, or delay the relay. Capture runs strictly after the
    last byte has been handed to the client, swallows every exception, and
    reports to stderr only.

Completed POST /v1/messages exchanges (2xx only) are appended as one JSON
line to ``~/.forget/proxy/stream/YYYY-MM-DD.jsonl``. Credential material
(x-api-key, authorization, any header at all) is never written to disk —
the capture record is built exclusively from the JSON bodies.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import socket
import sys
import time
import zlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .utils import utc_now

DEFAULT_UPSTREAM = "https://api.anthropic.com"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8377

# Hop-by-hop / transport headers the proxy owns; everything else passes through.
# content-length is recomputed by httpx from the identical body bytes.
_REQUEST_DROP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_RESPONSE_DROP = {"content-length", "transfer-encoding", "connection"}

# Above this the capture buffer is dropped (relay is unaffected) — the proxy
# must never turn a huge response into a memory problem for the client's call.
_CAPTURE_MAX_BYTES = 16 * 1024 * 1024


def forget_home() -> Path:
    return Path(os.environ.get("FORGET_HOME", Path.home() / ".forget"))


def proxy_stream_dir() -> Path:
    return forget_home() / "proxy" / "stream"


# ---------------------------------------------------------------------------
# capture — everything below runs after the relay completed and is fail-open


def _decode_body(data: bytes, content_encoding: str) -> bytes:
    """Undo transport compression for capture only — the relay already sent
    the raw bytes. Unknown encodings raise, which the caller swallows."""
    encoding = (content_encoding or "").strip().lower()
    if encoding in ("", "identity"):
        return data
    if encoding == "gzip":
        return gzip.decompress(data)
    if encoding == "deflate":
        try:
            return zlib.decompress(data)
        except zlib.error:
            return zlib.decompress(data, -zlib.MAX_WBITS)
    raise ValueError(f"unsupported content-encoding for capture: {encoding}")


def _iter_sse_json(text: str):
    """Yield the JSON payload of each SSE event. Non-JSON data and comment
    lines are skipped — capture tolerates anything the wire carried."""
    for raw_event in text.replace("\r\n", "\n").split("\n\n"):
        data_lines = [line[5:].strip() for line in raw_event.splitlines() if line.startswith("data:")]
        if not data_lines:
            continue
        try:
            yield json.loads("\n".join(data_lines))
        except ValueError:
            continue


def _assemble_stream(text: str) -> dict:
    """Fold a Messages-API SSE stream back into {model, content, usage}.

    message_start seeds model/usage/content; content_block_start opens a
    block; *_delta events append text/thinking/partial-json; message_delta
    carries the output-side usage. Mirrors the documented event sequence —
    unknown event types are ignored so future additions don't break capture.
    """
    model: str | None = None
    content: list[dict] = []
    usage: dict = {}
    partial_json: dict[int, str] = {}
    for event in _iter_sse_json(text):
        etype = event.get("type")
        if etype == "message_start":
            message = event.get("message") or {}
            model = message.get("model")
            usage.update(message.get("usage") or {})
            content = [dict(block) for block in (message.get("content") or [])]
        elif etype == "content_block_start":
            index = int(event.get("index", len(content)))
            while len(content) <= index:
                content.append({})
            content[index] = dict(event.get("content_block") or {})
        elif etype == "content_block_delta":
            index = int(event.get("index", 0))
            if index >= len(content):
                continue
            delta = event.get("delta") or {}
            dtype = delta.get("type")
            block = content[index]
            if dtype == "text_delta":
                block["text"] = block.get("text", "") + (delta.get("text") or "")
            elif dtype == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + (delta.get("thinking") or "")
            elif dtype == "input_json_delta":
                partial_json[index] = partial_json.get(index, "") + (delta.get("partial_json") or "")
            elif dtype == "signature_delta":
                block["signature"] = block.get("signature", "") + (delta.get("signature") or "")
        elif etype == "content_block_stop":
            index = int(event.get("index", 0))
            accumulated = partial_json.pop(index, None)
            if accumulated and index < len(content):
                try:
                    content[index]["input"] = json.loads(accumulated)
                except ValueError:
                    pass
        elif etype == "message_delta":
            usage.update(event.get("usage") or {})
    return {"model": model, "content": content, "usage": usage or None}


def _session_hint(request_json: dict) -> str | None:
    """Best-effort session identity: the client's metadata.user_id when
    present, else a fingerprint of the system prompt, else null."""
    metadata = request_json.get("metadata")
    if isinstance(metadata, dict):
        user_id = metadata.get("user_id")
        if isinstance(user_id, str) and user_id:
            return user_id
    system = request_json.get("system")
    if isinstance(system, str):
        text = system
    elif isinstance(system, list):
        text = "\n".join(
            block.get("text", "") for block in system if isinstance(block, dict)
        )
    else:
        text = ""
    if text.strip():
        return "sys-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return None


def _capture_exchange(
    capture_dir: Path | None,
    request_body: bytes,
    response_body: bytes,
    response_headers: httpx.Headers,
    latency_ms: int,
) -> None:
    """Append one capture line. Raises freely — the caller is the fail-open
    boundary. Only JSON bodies are read; headers never reach the record."""
    request_json = json.loads(request_body)
    decoded = _decode_body(response_body, response_headers.get("content-encoding", ""))
    if "text/event-stream" in response_headers.get("content-type", ""):
        assembled = _assemble_stream(decoded.decode("utf-8"))
    else:
        response_json = json.loads(decoded)
        assembled = {
            "model": response_json.get("model"),
            "content": response_json.get("content"),
            "usage": response_json.get("usage"),
        }
    record = {
        "ts": utc_now(),
        "session_hint": _session_hint(request_json),
        "model": assembled.get("model") or request_json.get("model"),
        "request_messages": request_json.get("messages"),
        "response_content": assembled.get("content"),
        "usage": assembled.get("usage"),
        "latency_ms": latency_ms,
    }
    directory = capture_dir if capture_dir is not None else proxy_stream_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# relay


def create_app(
    upstream: str = DEFAULT_UPSTREAM,
    capture_dir: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Build the proxy ASGI app.

    ``transport`` exists for tests (an in-process mock upstream); production
    leaves it None. ``capture_dir=None`` resolves to the live
    ``~/.forget/proxy/stream`` lazily, so FORGET_HOME is honored at runtime.
    """
    # No read timeout: SSE turns on hard tasks can legitimately run minutes.
    client = httpx.AsyncClient(
        base_url=upstream,
        transport=transport,
        timeout=httpx.Timeout(None, connect=10.0),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await client.aclose()

    # Docs routes disabled: every path belongs to the upstream, including /docs.
    app = FastAPI(title="forget-proxy", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        # The one deliberate carve-out from "every path belongs to the
        # upstream": the health watchdog needs an answer that proves *this*
        # process is alive, not the upstream. The Anthropic API namespace
        # lives under /v1/*, so nothing real is shadowed. Never captured,
        # never relayed, independent of the capture sink's health.
        return JSONResponse({"ok": True, "service": "forget-proxy"})

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def relay(request: Request, path: str) -> Response:
        started = time.monotonic()
        body = await request.body()
        if request.url.query:
            url = httpx.URL(path=request.url.path, query=request.url.query.encode("ascii"))
        else:
            url = httpx.URL(path=request.url.path)
        upstream_request = client.build_request(
            request.method,
            url,
            headers=[(k, v) for k, v in request.headers.items() if k.lower() not in _REQUEST_DROP],
            content=body,
        )
        try:
            upstream_response = await client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            # Upstream unreachable — the one case the proxy answers for itself.
            print(f"forget-proxy: upstream request failed: {exc}", file=sys.stderr, flush=True)
            return JSONResponse(
                {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"forget-proxy: upstream unreachable ({exc.__class__.__name__})",
                    },
                },
                status_code=502,
            )

        should_capture = (
            request.method == "POST"
            and request.url.path == "/v1/messages"
            and 200 <= upstream_response.status_code < 300
        )

        async def relay_bytes():
            buffer = bytearray()
            overflowed = False
            try:
                async for chunk in upstream_response.aiter_raw():
                    if should_capture and not overflowed:
                        buffer.extend(chunk)
                        if len(buffer) > _CAPTURE_MAX_BYTES:
                            overflowed = True
                            buffer.clear()
                    yield chunk
            finally:
                await upstream_response.aclose()
            # Reached only when the relay completed normally (a client
            # disconnect exits through the finally above and skips capture).
            if should_capture and not overflowed:
                try:
                    _capture_exchange(
                        capture_dir,
                        body,
                        bytes(buffer),
                        upstream_response.headers,
                        int((time.monotonic() - started) * 1000),
                    )
                except Exception as exc:  # noqa: BLE001 — fail-open by contract
                    print(
                        f"forget-proxy: capture skipped ({exc.__class__.__name__}: {exc}) — relay unaffected",
                        file=sys.stderr,
                        flush=True,
                    )

        headers = {
            k: v for k, v in upstream_response.headers.items() if k.lower() not in _RESPONSE_DROP
        }
        return StreamingResponse(
            relay_bytes(),
            status_code=upstream_response.status_code,
            headers=headers,
        )

    return app


# ---------------------------------------------------------------------------
# CLI


def _bind_or_exit(host: str, port: int) -> socket.socket:
    """Own the bind so failure is loud before anything hopeful prints
    (same rationale as forget-server's cold-install audit in cli.py)."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as exc:
        sock.close()
        sys.exit(
            f"forget-proxy: cannot listen on {host}:{port} — {exc.strerror or exc}.\n"
            f"  Is one already running?\n"
            f"  Or pick another port: forget-proxy --port {port + 1}"
        )
    sock.set_inheritable(True)
    return sock


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="forget-proxy",
        description="Capture-only local passthrough proxy for the Anthropic API. "
        "Relays every request untouched; appends completed /v1/messages "
        "exchanges to ~/.forget/proxy/stream/.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind address (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"listen port (default {DEFAULT_PORT})")
    parser.add_argument(
        "--upstream",
        default=DEFAULT_UPSTREAM,
        help=f"upstream base URL (default {DEFAULT_UPSTREAM})",
    )
    args = parser.parse_args(argv)

    try:
        import uvicorn
    except ImportError:
        sys.exit("uvicorn is not installed. Run: pip install 'forget-ai[server]'")

    stream_dir = proxy_stream_dir()
    try:
        stream_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Fail-open extends to startup: a broken capture dir degrades to
        # pure passthrough instead of refusing to serve.
        print(f"forget-proxy: capture dir unavailable ({exc}) — relaying without capture", file=sys.stderr)

    sock = _bind_or_exit(args.host, args.port)
    print(
        f"forget-proxy: {args.upstream} <- http://{args.host}:{args.port}  (capture: {stream_dir})",
        flush=True,
    )
    print(f"  ANTHROPIC_BASE_URL=http://{args.host}:{args.port} claude", flush=True)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(args.upstream, capture_dir=stream_dir),
            host=args.host,
            port=args.port,
            log_level="warning",
        )
    )
    server.run(sockets=[sock])
    if not server.started:
        sys.exit(3)


if __name__ == "__main__":
    main()
