from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
import uuid
from typing import Any

import httpx

from .config import Settings

_log = logging.getLogger("keepalive")

_BATCH_MAX = 20
_FLUSH_INTERVAL_S = 2.0
_HEARTBEAT_INTERVAL_S = 5.0
_CLOSE_TIMEOUT_S = 2.0

_EVENTS_PATH = "/api/v1/events"

_SENTINEL = object()


class EventReporter:
    """Fire-and-forget emitter for the observability data plane.

    Events are queued from the hot path (``queue.put_nowait``; never blocks, never
    raises) and flushed by a daemon thread that batches up to ``_BATCH_MAX`` events
    or every ``_FLUSH_INTERVAL_S`` seconds and POSTs them to ``/api/v1/events``.
    Every exception is swallowed: a dead server must never affect the training run.

    The library sends its own run-scoped id as each event's ``project_id`` field
    (the server treats this as ``run.id``). The server resolves the real project and
    returns its ``project_id`` on the first successful flush; we capture it as
    :attr:`server_project_id` for the command poller.
    """

    def __init__(
        self,
        settings: Settings,
        run_id: str,
        project_meta: dict[str, Any],
        http: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.run_id = run_id
        # `project_id` is the per-event run-scoped id the server treats as run.id.
        self.project_id = run_id
        self.project_meta = dict(project_meta or {})
        self.server_project_id: str | None = None
        self.server_run_id: str | None = None
        self._owns_http = http is None
        self._http = http or httpx.Client(
            base_url=settings.api_url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=5.0,
        )
        self._queue: queue.Queue[Any] = queue.Queue()
        self._last_heartbeat = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="keepalive-reporter", daemon=True)
        self._thread.start()

    def emit(
        self,
        type: str,
        message: str,
        *,
        incident_id: str | None = None,
        level: str = "info",
        data: dict[str, Any] | None = None,
        include_project: bool = False,
    ) -> None:
        try:
            event: dict[str, Any] = {
                "project_id": self.project_id,
                "source": "library",
                "level": level,
                "type": type,
                "message": message,
                "data": dict(data) if data else {},
                "ts": _iso_now(),
            }
            if incident_id is not None:
                event["incident_id"] = incident_id
            if include_project:
                event["project"] = dict(self.project_meta)
            self._queue.put_nowait(event)
        except Exception:  # pragma: no cover - put_nowait on an unbounded queue won't raise
            pass

    def heartbeat(self, step: int, loss: float | None, metrics: dict[str, float] | None = None) -> None:
        try:
            now = time.monotonic()
            if now - self._last_heartbeat < _HEARTBEAT_INTERVAL_S:
                return
            self._last_heartbeat = now
            data: dict[str, Any] = {"step": step}
            if loss is not None:
                data["loss"] = loss
            data["metrics"] = dict(metrics) if metrics else {}
            self.emit("run.heartbeat", f"step {step}", data=data)
        except Exception:
            pass

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._queue.put_nowait(_SENTINEL)
        self._stop.set()
        self._thread.join(timeout=_CLOSE_TIMEOUT_S)
        if self._owns_http:
            with contextlib.suppress(Exception):
                self._http.close()

    # -- background thread ---------------------------------------------------

    def _run(self) -> None:
        while True:
            batch = self._drain()
            if batch:
                self._post(batch)
            if self._stop.is_set() and self._queue.empty():
                # final drain to be safe, then exit
                final = self._drain(block=False)
                if final:
                    self._post(final)
                return

    def _drain(self, block: bool = True) -> list[dict[str, Any]]:
        batch: list[dict[str, Any]] = []
        try:
            if block:
                first = self._queue.get(timeout=_FLUSH_INTERVAL_S)
                if first is _SENTINEL:
                    self._stop.set()
                else:
                    batch.append(first)
        except queue.Empty:
            return batch
        except Exception:
            return batch
        while len(batch) < _BATCH_MAX:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            if item is _SENTINEL:
                self._stop.set()
                break
            batch.append(item)
        return batch

    def _post(self, events: list[dict[str, Any]]) -> None:
        try:
            resp = self._http.post(_EVENTS_PATH, json={"events": events})
            resp.raise_for_status()
            self._capture_ids(resp)
        except Exception as exc:  # pragma: no cover - network failures are swallowed
            _log.debug("keepalive: event flush failed: %r", exc)

    def _capture_ids(self, resp: httpx.Response) -> None:
        if self.server_project_id is not None:
            return
        try:
            body = resp.json()
        except Exception:
            return
        if not isinstance(body, dict):
            return
        pid = body.get("project_id")
        if isinstance(pid, str) and pid:
            self.server_project_id = pid
        rid = body.get("run_id")
        if isinstance(rid, str) and rid:
            self.server_run_id = rid


class NullReporter:
    """No-op reporter used when the server isn't configured."""

    project_id = ""
    server_project_id: str | None = None
    server_run_id: str | None = None

    def emit(self, *args: Any, **kwargs: Any) -> None:
        return None

    def heartbeat(self, *args: Any, **kwargs: Any) -> None:
        return None

    def close(self) -> None:
        return None


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_reporter(
    settings: Settings,
    run: Any,
    project_meta: dict[str, Any],
    *,
    http: httpx.Client | None = None,
) -> EventReporter | NullReporter:
    """Build a reporter. ``project_meta`` is the full `project` block for run.started."""
    if not settings.api_key or not settings.api_url:
        return NullReporter()

    run_id = ""
    if run is not None:
        run_id = str(getattr(run, "id", "") or "")
    run_id = run_id or f"local-{uuid.uuid4().hex[:8]}"

    return EventReporter(settings, run_id, dict(project_meta or {}), http=http)
