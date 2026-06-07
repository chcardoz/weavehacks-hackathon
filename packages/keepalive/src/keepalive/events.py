from __future__ import annotations

import json
from typing import Any


class EventBus:
    def __init__(
        self,
        redis_client: Any,
        stream: str = "keepalive:events",
        group: str = "keepalive",
    ) -> None:
        self.redis = redis_client
        self.stream = stream
        self.group = group

    def publish(self, event_type: str, payload: dict[str, Any]) -> str:
        entry = {"type": event_type, "data": json.dumps(payload)}
        return self.redis.xadd(self.stream, entry)

    def ensure_group(self) -> None:
        try:
            self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def consume(
        self,
        consumer: str = "watchdog",
        count: int = 10,
        block_ms: int = 1000,
    ) -> list[tuple[str, dict[str, Any]]]:
        response = self.redis.xreadgroup(
            self.group,
            consumer,
            {self.stream: ">"},
            count=count,
            block=block_ms,
        )
        out: list[tuple[str, dict[str, Any]]] = []
        if not response:
            return out
        for _stream, entries in response:
            for entry_id, fields in entries:
                payload = self._decode(fields)
                out.append((self._as_str(entry_id), payload))
        return out

    def ack(self, *ids: str) -> None:
        if ids:
            self.redis.xack(self.stream, self.group, *ids)

    @staticmethod
    def _as_str(value: Any) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)

    def _decode(self, fields: dict[Any, Any]) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for key, value in fields.items():
            decoded[self._as_str(key)] = self._as_str(value)
        payload: dict[str, Any] = {}
        if "data" in decoded:
            try:
                payload = json.loads(decoded["data"])
            except (json.JSONDecodeError, TypeError):
                payload = {}
        if "type" in decoded:
            payload["type"] = decoded["type"]
        return payload
