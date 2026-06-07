from __future__ import annotations

import math
from typing import Any

import httpx
import pytest

from keepalive.config import Settings
from keepalive.demo import (
    INJECT_DIVERGENCE,
    INJECT_NAN,
    INJECT_OOM,
    INJECT_STALL,
    CommandPoller,
    FaultInjector,
)
from keepalive.detect.rules import DetectorSuite
from keepalive.types import MetricSnapshot


def make_settings(**over: Any) -> Settings:
    base = {"api_key": "ka_live_test", "api_url": "https://api.test"}
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


class RecordingReporter:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def emit(self, type: str, message: str, **kwargs: Any) -> None:
        self.events.append((type, message, kwargs))


# -- FaultInjector ----------------------------------------------------------


def test_pop_once_semantics() -> None:
    inj = FaultInjector()
    inj.request(INJECT_NAN)
    assert inj.pop() == INJECT_NAN
    assert inj.pop() is None  # consumed exactly once


def test_request_ignores_unknown_fault() -> None:
    inj = FaultInjector()
    inj.request("not_a_fault")
    assert inj.pop() is None


def test_nan_injection_produces_nan_for_detector() -> None:
    inj = FaultInjector(loss_key="loss")
    inj.request(INJECT_NAN)
    metrics = {"loss": 0.5}
    inj.apply(metrics)
    assert math.isnan(metrics["loss"])

    # the DetectorSuite sees the NaN and fires NaNLoss
    suite = DetectorSuite()
    event = suite.observe(MetricSnapshot(step=10, metrics=metrics))
    assert event is not None
    assert event.kind.value == "nan_loss"


def test_divergence_with_optimizer_scales_lr() -> None:
    scaled: list[float] = []
    inj = FaultInjector(lr_scale_fn=scaled.append)
    inj.request(INJECT_DIVERGENCE)
    inj.apply({"loss": 1.0})
    assert scaled == [100.0]


def test_divergence_without_optimizer_grows_loss() -> None:
    inj = FaultInjector(loss_key="loss")  # no lr_scale_fn
    inj.request(INJECT_DIVERGENCE)
    m1 = {"loss": 1.0}
    inj.apply(m1)
    m2 = {"loss": 1.0}
    inj.apply(m2)  # divergence stays active, multiplier grows
    assert m2["loss"] > m1["loss"]


def test_stall_calls_sleep_fn_once() -> None:
    slept: list[float] = []
    inj = FaultInjector(stall_seconds=12.0, sleep_fn=slept.append)
    inj.request(INJECT_STALL)
    inj.apply({"loss": 1.0})
    assert slept == [12.0]
    # only once — fault consumed
    inj.apply({"loss": 1.0})
    assert slept == [12.0]


def test_oom_raises_cuda_error() -> None:
    inj = FaultInjector()
    inj.request(INJECT_OOM)
    with pytest.raises(RuntimeError, match="CUDA out of memory"):
        inj.apply({"loss": 1.0})


def test_apply_noop_when_no_fault() -> None:
    inj = FaultInjector(loss_key="loss")
    metrics = {"loss": 0.5}
    inj.apply(metrics)
    assert metrics == {"loss": 0.5}


# -- CommandPoller ----------------------------------------------------------


def _poller_with_responses(responses: list[Any], injector: FaultInjector, reporter: Any) -> CommandPoller:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[idx]

    http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    return CommandPoller(make_settings(), "run-1", injector, reporter, http=http)


def test_command_poller_hits_v1_endpoint() -> None:
    inj = FaultInjector()
    rep = RecordingReporter()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"commands": []})

    http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    poller = CommandPoller(make_settings(), "proj-1", inj, rep, http=http)
    poller.poll_once()
    poller.close()
    assert seen == ["/api/v1/projects/proj-1/commands"]


def test_command_poller_arms_injector_and_logs() -> None:
    inj = FaultInjector()
    rep = RecordingReporter()
    poller = _poller_with_responses(
        [
            httpx.Response(200, json={"commands": [{"id": "c1", "type": "inject_nan"}]}),
            httpx.Response(200, json={"commands": []}),
        ],
        inj,
        rep,
    )
    handled = poller.poll_once()
    assert handled == 1
    assert inj.pop() == INJECT_NAN
    assert rep.events
    type_, message, kwargs = rep.events[0]
    assert type_ == "log"
    assert "inject_nan" in message
    assert kwargs["level"] == "warn"

    # second poll: no commands
    assert poller.poll_once() == 0
    poller.close()


def test_command_poller_swallows_http_error() -> None:
    inj = FaultInjector()
    rep = RecordingReporter()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    http = httpx.Client(base_url="https://api.test", transport=httpx.MockTransport(handler))
    poller = CommandPoller(make_settings(), "run-1", inj, rep, http=http)
    assert poller.poll_once() == 0  # no raise
    poller.close()


def test_command_poller_start_and_close() -> None:
    inj = FaultInjector()
    rep = RecordingReporter()
    poller = _poller_with_responses([httpx.Response(200, json={"commands": []})], inj, rep)
    poller.start()
    poller.close()  # stops cleanly
