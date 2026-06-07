from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx

from keepalive.config import Settings
from keepalive.reporter import EventReporter, NullReporter, build_reporter


def make_settings(**over: Any) -> Settings:
    base = {"api_key": "ka_live_test", "api_url": "https://api.test"}
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


class CapturingTransport:
    """A MockTransport wrapper that records every posted event batch."""

    def __init__(self, status: int = 200, raise_exc: bool = False) -> None:
        self.batches: list[list[dict[str, Any]]] = []
        self.requests: list[httpx.Request] = []
        self._status = status
        self._raise = raise_exc
        self._event = threading.Event()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._raise:
            self._event.set()
            raise httpx.ConnectError("boom", request=request)
        body = json.loads(request.content)
        self.batches.append(body.get("events", []))
        self._event.set()
        return httpx.Response(self._status, json={"accepted": len(body.get("events", []))})

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(self.handler))

    def wait(self, timeout: float = 3.0) -> bool:
        return self._event.wait(timeout)


def _all_events(cap: CapturingTransport) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for batch in cap.batches:
        out.extend(batch)
    return out


def test_emit_flushes_on_close() -> None:
    cap = CapturingTransport()
    rep = EventReporter(make_settings(), "run-1", {"name": "n"}, http=cap.client())
    rep.emit("run.started", "hello", include_project=True)
    rep.close()

    events = _all_events(cap)
    assert len(events) == 1
    ev = events[0]
    assert ev["project_id"] == "run-1"
    assert ev["type"] == "run.started"
    assert ev["source"] == "library"
    assert ev["project"] == {"name": "n"}


def test_emit_batches_by_size() -> None:
    cap = CapturingTransport()
    rep = EventReporter(make_settings(), "run-1", {}, http=cap.client())
    for i in range(25):
        rep.emit("log", f"m{i}")
    assert cap.wait(3.0)
    rep.close()
    events = _all_events(cap)
    assert len(events) == 25
    # at least one batch hit the 20-event cap
    assert any(len(b) == 20 for b in cap.batches)


def test_emit_never_raises_when_post_explodes() -> None:
    cap = CapturingTransport(raise_exc=True)
    rep = EventReporter(make_settings(), "run-1", {}, http=cap.client())
    rep.emit("log", "explode please")
    assert cap.wait(3.0)
    # close must not raise even though the POST blew up
    rep.close()


def test_emit_optional_fields_included() -> None:
    cap = CapturingTransport()
    rep = EventReporter(make_settings(), "run-1", {}, http=cap.client())
    rep.emit("agent.status", "s", incident_id="inc_1", agent_id="probe_1", level="warn", data={"state": "running"})
    rep.close()
    ev = _all_events(cap)[0]
    assert ev["incident_id"] == "inc_1"
    assert ev["agent_id"] == "probe_1"
    assert ev["level"] == "warn"
    assert ev["data"] == {"state": "running"}
    assert "project" not in ev  # include_project defaulted False


def test_heartbeat_rate_limited() -> None:
    cap = CapturingTransport()
    rep = EventReporter(make_settings(), "run-1", {}, http=cap.client())
    rep.heartbeat(1, 0.5)
    rep.heartbeat(2, 0.4)  # dropped, within 5s window
    rep.heartbeat(3, 0.3)  # dropped
    rep.close()
    events = _all_events(cap)
    hb = [e for e in events if e["type"] == "run.heartbeat"]
    assert len(hb) == 1
    assert hb[0]["data"] == {"step": 1, "loss": 0.5}


def test_heartbeat_omits_none_loss() -> None:
    cap = CapturingTransport()
    rep = EventReporter(make_settings(), "run-1", {}, http=cap.client())
    rep.heartbeat(7, None)
    rep.close()
    ev = _all_events(cap)[0]
    assert ev["data"] == {"step": 7}


def test_null_reporter_noops() -> None:
    rep = NullReporter()
    # none of these should raise or do anything observable
    rep.emit("anything", "msg", incident_id="x", data={"a": 1})
    rep.heartbeat(1, 0.5)
    rep.close()


def test_build_reporter_unconfigured_returns_null() -> None:
    rep = build_reporter(Settings(), run=None, commit_sha="abc")
    assert isinstance(rep, NullReporter)


def test_build_reporter_project_id_from_run() -> None:
    class Run:
        id = "wandb-xyz"
        name = "nanogpt"
        url = "https://wandb.ai/t/p/wandb-xyz"

    cap = CapturingTransport()
    rep = build_reporter(make_settings(), run=Run(), commit_sha="deadbeef", demo_mode=True, http=cap.client())
    assert isinstance(rep, EventReporter)
    assert rep.project_id == "wandb-xyz"
    assert rep.project_meta["wandb_run_id"] == "wandb-xyz"
    assert rep.project_meta["wandb_url"] == "https://wandb.ai/t/p/wandb-xyz"
    assert rep.project_meta["commit_sha"] == "deadbeef"
    assert rep.project_meta["demo_mode"] is True
    rep.close()


def test_build_reporter_project_id_local_without_run() -> None:
    cap = CapturingTransport()
    rep = build_reporter(make_settings(), run=None, commit_sha="", http=cap.client())
    assert isinstance(rep, EventReporter)
    assert rep.project_id.startswith("local-")
    rep.close()


def test_periodic_flush_without_close() -> None:
    cap = CapturingTransport()
    rep = EventReporter(make_settings(), "run-1", {}, http=cap.client())
    rep.emit("log", "tick")
    # background thread flushes within ~2s even without close()
    assert cap.wait(4.0)
    deadline = time.monotonic() + 3.0
    while not _all_events(cap) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _all_events(cap)
    rep.close()
