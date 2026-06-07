from __future__ import annotations

from typing import Any

from keepalive.probes.executor import race
from keepalive.types import (
    FixHypothesis,
    ProbeResult,
    ProbeSpec,
    ProbeState,
    RunContext,
)


def _ctx() -> RunContext:
    return RunContext(
        run_id="run1",
        project="proj",
        entity="ent",
        run_url="u",
        commit_sha="sha",
        repo_url="https://github.com/me/repo",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
        loss_key="loss",
    )


def _spec(pid: str, state: ProbeState = ProbeState.READY, branch: str | None = "b") -> ProbeSpec:
    h = FixHypothesis(id="h", title="t", rationale="r", instructions="i")
    return ProbeSpec(id=pid, incident_id="inc1", hypothesis=h, state=state, branch=branch)


class FakeExecutor:
    def __init__(self, results: dict[str, Any], raises: dict[str, Exception] | None = None) -> None:
        self._results = results  # spec.id -> ProbeResult or (loss, state)
        self._raises = raises or {}
        self.executed: list[str] = []
        self.killed: list[str] = []

    def execute(self, spec: ProbeSpec, ctx: RunContext, *, steps: int) -> ProbeResult:
        self.executed.append(spec.id)
        if spec.id in self._raises:
            raise self._raises[spec.id]
        loss, state = self._results[spec.id]
        spec.state = state
        return ProbeResult(spec=spec, wandb_run_id="r-" + spec.id, history=[], final_loss=loss, state=state)

    def kill(self, spec: ProbeSpec) -> None:
        self.killed.append(spec.id)


def test_all_ready_run_argmin_winner_others_killed() -> None:
    specs = [_spec("a"), _spec("b"), _spec("c")]
    ex = FakeExecutor(
        {
            "a": (2.0, ProbeState.FINISHED),
            "b": (1.0, ProbeState.FINISHED),
            "c": (3.0, ProbeState.FINISHED),
        }
    )
    updates: list[ProbeResult] = []
    winner, results = race(specs, ex, _ctx(), steps=5, on_update=updates.append)

    assert winner is not None
    assert winner.spec.id == "b"
    assert set(ex.executed) == {"a", "b", "c"}
    # winner not killed; the two losers are
    assert set(ex.killed) == {"a", "c"}
    # on_update called once per result
    assert len(updates) == 3
    assert all(isinstance(u, ProbeResult) for u in updates)
    assert len(results) == 3


def test_pending_or_no_branch_specs_become_failed_no_execute() -> None:
    specs = [
        _spec("ready", ProbeState.READY, branch="b"),
        _spec("pending", ProbeState.PENDING, branch="b"),
        _spec("nobranch", ProbeState.READY, branch=None),
    ]
    ex = FakeExecutor({"ready": (1.0, ProbeState.FINISHED)})
    updates: list[ProbeResult] = []
    winner, results = race(specs, ex, _ctx(), steps=5, on_update=updates.append)

    assert winner is not None
    assert winner.spec.id == "ready"
    assert ex.executed == ["ready"]

    by_id = {r.spec.id: r for r in results}
    assert by_id["pending"].state == ProbeState.FAILED
    assert by_id["pending"].error == "no branch"
    assert by_id["nobranch"].state == ProbeState.FAILED
    assert by_id["nobranch"].error == "no branch"
    assert len(updates) == 3


def test_executor_raising_marks_probe_failed_others_complete() -> None:
    specs = [_spec("a"), _spec("b")]
    ex = FakeExecutor(
        {"b": (1.0, ProbeState.FINISHED)},
        raises={"a": RuntimeError("kaboom")},
    )
    winner, results = race(specs, ex, _ctx(), steps=5)

    by_id = {r.spec.id: r for r in results}
    assert by_id["a"].state == ProbeState.FAILED
    assert "kaboom" in (by_id["a"].error or "")
    assert by_id["b"].state == ProbeState.FINISHED
    assert winner is not None
    assert winner.spec.id == "b"


def test_empty_specs() -> None:
    ex = FakeExecutor({})
    winner, results = race([], ex, _ctx(), steps=5)
    assert winner is None
    assert results == []
    assert ex.executed == []
    assert ex.killed == []
