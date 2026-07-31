"""forget — local-first memory system adapter for MemoryArena.

Unlike the hosted systems in this directory (mem0, letta, mirix, zep),
forget runs entirely on the machine under test: one local server, one
SQLite file, no API key and no network egress. Point FORGET_BASE_URL at
a running `forget-server` (default http://127.0.0.1:8000).

Scope: every MemoryArena task gets its own user_id, so tasks stay isolated
in exactly the way the product isolates users × apps.
"""

import os
import time
import uuid
from typing import Optional

import requests


class ForgetMemorySystem:
    def __init__(
        self,
        user_id: Optional[str] = None,
        base_url: Optional[str] = None,
        app_id: str = "memoryarena",
        top_k: int = 10,
        timeout: int = 60,
        index_wait: float = 1.5,
    ):
        self.base_url = (base_url or os.getenv("FORGET_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.user_id = user_id if user_id is not None else str(uuid.uuid4())
        self.app_id = app_id
        self.top_k = top_k
        self.timeout = timeout
        # Writes are gated and indexed asynchronously; a short settle keeps the
        # next turn's retrieval honest without polling internals.
        self.index_wait = index_wait
        self.session = requests.Session()

    # ---- MemoryArena memory-system protocol -------------------------------

    def add_chunk(self, chunk: str):
        payload = {
            "text": chunk,
            "user_id": self.user_id,
            "app_id": self.app_id,
        }
        response = self.session.post(
            f"{self.base_url}/v1/memories/", json=payload, timeout=self.timeout
        )
        response.raise_for_status()
        if self.index_wait:
            time.sleep(self.index_wait)
        return response.json()

    def wrap_user_prompt(self, prompt: str) -> str:
        payload = {
            "query": prompt,
            "user_id": self.user_id,
            "app_id": self.app_id,
            "top_k": self.top_k,
        }
        response = self.session.post(
            f"{self.base_url}/v1/memories/search/", json=payload, timeout=self.timeout
        )
        response.raise_for_status()
        results = response.json().get("results", [])

        lines = ["<memory_context>"]
        for item in results:
            text = item.get("memory")
            if not text:
                continue
            # Trust labels are part of what forget returns: green means
            # user-stated or tool-observed, yellow means agent-inferred.
            trust = ((item.get("metadata") or {}).get("trust") or {}).get("light")
            lines.append(f"{text} (trust: {trust})" if trust else text)
        lines.append("</memory_context>")
        lines.append(f"User Prompt: {prompt}")
        return "\n".join(lines)
