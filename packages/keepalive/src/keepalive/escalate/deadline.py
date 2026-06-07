from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from keepalive.types import HumanReply


class DeadlineClock:
    def __init__(self, redis_client: Any, key: str = "keepalive:deadlines") -> None:
        self.redis = redis_client
        self.key = key

    def arm(self, incident_id: str, timeout_s: float) -> float:
        deadline = time.time() + timeout_s
        self.redis.zadd(self.key, {incident_id: deadline})
        return deadline

    def due(self, now: float | None = None) -> list[str]:
        cutoff = now if now is not None else time.time()
        members = self.redis.zrangebyscore(self.key, "-inf", cutoff)
        return [m.decode() if isinstance(m, bytes) else str(m) for m in members]

    def disarm(self, incident_id: str) -> None:
        self.redis.zrem(self.key, incident_id)

    def await_human(
        self,
        incident_id: str,
        fetch_reply: Callable[[str], HumanReply | None],
        poll_interval: float = 2.0,
        now_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> HumanReply | None:
        score = self.redis.zscore(self.key, incident_id)
        deadline = float(score) if score is not None else now_fn()
        while True:
            reply = fetch_reply(incident_id)
            if reply is not None:
                self.disarm(incident_id)
                return reply
            if now_fn() >= deadline:
                self.disarm(incident_id)
                return None
            sleep_fn(poll_interval)
