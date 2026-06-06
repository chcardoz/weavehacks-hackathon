from __future__ import annotations

import collections
import math
import re
from collections.abc import Sequence

from keepalive.types import FailureEvent, FailureKind, MetricSnapshot


def _finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


class NaNLossDetector:
    name = "nan_loss"

    def __init__(self, loss_key: str = "loss") -> None:
        self.loss_key = loss_key

    def check(self, snapshot: MetricSnapshot, history: Sequence[MetricSnapshot]) -> FailureEvent | None:
        loss = snapshot.metrics.get(self.loss_key)
        if loss is None:
            return None
        if math.isnan(loss) or math.isinf(loss):
            sign = "NaN" if math.isnan(loss) else ("+Inf" if loss > 0 else "-Inf")
            return FailureEvent(
                kind=FailureKind.NAN_LOSS,
                step=snapshot.step,
                message=f"{self.loss_key} became {sign} at step {snapshot.step}",
                metrics=dict(snapshot.metrics),
                timestamp=snapshot.timestamp,
            )
        return None


class DivergenceDetector:
    name = "divergence"

    def __init__(
        self,
        loss_key: str = "loss",
        window: int = 20,
        factor: float = 2.5,
        min_history: int = 20,
    ) -> None:
        self.loss_key = loss_key
        self.window = window
        self.factor = factor
        self.min_history = min_history

    def check(self, snapshot: MetricSnapshot, history: Sequence[MetricSnapshot]) -> FailureEvent | None:
        losses = [
            s.metrics[self.loss_key]
            for s in history
            if self.loss_key in s.metrics and _finite(s.metrics[self.loss_key])
        ]
        if len(losses) < self.min_history or len(losses) < self.window:
            return None

        best_window_mean = math.inf
        for start in range(0, len(losses) - self.window + 1):
            chunk = losses[start : start + self.window]
            mean = sum(chunk) / self.window
            if mean < best_window_mean:
                best_window_mean = mean

        recent_mean = sum(losses[-self.window :]) / self.window
        if best_window_mean > 0 and recent_mean > self.factor * best_window_mean:
            return FailureEvent(
                kind=FailureKind.DIVERGENCE,
                step=snapshot.step,
                message=(
                    f"{self.loss_key} diverging: recent {self.window}-mean {recent_mean:.4g} "
                    f"exceeds {self.factor}x best {best_window_mean:.4g}"
                ),
                metrics=dict(snapshot.metrics),
                timestamp=snapshot.timestamp,
            )
        return None


class StallDetector:
    name = "stall"

    def __init__(self, timeout_s: float = 300.0) -> None:
        self.timeout_s = timeout_s

    def check_idle(self, now: float, last: MetricSnapshot | None) -> FailureEvent | None:
        if last is None:
            return None
        idle = now - last.timestamp
        if idle > self.timeout_s:
            return FailureEvent(
                kind=FailureKind.STALL,
                step=last.step,
                message=f"no metrics for {idle:.0f}s (> {self.timeout_s:.0f}s) since step {last.step}",
                metrics=dict(last.metrics),
                timestamp=now,
            )
        return None


_OOM_PATTERNS = [
    re.compile(r"CUDA out of memory", re.IGNORECASE),
    re.compile(r"OutOfMemoryError"),
    re.compile(r"CUBLAS_STATUS_ALLOC_FAILED"),
]

_EXCEPTION_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"Segmentation fault", re.IGNORECASE),
    re.compile(r"\bKilled\b"),
]


def scan_logline(line: str, step: int = -1) -> FailureEvent | None:
    for pattern in _OOM_PATTERNS:
        if pattern.search(line):
            return FailureEvent(
                kind=FailureKind.OOM,
                step=step,
                message=f"OOM detected in log: {line.strip()}",
            )
    for pattern in _EXCEPTION_PATTERNS:
        if pattern.search(line):
            return FailureEvent(
                kind=FailureKind.EXCEPTION,
                step=step,
                message=f"fatal error in log: {line.strip()}",
            )
    return None


class DetectorSuite:
    def __init__(
        self,
        detectors: Sequence[object] | None = None,
        stall: StallDetector | None = None,
        max_history: int = 2000,
    ) -> None:
        self.detectors = list(detectors) if detectors is not None else [NaNLossDetector(), DivergenceDetector()]
        self.stall = stall if stall is not None else StallDetector()
        self._history: collections.deque[MetricSnapshot] = collections.deque(maxlen=max_history)
        self.tripped = False

    @property
    def history(self) -> list[MetricSnapshot]:
        return list(self._history)

    def reset(self) -> None:
        self.tripped = False

    def observe(self, snapshot: MetricSnapshot) -> FailureEvent | None:
        self._history.append(snapshot)
        if self.tripped:
            return None
        for detector in self.detectors:
            event = detector.check(snapshot, self._history)  # type: ignore[attr-defined]
            if event is not None:
                self.tripped = True
                return event
        return None

    def idle_check(self, now: float | None = None) -> FailureEvent | None:
        if self.tripped:
            return None
        import time

        last = self._history[-1] if self._history else None
        event = self.stall.check_idle(time.time() if now is None else now, last)
        if event is not None:
            self.tripped = True
        return event

    def scan_logline(self, line: str, step: int = -1) -> FailureEvent | None:
        if self.tripped:
            return None
        event = scan_logline(line, step)
        if event is not None:
            self.tripped = True
        return event
