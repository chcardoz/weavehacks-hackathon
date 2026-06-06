from __future__ import annotations

from typing import Any

from keepalive.types import MetricSnapshot


def snap(step: int, loss: float | None = None, ts: float | None = None, **metrics: float) -> MetricSnapshot:
    data: dict[str, float] = dict(metrics)
    if loss is not None:
        data["loss"] = loss
    kwargs: dict[str, Any] = {"step": step, "metrics": data}
    if ts is not None:
        kwargs["timestamp"] = ts
    return MetricSnapshot(**kwargs)


class FakeRun:
    def __init__(self, step: int | None = None) -> None:
        self.logged: list[dict[str, Any]] = []
        if step is not None:
            self.step = step

    def log(self, data: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        self.logged.append(data)
        return "logged"
