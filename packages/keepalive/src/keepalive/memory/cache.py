from __future__ import annotations

import contextlib
from typing import Any


class DiagnosisCache:
    def __init__(self, redis_url: str, cache: Any | None = None) -> None:
        self.redis_url = redis_url
        self._injected = cache

    def _cache(self) -> Any | None:
        if self._injected is not None:
            return self._injected
        try:
            from redisvl.extensions.llmcache import SemanticCache  # pyright: ignore[reportMissingImports]

            self._injected = SemanticCache(
                name="keepalive:diagcache",
                redis_url=self.redis_url,
                distance_threshold=0.1,
            )
            return self._injected
        except Exception:
            return None

    def get(self, prompt: str) -> str | None:
        cache = self._cache()
        if cache is None:
            return None
        try:
            hits = cache.check(prompt=prompt)
            if hits:
                return hits[0].get("response")
            return None
        except Exception:
            return None

    def set(self, prompt: str, response: str) -> None:
        cache = self._cache()
        if cache is None:
            return
        with contextlib.suppress(Exception):
            cache.store(prompt=prompt, response=response)
