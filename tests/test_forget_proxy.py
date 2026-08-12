"""forget-proxy v0 contract tests — passthrough fidelity, SSE assembly, fail-open.

The proxy and the mock upstream both run in-process: the proxy app talks to
the upstream through an injected httpx transport, and the tests talk to the
proxy through httpx.ASGITransport. No sockets, no uvicorn.

(Named test_forget_proxy.py, not test_proxy.py — conftest's
OPTIONAL_TEST_MODULES would silently skip the latter without litellm/openai.)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from forget.proxy import create_app

SECRET_API_KEY = "sk-ant-api03-test-secret-key"
SECRET_BEARER = "Bearer oauth-test-secret-token"


class _BodyStream(httpx.AsyncByteStream):
    """Serve a canned body in explicit chunks so the relay is exercised as a
    stream, not a single buffer."""

    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        pass


class _UpstreamTransport(httpx.AsyncBaseTransport):
    """Mock upstream: records every forwarded request, returns via responder."""

    def __init__(self, responder):
        self._responder = responder
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responder(request)


def _proxy_client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy.test")


def _capture_lines(capture_dir) -> list[dict]:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = capture_dir / f"{day}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# Deliberately quirky whitespace: byte-identity fails if the proxy re-serializes.
NON_STREAM_BODY = (
    b'{"id": "msg_01",  "model":"claude-opus-5",\n'
    b' "content": [{"type": "text", "text": "\xed\x95\x9c\xea\xb8\x80 ok"}],\n'
    b' "usage": {"input_tokens": 11, "output_tokens": 7}}'
)

REQUEST_BODY = {
    "model": "claude-opus-5",
    "max_tokens": 64,
    "metadata": {"user_id": "session-hint-abc"},
    "messages": [{"role": "user", "content": "안녕"}],
}


@pytest.mark.asyncio
async def test_non_streaming_passthrough_bytes_and_capture(tmp_path):
    upstream = _UpstreamTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/json", "anthropic-request-id": "req_test_1"},
            stream=_BodyStream([NON_STREAM_BODY[:20], NON_STREAM_BODY[20:]]),
            request=request,
        )
    )
    app = create_app("https://upstream.test", capture_dir=tmp_path, transport=upstream)
    raw_request = json.dumps(REQUEST_BODY, ensure_ascii=False).encode("utf-8")

    async with _proxy_client(app) as client:
        response = await client.post(
            "/v1/messages",
            content=raw_request,
            headers={"content-type": "application/json", "x-api-key": SECRET_API_KEY},
        )

    # Relay: status, body bytes, and upstream headers pass through untouched.
    assert response.status_code == 200
    assert response.content == NON_STREAM_BODY
    assert response.headers["anthropic-request-id"] == "req_test_1"

    # Upstream saw the exact request bytes and the credential it needs.
    forwarded = upstream.requests[0]
    assert forwarded.content == raw_request
    assert forwarded.headers["x-api-key"] == SECRET_API_KEY
    assert forwarded.method == "POST"
    assert forwarded.url.path == "/v1/messages"

    # Capture: one line, the spec'd fields, built from bodies only.
    lines = _capture_lines(tmp_path)
    assert len(lines) == 1
    record = lines[0]
    assert record["model"] == "claude-opus-5"
    assert record["session_hint"] == "session-hint-abc"
    assert record["request_messages"] == REQUEST_BODY["messages"]
    assert record["response_content"] == [{"type": "text", "text": "한글 ok"}]
    assert record["usage"] == {"input_tokens": 11, "output_tokens": 7}
    assert isinstance(record["latency_ms"], int) and record["latency_ms"] >= 0
    assert record["ts"]


def _sse(event: str, payload: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


SSE_BODY = b"".join(
    [
        _sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_02",
                    "model": "claude-opus-5",
                    "content": [],
                    "usage": {"input_tokens": 10, "output_tokens": 1},
                },
            },
        ),
        _sse(
            "content_block_start",
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ),
        _sse(
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}},
        ),
        _sse("ping", {"type": "ping"}),
        _sse(
            "content_block_delta",
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}},
        ),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        _sse(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "id": "toolu_01", "name": "get_weather", "input": {}},
            },
        ),
        _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"city": "Se'},
            },
        ),
        _sse(
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": 'oul"}'},
            },
        ),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 1}),
        _sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 23},
            },
        ),
        _sse("message_stop", {"type": "message_stop"}),
    ]
)


@pytest.mark.asyncio
async def test_sse_streaming_relay_and_assembled_capture(tmp_path):
    # Chunk boundaries cut mid-event on purpose: relay must not care, and
    # capture must reassemble from the accumulated bytes.
    chunks = [SSE_BODY[i : i + 97] for i in range(0, len(SSE_BODY), 97)]
    upstream = _UpstreamTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=_BodyStream(chunks),
            request=request,
        )
    )
    app = create_app("https://upstream.test", capture_dir=tmp_path, transport=upstream)

    async with _proxy_client(app) as client:
        response = await client.post(
            "/v1/messages",
            json={"model": "claude-opus-5", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
            headers={"x-api-key": SECRET_API_KEY},
        )

    assert response.status_code == 200
    assert response.content == SSE_BODY  # byte-faithful SSE relay
    assert response.headers["content-type"].startswith("text/event-stream")

    lines = _capture_lines(tmp_path)
    assert len(lines) == 1
    record = lines[0]
    assert record["model"] == "claude-opus-5"
    assert record["response_content"] == [
        {"type": "text", "text": "Hello"},
        {"type": "tool_use", "id": "toolu_01", "name": "get_weather", "input": {"city": "Seoul"}},
    ]
    assert record["usage"] == {"input_tokens": 10, "output_tokens": 23}
    # No metadata and no system prompt in the request → hint is null.
    assert record["session_hint"] is None


@pytest.mark.asyncio
async def test_capture_sink_error_is_fail_open(tmp_path, capsys):
    # capture_dir points at a *file*, so mkdir() inside the sink raises.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    upstream = _UpstreamTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=_BodyStream([NON_STREAM_BODY]),
            request=request,
        )
    )
    app = create_app("https://upstream.test", capture_dir=blocked, transport=upstream)

    async with _proxy_client(app) as client:
        response = await client.post("/v1/messages", json=REQUEST_BODY)

    # The relay is untouched by the sink failure.
    assert response.status_code == 200
    assert response.content == NON_STREAM_BODY
    assert "capture skipped" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_credential_headers_never_reach_capture_file(tmp_path):
    upstream = _UpstreamTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=_BodyStream([NON_STREAM_BODY]),
            request=request,
        )
    )
    app = create_app("https://upstream.test", capture_dir=tmp_path, transport=upstream)

    async with _proxy_client(app) as client:
        response = await client.post(
            "/v1/messages",
            json=REQUEST_BODY,
            headers={"x-api-key": SECRET_API_KEY, "authorization": SECRET_BEARER},
        )
    assert response.status_code == 200

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    text = (tmp_path / f"{day}.jsonl").read_text(encoding="utf-8")
    assert SECRET_API_KEY not in text
    assert SECRET_BEARER not in text
    assert "x-api-key" not in text
    assert "authorization" not in text


@pytest.mark.asyncio
async def test_upstream_errors_and_other_paths_pass_through_uncaptured(tmp_path):
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                stream=_BodyStream([b'{"data": []}']),
                request=request,
            )
        return httpx.Response(
            429,
            headers={"content-type": "application/json", "retry-after": "7"},
            stream=_BodyStream([b'{"type":"error","error":{"type":"rate_limit_error","message":"slow down"}}']),
            request=request,
        )

    upstream = _UpstreamTransport(responder)
    app = create_app("https://upstream.test", capture_dir=tmp_path, transport=upstream)

    async with _proxy_client(app) as client:
        # Non-/v1/messages path relays as-is.
        models = await client.get("/v1/models?limit=5")
        # Upstream error status relays as-is.
        limited = await client.post("/v1/messages", json=REQUEST_BODY)

    assert models.status_code == 200
    assert models.content == b'{"data": []}'
    assert upstream.requests[0].url.query == b"limit=5"
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "7"
    assert b"rate_limit_error" in limited.content

    # Neither exchange was a completed 2xx /v1/messages → nothing captured.
    assert _capture_lines(tmp_path) == []
