from __future__ import annotations

from typing import Any

_ROUTES: dict[str, list[str]] = {
    "divergence": ["loss exploded", "loss is NaN", "gradient overflow", "loss increasing rapidly"],
    "thermal": ["GPU temperature high", "thermal throttling", "fan speed", "overheating"],
    "dataloader": ["dataloader worker killed", "dataset corrupt sample", "input pipeline stalled", "tokenizer error"],
    "oom": ["CUDA out of memory", "OOM killed", "allocation failed"],
}


class SignalRouter:
    def __init__(self, redis_url: str, router: Any | None = None) -> None:
        self.redis_url = redis_url
        self._injected = router

    def _router(self) -> Any | None:
        if self._injected is not None:
            return self._injected
        try:
            from redisvl.extensions.router import Route, SemanticRouter

            routes = [Route(name=name, references=refs) for name, refs in _ROUTES.items()]
            self._injected = SemanticRouter(
                name="keepalive-signals",
                routes=routes,
                redis_url=self.redis_url,
                overwrite=False,
            )
            return self._injected
        except Exception:
            return None

    def classify(self, text: str) -> str | None:
        router = self._router()
        if router is None:
            return None
        try:
            route_match = router(text)
            name = getattr(route_match, "name", None)
            return name if name else None
        except Exception:
            return None
