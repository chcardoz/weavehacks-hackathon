from __future__ import annotations

import math
from typing import Any

import pytest

from keepalive.detect.monitor import HistoryPoller, MetricHook
from keepalive.detect.rules import DetectorSuite
from keepalive.types import FailureEvent, FailureKind, KeepaliveStop, MetricSnapshot

from .conftest import FakeRun


def _noop(_event: FailureEvent) -> None:
    return None


class TestMetricHook:
    def test_install_preserves_original_log(self) -> None:
        run = FakeRun()
        hook = MetricHook(DetectorSuite(), _noop)
        hook.install(run)
        run.log({"loss": 0.5})
        assert run.logged == [{"loss": 0.5}]

    def test_non_numeric_and_bool_excluded(self) -> None:
        run = FakeRun()
        captured: list[MetricSnapshot] = []
        suite = DetectorSuite(detectors=[])

        orig_observe = suite.observe

        def spy(snapshot: MetricSnapshot) -> Any:
            captured.append(snapshot)
            return orig_observe(snapshot)

        suite.observe = spy  # type: ignore[method-assign]
        hook = MetricHook(suite, _noop)
        hook.install(run)
        run.log({"loss": 0.5, "name": "x", "flag": True, "n": 3})
        assert len(captured) == 1
        assert captured[0].metrics == {"loss": 0.5, "n": 3.0}

    def test_on_failure_called_on_detection(self) -> None:
        run = FakeRun()
        events: list[FailureEvent] = []
        hook = MetricHook(DetectorSuite(), events.append)
        hook.install(run)
        run.log({"loss": math.nan})
        assert len(events) == 1
        assert events[0].kind is FailureKind.NAN_LOSS

    def test_uninstall_restores_original(self) -> None:
        run = FakeRun()
        events: list[FailureEvent] = []
        hook = MetricHook(DetectorSuite(), events.append)
        patched_marker = run.log
        hook.install(run)
        assert run.log is not patched_marker
        hook.uninstall()
        run.log({"loss": math.nan})
        assert run.logged == [{"loss": math.nan}]
        assert events == []

    def test_install_idempotent(self) -> None:
        run = FakeRun()
        hook = MetricHook(DetectorSuite(), _noop)
        hook.install(run)
        patched = run.log
        hook.install(run)
        assert run.log is patched

    def test_on_failure_control_flow_propagates(self) -> None:
        run = FakeRun()

        def boom(_event: FailureEvent) -> None:
            raise KeepaliveStop("control flow")

        hook = MetricHook(DetectorSuite(), boom)
        hook.install(run)
        with pytest.raises(KeepaliveStop):
            run.log({"loss": math.nan})
        assert run.logged == [{"loss": math.nan}]

    def test_internal_hook_errors_dont_break_log(self) -> None:
        run = FakeRun()

        def bad_on_failure(_event: FailureEvent) -> None:
            raise RuntimeError("internal")

        hook = MetricHook(DetectorSuite(), bad_on_failure)
        hook.install(run)
        assert run.log({"loss": math.nan}) == "logged"
        assert run.logged == [{"loss": math.nan}]

    def test_step_from_run_attribute(self) -> None:
        run = FakeRun(step=42)
        events: list[FailureEvent] = []
        hook = MetricHook(DetectorSuite(), events.append)
        hook.install(run)
        run.log({"loss": math.nan})
        assert events[0].step == 42


class FakeApiRun:
    def __init__(self, rows_by_cursor: dict[int, list[dict[str, Any]]]) -> None:
        self.rows_by_cursor = rows_by_cursor

    def scan_history(self, min_step: int = 0, **_kwargs: Any) -> list[dict[str, Any]]:
        return self.rows_by_cursor.get(min_step, [])


class FakeApi:
    def __init__(self, run_obj: FakeApiRun) -> None:
        self.run_obj = run_obj
        self.run_calls: list[str] = []

    def run(self, path: str) -> FakeApiRun:
        self.run_calls.append(path)
        return self.run_obj


class TestHistoryPoller:
    def test_poll_returns_snapshots_and_advances_cursor(self) -> None:
        rows = {
            0: [
                {"_step": 0, "_timestamp": 1000.0, "loss": 1.0, "_internal": 99},
                {"_step": 1, "_timestamp": 1001.0, "loss": 0.9, "_internal": 99},
            ],
        }
        api = FakeApi(FakeApiRun(rows))
        poller = HistoryPoller("e/p/r", api=api)

        snaps = poller.poll()
        assert len(snaps) == 2
        assert snaps[0].step == 0
        assert snaps[0].timestamp == 1000.0
        assert snaps[0].metrics == {"loss": 1.0}
        assert "_internal" not in snaps[0].metrics

        second = poller.poll()
        assert second == []
        assert api.run_calls == ["e/p/r", "e/p/r"]

    def test_skips_rows_without_step(self) -> None:
        rows = {0: [{"_timestamp": 1.0, "loss": 1.0}, {"_step": 5, "loss": 0.5}]}
        api = FakeApi(FakeApiRun(rows))
        poller = HistoryPoller("e/p/r", api=api)
        snaps = poller.poll()
        assert len(snaps) == 1
        assert snaps[0].step == 5
