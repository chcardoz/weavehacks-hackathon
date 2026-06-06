from __future__ import annotations

from typing import Any

from keepalive.probes import judge
from keepalive.types import FixHypothesis, MetricSnapshot, ProbeResult, ProbeSpec, ProbeState


def _spec(pid: str, branch: str | None = "b") -> ProbeSpec:
    h = FixHypothesis(id="h", title="t", rationale="r", instructions="i")
    return ProbeSpec(id=pid, incident_id="inc1", hypothesis=h, branch=branch)


def _result(pid: str, loss: float | None, state: ProbeState) -> ProbeResult:
    return ProbeResult(spec=_spec(pid), wandb_run_id="r-" + pid, history=[], final_loss=loss, state=state)


def test_pick_winner_empty() -> None:
    assert judge.pick_winner([]) is None


def test_pick_winner_argmin_over_finished() -> None:
    results = [
        _result("a", 2.0, ProbeState.FINISHED),
        _result("b", 1.0, ProbeState.FINISHED),
        _result("c", None, ProbeState.FINISHED),
        _result("d", float("nan"), ProbeState.FINISHED),
    ]
    winner = judge.pick_winner(results)
    assert winner is not None
    assert winner.spec.id == "b"
    assert winner.final_loss == 1.0


def test_pick_winner_excludes_non_finished_even_with_finite_loss() -> None:
    results = [
        _result("a", 0.1, ProbeState.FAILED),
        _result("b", 0.5, ProbeState.RUNNING),
        _result("c", 0.9, ProbeState.KILLED),
    ]
    assert judge.pick_winner(results) is None


def test_summarize_contains_every_spec_id() -> None:
    results = [
        _result("alpha", 1.0, ProbeState.FINISHED),
        _result("beta", None, ProbeState.FAILED),
    ]
    text = judge.summarize(results)
    assert "alpha" in text
    assert "beta" in text
    assert "n/a" in text  # None loss rendered n/a
    assert "1.0000" in text  # finite loss formatted


class _FakeRun:
    def __init__(self, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
        self._rows = rows
        self.summary = summary

    def scan_history(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeApi:
    def __init__(self, run: Any) -> None:
        self._run = run

    def run(self, run_path: str) -> Any:
        return self._run


def test_fetch_probe_metrics_summary_loss() -> None:
    rows = [
        {"_step": 0, "loss": 2.0, "acc": 0.5},
        {"_step": 1, "loss": 1.5, "acc": 0.6},
    ]
    run = _FakeRun(rows, summary={"loss": 1.2})
    api = _FakeApi(run)
    final, history = judge.fetch_probe_metrics("ent/proj/r", api=api, loss_key="loss")
    assert final == 1.2
    assert len(history) == 2
    assert all(isinstance(h, MetricSnapshot) for h in history)
    assert history[0].step == 0
    assert history[0].metrics["loss"] == 2.0
    assert history[1].metrics["acc"] == 0.6


def test_fetch_probe_metrics_falls_back_to_last_finite_history_loss() -> None:
    rows = [
        {"_step": 0, "loss": 2.0},
        {"_step": 1, "loss": 0.7},
        {"_step": 2, "acc": 0.9},  # no loss; should not overwrite last finite loss
    ]
    run = _FakeRun(rows, summary={})  # summary missing loss
    api = _FakeApi(run)
    final, history = judge.fetch_probe_metrics("ent/proj/r", api=api, loss_key="loss")
    assert final == 0.7
    assert len(history) == 3


def test_fetch_probe_metrics_nonfinite_summary_falls_back() -> None:
    rows = [{"_step": 0, "loss": 3.0}]
    run = _FakeRun(rows, summary={"loss": float("inf")})  # coerces to None
    api = _FakeApi(run)
    final, _ = judge.fetch_probe_metrics("ent/proj/r", api=api, loss_key="loss")
    assert final == 3.0


class _Run:
    def __init__(self, rid: str) -> None:
        self.id = rid


class _RunsApi:
    def __init__(self, runs: Any, raise_exc: bool = False) -> None:
        self._runs = runs
        self._raise = raise_exc

    def runs(self, path: str, filters: dict[str, Any] | None = None) -> Any:
        if self._raise:
            raise RuntimeError("boom")
        return self._runs


def test_find_probe_run_returns_first() -> None:
    api = _RunsApi([_Run("run-a"), _Run("run-b")])
    assert judge.find_probe_run(api, "ent", "proj", "grp", "name") == "run-a"


def test_find_probe_run_none_on_exception() -> None:
    api = _RunsApi([], raise_exc=True)
    assert judge.find_probe_run(api, "ent", "proj", "grp", "name") is None


def test_find_probe_run_none_when_empty() -> None:
    api = _RunsApi([])
    assert judge.find_probe_run(api, "ent", "proj", "grp", "name") is None
