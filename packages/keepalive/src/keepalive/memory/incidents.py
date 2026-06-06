from __future__ import annotations

import asyncio
import os
from typing import Any

from keepalive.config import Settings
from keepalive.types import FailureEvent, Incident


class IncidentMemory:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self._injected = client

    @property
    def available(self) -> bool:
        if self._injected is not None:
            return True
        try:
            import agent_memory_client  # noqa: F401
        except Exception:
            return False
        return True

    def _client(self) -> Any | None:
        if self._injected is not None:
            return self._injected
        try:
            from agent_memory_client import MemoryAPIClient, MemoryClientConfig

            base_url = os.environ.get("AGENT_MEMORY_URL", "http://localhost:8000")
            return MemoryAPIClient(MemoryClientConfig(base_url=base_url, default_namespace="keepalive"))
        except Exception:
            return None

    @staticmethod
    def _drive(coro: Any) -> None:
        try:
            asyncio.run(coro)
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(coro)
            except Exception:
                pass
        except Exception:
            pass

    def remember(self, incident: Incident, resolution: str) -> None:
        client = self._client()
        if client is None:
            return
        try:
            failure = incident.failure
            summary = incident.diagnosis.summary if incident.diagnosis is not None else "n/a"
            category = incident.diagnosis.category if incident.diagnosis is not None else str(failure.kind)
            text = (
                f"Failure {failure.kind} at step {failure.step} in run {incident.run.run_id}: "
                f"{failure.message}. Diagnosis: {summary}. Resolution: {resolution}."
            )
            records = [
                {
                    "text": text,
                    "memory_type": "episodic",
                    "topics": [str(failure.kind), str(category)],
                }
            ]
            self._drive(client.create_long_term_memory(records))
        except Exception:
            pass

    def recall(self, failure: FailureEvent) -> list[str]:
        client = self._client()
        if client is None:
            return []
        try:
            query = f"{failure.kind} {failure.message}"
            result = asyncio.run(client.search_long_term_memory(text=query, limit=3))
            return _extract_texts(result)
        except Exception:
            return []


def _extract_texts(result: Any) -> list[str]:
    items = getattr(result, "memories", None)
    if items is None and isinstance(result, dict):
        items = result.get("memories")
    if items is None:
        items = result
    texts: list[str] = []
    for item in items or []:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item.get("text")
        if isinstance(text, str):
            texts.append(text)
    return texts
