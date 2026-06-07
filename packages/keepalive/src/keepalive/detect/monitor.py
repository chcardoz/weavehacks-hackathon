from __future__ import annotations

import contextlib
import numbers
from collections.abc import Callable
from typing import Any

from keepalive.detect.rules import DetectorSuite
from keepalive.types import FailureEvent, FailureKind, KeepaliveError, MetricSnapshot


def _is_numeric(value: Any) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _oom_event(step: int, message: str) -> FailureEvent:
    return FailureEvent(kind=FailureKind.OOM, step=step, message=message)


class MetricHook:
    def __init__(
        self,
        suite: DetectorSuite,
        on_failure: Callable[[FailureEvent], None],
        *,
        on_metrics: Callable[[int, dict[str, float]], None] | None = None,
        injector: Any | None = None,
    ) -> None:
        self.suite = suite
        self.on_failure = on_failure
        self.on_metrics = on_metrics
        self.injector = injector
        self._run: Any | None = None
        self._original_log: Callable[..., Any] | None = None
        self._counter = 0
        self._installed = False

    def install(self, run: Any) -> None:
        if self._installed:
            return
        self._run = run
        original = run.log
        self._original_log = original

        def patched(data: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            result = original(data, *args, **kwargs)
            try:
                self._handle(data)
            except KeepaliveError:
                raise
            except Exception:
                pass
            return result

        run.log = patched
        self._installed = True

    def _handle(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        metrics = {k: float(v) for k, v in data.items() if _is_numeric(v)}
        if not metrics:
            return
        step = getattr(self._run, "step", None)
        if not isinstance(step, int):
            step = self._counter
        self._counter += 1
        if self.injector is not None:
            # apply() may mutate metrics (nan/divergence) or raise (oom/stall path);
            # OOM is surfaced to on_failure as a real failure signal.
            try:
                self.injector.apply(metrics)
            except RuntimeError as exc:
                self.on_failure(_oom_event(step, str(exc)))
                return
        if self.on_metrics is not None:
            with contextlib.suppress(Exception):
                self.on_metrics(step, metrics)
        snapshot = MetricSnapshot(step=step, metrics=metrics)
        event = self.suite.observe(snapshot)
        if event is not None:
            self.on_failure(event)

    def uninstall(self) -> None:
        if not self._installed:
            return
        if self._run is not None and self._original_log is not None:
            self._run.log = self._original_log
        self._installed = False
        self._run = None
        self._original_log = None


class HistoryPoller:
    def __init__(self, run_path: str, api: Any | None = None, loss_key: str = "loss") -> None:
        self.run_path = run_path
        self.loss_key = loss_key
        self._api = api
        self._cursor = 0

    def _get_api(self) -> Any:
        if self._api is None:
            import wandb

            self._api = wandb.Api()
        return self._api

    def poll(self) -> list[MetricSnapshot]:
        api = self._get_api()
        run = api.run(self.run_path)
        snapshots: list[MetricSnapshot] = []
        max_step = self._cursor
        for row in run.scan_history(min_step=self._cursor):
            step_raw = row.get("_step")
            if step_raw is None:
                continue
            step = int(step_raw)
            timestamp = row.get("_timestamp")
            metrics = {k: float(v) for k, v in row.items() if not k.startswith("_") and _is_numeric(v)}
            kwargs: dict[str, Any] = {"step": step, "metrics": metrics}
            if timestamp is not None and _is_numeric(timestamp):
                kwargs["timestamp"] = float(timestamp)
            snapshots.append(MetricSnapshot(**kwargs))
            if step > max_step:
                max_step = step
        self._cursor = max_step + 1
        return snapshots
