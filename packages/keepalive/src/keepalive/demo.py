from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from .config import Settings

_log = logging.getLogger("keepalive")

INJECT_NAN = "inject_nan"
INJECT_DIVERGENCE = "inject_divergence"
INJECT_STALL = "inject_stall"
INJECT_OOM = "inject_oom"

_KNOWN_FAULTS = {INJECT_NAN, INJECT_DIVERGENCE, INJECT_STALL, INJECT_OOM}

_POLL_INTERVAL_S = 2.0


class FaultInjector:
    """Thread-safe single-slot holder for a pending demo fault.

    The metric hook polls :meth:`pop` once per step; the command poller (or a test)
    arms a fault with :meth:`request`. Only one fault is pending at a time and it is
    consumed (popped) exactly once.
    """

    def __init__(
        self,
        loss_key: str = "loss",
        *,
        stall_seconds: float = 0.0,
        lr_scale_fn: Callable[[float], None] | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.loss_key = loss_key
        self.stall_seconds = stall_seconds
        self._lr_scale_fn = lr_scale_fn
        self._sleep_fn = sleep_fn
        self._lock = threading.Lock()
        self._pending: str | None = None
        self._divergence_active = False
        self._divergence_mult = 1.0

    def request(self, fault_type: str) -> None:
        if fault_type not in _KNOWN_FAULTS:
            return
        with self._lock:
            self._pending = fault_type

    def pop(self) -> str | None:
        with self._lock:
            fault = self._pending
            self._pending = None
            return fault

    def apply(self, metrics: dict[str, float]) -> None:
        """Apply a pending fault to the metric snapshot, in place.

        Called from the metric hook before detectors observe the snapshot. Faults
        that produce a real failure signal mutate ``metrics``; stall sleeps; OOM
        raises a RuntimeError that the detectors recognize as a CUDA OOM.
        """
        fault = self.pop()
        if fault == INJECT_NAN:
            metrics[self.loss_key] = float("nan")
        elif fault == INJECT_DIVERGENCE:
            if self._lr_scale_fn is not None:
                _safely(lambda: self._lr_scale_fn(100.0), "lr_scale")  # type: ignore[misc]
            else:
                # No optimizer handle: corrupt the loss with a multiplier that grows
                # each step so the DivergenceDetector fires naturally.
                self._divergence_active = True
        elif fault == INJECT_STALL:
            seconds = self.stall_seconds
            _safely(lambda: self._sleep_fn(seconds), "stall_sleep")
        elif fault == INJECT_OOM:
            raise RuntimeError("CUDA out of memory. (keepalive demo fault)")

        if self._divergence_active and self.loss_key in metrics:
            self._divergence_mult *= 3.0
            metrics[self.loss_key] = metrics[self.loss_key] * self._divergence_mult


class CommandPoller:
    """Daemon thread that pulls demo commands from the relay and arms the injector.

    Only started when demo mode is armed. Every ``_POLL_INTERVAL_S`` seconds it GETs
    ``/v1/projects/{project_id}/commands`` (the relay marks them consumed atomically),
    arms each command on the injector, and logs it via the reporter. All exceptions
    are swallowed.
    """

    def __init__(
        self,
        settings: Settings,
        project_id: str,
        injector: FaultInjector,
        reporter: Any,
        *,
        http: httpx.Client | None = None,
        poll_interval_s: float = _POLL_INTERVAL_S,
    ) -> None:
        self.settings = settings
        self.project_id = project_id
        self.injector = injector
        self.reporter = reporter
        self.poll_interval_s = poll_interval_s
        self._owns_http = http is None
        self._http = http or httpx.Client(
            base_url=settings.api_url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=5.0,
        )
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="keepalive-commands", daemon=True)

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def poll_once(self) -> int:
        """Fetch pending commands, arm them, log them. Returns how many were handled."""
        try:
            resp = self._http.get(f"/v1/projects/{self.project_id}/commands")
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            _log.debug("keepalive: command poll failed: %r", exc)
            return 0
        commands = payload.get("commands") if isinstance(payload, dict) else None
        if not isinstance(commands, list):
            return 0
        handled = 0
        for cmd in commands:
            if not isinstance(cmd, dict):
                continue
            ctype = cmd.get("type")
            if not isinstance(ctype, str):
                continue
            self.injector.request(ctype)
            _safely(
                lambda ctype=ctype: self.reporter.emit(
                    "log",
                    f"demo fault requested: {ctype}",
                    level="warn",
                    data={"command": ctype},
                ),
                "command_log",
            )
            handled += 1
        return handled

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.poll_interval_s)

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._owns_http:
            with contextlib.suppress(Exception):
                self._http.close()


def _safely(fn: Callable[[], Any], what: str = "") -> Any:
    try:
        return fn()
    except Exception as exc:
        _log.debug("keepalive: demo step failed (%s): %r", what, exc)
        return None
