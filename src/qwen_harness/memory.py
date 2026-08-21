from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .contracts import EvidenceSpan


class Memory(Protocol):
    def retrieve(self, session: str, prompt: str, token_budget: int = 800) -> tuple[EvidenceSpan, ...]: ...
    def ingest(self, session: str, role: str, content: str) -> None: ...


class NullMemory:
    def retrieve(self, session: str, prompt: str, token_budget: int = 800) -> tuple[EvidenceSpan, ...]:
        return ()

    def ingest(self, session: str, role: str, content: str) -> None:
        return None


@dataclass
class ToamMemory:
    base_url: str = "http://127.0.0.1:8810"
    timeout: float = 5.0

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def retrieve(self, session: str, prompt: str, token_budget: int = 800) -> tuple[EvidenceSpan, ...]:
        payload = self._post("/retrieve", {"session": session, "prompt": prompt, "token_budget": token_budget})
        injection = str(payload.get("injection", "")).strip()
        if not injection:
            return ()
        digest = hashlib.sha256(injection.encode("utf-8")).hexdigest()
        return (EvidenceSpan("toam-memory", injection, digest, "recalled-untrusted"),)

    def ingest(self, session: str, role: str, content: str) -> None:
        self._post("/ingest", {"session": session, "kind": "turn", "role": role, "content": content})

    def record_event(self, session: str, kind: str, value: dict) -> dict:
        """Append a canonical typed event to the durable TOAM ledger."""
        return self._post(
            "/ingest",
            {
                "session": session,
                "kind": kind,
                "role": "harness",
                "content": json.dumps(value, sort_keys=True, separators=(",", ":")),
            },
        )
