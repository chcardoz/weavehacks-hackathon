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

_SENTINEL = object()


class EventReporter:
    """Fire-and-forget emitter for the observability data plane.

    Events are queued from the hot path (``queue.put_nowait``; never blocks, never
    raises) and flushed by a daemon thread that batches up to ``_BATCH_MAX`` events
    or every ``_FLUSH_INTERVAL_S`` seconds and POSTs them to ``/v1/events``. Every
    exception is swallowed: a dead relay must never affect the training run.
    """

    def __init__(
        self,
        settings: Settings,
        project_id: str,
        project_meta: dict[str, Any],
        http: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.project_id = project_id
        self.project_meta = dict(project_meta or {})
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
        agent_id: str | None = None,
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
            if agent_id is not None:
                event["agent_id"] = agent_id
            if include_project:
                event["project"] = dict(self.project_meta)
            self._queue.put_nowait(event)
        except Exception:  # pragma: no cover - put_nowait on an unbounded queue won't raise
            pass

    def heartbeat(self, step: int, loss: float | None) -> None:
        try:
            now = time.monotonic()
            if now - self._last_heartbeat < _HEARTBEAT_INTERVAL_S:
                return
            self._last_heartbeat = now
            data: dict[str, Any] = {"step": step}
            if loss is not None:
                data["loss"] = loss
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
            resp = self._http.post("/v1/events", json={"events": events})
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - network failures are swallowed
            _log.debug("keepalive: event flush failed: %r", exc)


class NullReporter:
    """No-op reporter used when the relay isn't configured."""

    project_id = ""

    def emit(self, *args: Any, **kwargs: Any) -> None:
        return None

    def heartbeat(self, *args: Any, **kwargs: Any) -> None:
        return None

    def close(self) -> None:
        return None


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git_remote() -> str:
    try:
        import subprocess

        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = out.stdout.strip()
    except Exception:
        return ""
    if url.startswith("git@"):
        host, _, path = url.partition(":")
        host = host.removeprefix("git@")
        return f"https://{host}/{path.removesuffix('.git')}"
    return url.removesuffix(".git")


def build_reporter(
    settings: Settings,
    run: Any,
    commit_sha: str,
    *,
    demo_mode: bool = False,
    http: httpx.Client | None = None,
) -> EventReporter | NullReporter:
    """Build a reporter, deriving project identity from the wandb run + git."""
    if not settings.api_key or not settings.api_url:
        return NullReporter()

    run_id = ""
    if run is not None:
        run_id = str(getattr(run, "id", "") or "")
    project_id = run_id or f"local-{uuid.uuid4().hex[:8]}"

    name = ""
    wandb_url = ""
    if run is not None:
        name = str(getattr(run, "name", "") or getattr(run, "project", "") or "")
        wandb_url = str(getattr(run, "url", "") or "")

    repo = ""
    for candidate in (getattr(settings, "repo_url", ""), _git_remote()):
        if candidate:
            repo = candidate
            break

    project_meta = {
        "name": name,
        "repo": repo,
        "wandb_run_id": run_id or None,
        "wandb_url": wandb_url or None,
        "commit_sha": commit_sha or None,
        "demo_mode": demo_mode,
    }
    return EventReporter(settings, project_id, project_meta, http=http)
