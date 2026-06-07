from __future__ import annotations

from typing import Any

import pytest

from keepalive.config import Settings
from keepalive.watchdog import Watchdog, _parse_owner_repo, watchdog


class RecordingReporter:
    project_id = "run-1"
    server_project_id = None
    server_run_id = None

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        self.heartbeats: list[tuple[int, float | None, dict[str, float] | None]] = []
        self.closed = False

    def emit(self, type: str, message: str, **kwargs: Any) -> None:
        self.events.append((type, message, kwargs))

    def heartbeat(self, step: int, loss: float | None, metrics: dict[str, float] | None = None) -> None:
        self.heartbeats.append((step, loss, metrics))

    def close(self) -> None:
        self.closed = True

    def types(self) -> list[str]:
        return [t for t, _, _ in self.events]


# -- git url parsing --------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("git@github.com:chcardoz/nanogpt.git", ("chcardoz", "nanogpt")),
        ("git@github.com:chcardoz/nanogpt", ("chcardoz", "nanogpt")),
        ("https://github.com/chcardoz/nanogpt.git", ("chcardoz", "nanogpt")),
        ("https://github.com/chcardoz/nanogpt", ("chcardoz", "nanogpt")),
        ("http://gitlab.com/group/sub/proj.git", ("sub", "proj")),
        ("", ("", "")),
        ("not-a-url", ("", "")),
    ],
)
def test_parse_owner_repo(url: str, expected: tuple[str, str]) -> None:
    assert _parse_owner_repo(url) == expected


# -- lifecycle --------------------------------------------------------------


class FakeRun:
    id = "wandb-xyz"
    name = "nanogpt"
    url = "https://wandb.ai/t/p/wandb-xyz"

    def __init__(self) -> None:
        self.logged: list[dict[str, Any]] = []

    def log(self, data: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        self.logged.append(data)
        return "ok"


def _wd(reporter: RecordingReporter, run: Any = None, **kw: Any) -> Watchdog:
    return Watchdog(
        run=run,
        settings=Settings(api_key="k", api_url="https://api.test"),
        reporter=reporter,
        **kw,
    )


def test_start_emits_run_started_with_project_block() -> None:
    rep = RecordingReporter()
    wd = _wd(rep, prompt="watch grad norm", threshold=0.7, max_agents=2)
    wd.start()
    wd.stop()

    started = next(kw for t, _, kw in rep.events if t == "run.started")
    assert started["include_project"] is True
    meta = wd._project_meta()
    assert meta["monitoring_prompt"] == "watch grad norm"
    assert meta["threshold"] == 0.7
    assert meta["max_agents"] == 2
    # repo owner/name come from the real repo's git origin (best-effort, may be empty)
    assert "repo_owner" in meta
    assert "branch" in meta


def test_stop_emits_run_stopped_and_closes() -> None:
    rep = RecordingReporter()
    wd = _wd(rep)
    wd.start()
    wd.stop()
    assert "run.stopped" in rep.types()
    assert rep.closed is True


def test_metric_hook_drives_heartbeat() -> None:
    rep = RecordingReporter()
    run = FakeRun()
    wd = _wd(rep, run=run)
    with wd:
        run.log({"loss": 0.5, "step": 1})
    assert rep.heartbeats
    _step, loss, metrics = rep.heartbeats[0]
    assert loss == 0.5
    assert metrics is not None and metrics["loss"] == 0.5


def test_hard_failure_emits_incident_and_keeps_going() -> None:
    rep = RecordingReporter()
    run = FakeRun()
    wd = _wd(rep, run=run, loss_key="loss")
    with wd:
        run.log({"loss": float("nan")})  # NaN trips the detector
        # control returns here — no exception raised, training continues
        run.log({"loss": 0.2})

    types = rep.types()
    assert "incident.detected" in types
    detected = next(kw for t, _, kw in rep.events if t == "incident.detected")
    assert detected["data"]["kind"] == "nan_loss"
    assert detected["level"] == "error"
    assert detected["include_project"] is True
    assert "metrics_tail" in detected["data"]


def test_context_manager_exception_emits_incident_and_reraises() -> None:
    rep = RecordingReporter()
    wd = _wd(rep)
    with pytest.raises(ValueError):
        with wd:
            raise ValueError("boom")

    types = rep.types()
    assert "incident.detected" in types
    assert "run.stopped" in types
    detected = next(kw for t, _, kw in rep.events if t == "incident.detected")
    assert detected["data"]["kind"] == "exception"


def test_watchdog_contextmanager_helper() -> None:
    rep = RecordingReporter()
    with watchdog(run=None, settings=Settings(api_key="k"), reporter=rep) as wd:
        assert isinstance(wd, Watchdog)
    assert "run.started" in rep.types()
    assert "run.stopped" in rep.types()


def test_default_suite_inherits_loss_key() -> None:
    wd = Watchdog(run=None, settings=Settings(api_key="k"), loss_key="train/loss")
    keys = {getattr(d, "loss_key", None) for d in wd.suite.detectors}
    assert keys == {"train/loss"}
