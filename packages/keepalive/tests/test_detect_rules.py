from __future__ import annotations

import math

import pytest

from keepalive.detect.rules import (
    DetectorSuite,
    DivergenceDetector,
    NaNLossDetector,
    StallDetector,
    scan_logline,
)
from keepalive.types import FailureKind

from .conftest import snap


class TestNaNLossDetector:
    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_fires_on_non_finite(self, bad: float) -> None:
        det = NaNLossDetector()
        s = snap(7, loss=bad, lr=0.1)
        event = det.check(s, [s])
        assert event is not None
        assert event.kind is FailureKind.NAN_LOSS
        assert event.step == 7
        assert event.metrics["lr"] == 0.1

    def test_no_fire_on_finite(self) -> None:
        det = NaNLossDetector()
        s = snap(1, loss=0.5)
        assert det.check(s, [s]) is None

    def test_no_fire_when_loss_absent(self) -> None:
        det = NaNLossDetector()
        s = snap(1, acc=0.9)
        assert det.check(s, [s]) is None


class TestDivergenceDetector:
    def test_no_fire_below_min_history(self) -> None:
        det = DivergenceDetector()
        hist = [snap(i, loss=1.0) for i in range(10)]
        assert det.check(hist[-1], hist) is None

    def test_no_fire_on_flat_loss(self) -> None:
        det = DivergenceDetector()
        hist = [snap(i, loss=1.0) for i in range(50)]
        assert det.check(hist[-1], hist) is None

    def test_fires_on_divergence(self) -> None:
        det = DivergenceDetector()
        hist = [snap(i, loss=1.0) for i in range(30)]
        hist += [snap(30 + i, loss=10.0) for i in range(20)]
        event = det.check(hist[-1], hist)
        assert event is not None
        assert event.kind is FailureKind.DIVERGENCE
        assert event.step == 49

    def test_non_finite_losses_ignored(self) -> None:
        det = DivergenceDetector()
        hist = [snap(i, loss=1.0) for i in range(30)]
        hist += [snap(30 + i, loss=math.nan) for i in range(20)]
        assert det.check(hist[-1], hist) is None


class TestStallDetector:
    def test_none_when_last_none(self) -> None:
        det = StallDetector(timeout_s=100.0)
        assert det.check_idle(now=1000.0, last=None) is None

    def test_none_within_timeout(self) -> None:
        det = StallDetector(timeout_s=100.0)
        last = snap(5, loss=0.3, ts=1000.0)
        assert det.check_idle(now=1050.0, last=last) is None

    def test_fires_past_timeout(self) -> None:
        det = StallDetector(timeout_s=100.0)
        last = snap(5, loss=0.3, ts=1000.0)
        event = det.check_idle(now=1200.0, last=last)
        assert event is not None
        assert event.kind is FailureKind.STALL
        assert event.step == 5
        assert event.timestamp == 1200.0


class TestScanLogline:
    @pytest.mark.parametrize(
        "line",
        [
            "RuntimeError: CUDA out of memory. Tried to allocate",
            "torch.cuda.OutOfMemoryError: out of memory",
            "CUBLAS_STATUS_ALLOC_FAILED when calling cublasCreate",
        ],
    )
    def test_oom(self, line: str) -> None:
        event = scan_logline(line, step=3)
        assert event is not None
        assert event.kind is FailureKind.OOM
        assert event.step == 3

    @pytest.mark.parametrize(
        "line",
        [
            "Traceback (most recent call last):",
            "Segmentation fault (core dumped)",
            "Killed",
        ],
    )
    def test_exception(self, line: str) -> None:
        event = scan_logline(line)
        assert event is not None
        assert event.kind is FailureKind.EXCEPTION

    def test_benign(self) -> None:
        assert scan_logline("epoch 3 loss 0.42 lr 1e-4") is None


class TestDetectorSuite:
    def test_observe_fires_once_then_suppresses(self) -> None:
        suite = DetectorSuite()
        first = suite.observe(snap(0, loss=math.nan))
        assert first is not None
        assert suite.tripped is True
        second = suite.observe(snap(1, loss=math.nan))
        assert second is None

    def test_reset_rearms(self) -> None:
        suite = DetectorSuite()
        assert suite.observe(snap(0, loss=math.nan)) is not None
        suite.reset()
        assert suite.tripped is False
        assert suite.observe(snap(1, loss=math.nan)) is not None

    def test_history_bounded(self) -> None:
        suite = DetectorSuite(detectors=[], max_history=5)
        for i in range(20):
            suite.observe(snap(i, loss=1.0))
        hist = suite.history
        assert len(hist) == 5
        assert hist[0].step == 15
        assert hist[-1].step == 19

    def test_idle_check_uses_injected_now(self) -> None:
        suite = DetectorSuite(detectors=[], stall=StallDetector(timeout_s=10.0))
        suite.observe(snap(0, loss=1.0, ts=1000.0))
        assert suite.idle_check(now=1005.0) is None
        event = suite.idle_check(now=1050.0)
        assert event is not None
        assert event.kind is FailureKind.STALL
        assert suite.tripped is True

    def test_idle_check_suppressed_when_tripped(self) -> None:
        suite = DetectorSuite(detectors=[], stall=StallDetector(timeout_s=10.0))
        suite.observe(snap(0, loss=1.0, ts=1000.0))
        suite.tripped = True
        assert suite.idle_check(now=1050.0) is None

    def test_scan_logline_respects_tripped(self) -> None:
        suite = DetectorSuite()
        first = suite.scan_logline("CUDA out of memory")
        assert first is not None
        assert suite.tripped is True
        assert suite.scan_logline("Traceback (most recent call last):") is None
