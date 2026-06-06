from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from keepalive.config import Settings
from keepalive.probes.cursor import IntegrationNotConnectedError
from keepalive.types import (
    Diagnosis,
    FailureEvent,
    FailureKind,
    FixHypothesis,
    HumanReply,
    KeepaliveHandedOff,
    KeepaliveRollback,
    KeepaliveStop,
    ProbeResult,
    ProbeSpec,
    ProbeState,
)
from keepalive.watchdog import Watchdog

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _hyps(n: int = 2) -> list[FixHypothesis]:
    return [FixHypothesis(id=f"h{i}", title=f"title {i}", rationale=f"r{i}", instructions=f"do {i}") for i in range(n)]


class FakeEngine:
    def __init__(self, hypotheses: list[FixHypothesis] | None = None) -> None:
        self._hyps = _hyps() if hypotheses is None else hypotheses
        self.incidents: list[Any] = []

    def diagnose(self, incident: Any, fetcher: Any) -> Diagnosis:
        self.incidents.append(incident)
        return Diagnosis(summary="diverged", category="divergence", confidence=0.8, hypotheses=list(self._hyps))


class FakeEscalation:
    def __init__(self) -> None:
        self.notify_count = 0
        self.recaps: list[str] = []
        self.scripts: list[str | None] = []

    def notify_incident(self, incident: Any, voice_script: str | None = None) -> None:
        self.notify_count += 1
        self.scripts.append(voice_script)

    def fetch_reply(self, incident_id: str) -> HumanReply | None:  # pragma: no cover - overridden via deadline
        return None

    def send_recap(self, incident: Any, message: str) -> None:
        self.recaps.append(message)


class FakeDeadline:
    def __init__(self, reply: HumanReply | None = None) -> None:
        self._reply = reply
        self.armed: list[Any] = []

    def arm(self, incident_id: str, timeout_s: float) -> float:
        self.armed.append((incident_id, timeout_s))
        return 1000.0

    def await_human(self, incident_id: str, fetch_reply: Any, poll_interval: float = 2.0) -> HumanReply | None:
        return self._reply


class FakeMemory:
    def __init__(self) -> None:
        self.remembered: list[tuple[Any, str]] = []

    def remember(self, incident: Any, note: str) -> None:
        self.remembered.append((incident, note))


class FakeRouter:
    def classify(self, message: str) -> str:
        return "divergence"


class FakeCursor:
    def __init__(self, branch_state: ProbeState = ProbeState.READY, spawn_exc: Exception | None = None) -> None:
        self._branch_state = branch_state
        self._spawn_exc = spawn_exc
        self.spawn_count = 0

    def spawn_probe(self, hyp: FixHypothesis, ctx: Any, incident_id: str) -> ProbeSpec:
        self.spawn_count += 1
        if self._spawn_exc is not None:
            raise self._spawn_exc
        spec = ProbeSpec(id=f"probe_{self.spawn_count}", incident_id=incident_id, hypothesis=hyp)
        spec.branch = f"cursor/probe-{spec.id}"
        spec.agent_id = f"agent-{self.spawn_count}"
        spec.state = ProbeState.WRITING
        return spec

    def wait_for_branch(self, spec: ProbeSpec) -> ProbeSpec:
        spec.state = self._branch_state
        if self._branch_state != ProbeState.READY:
            spec.branch = None
        return spec


class FakeExecutor:
    """Returns FINISHED results; the first executed spec gets the lowest loss (winner)."""

    def __init__(self, all_fail: bool = False) -> None:
        self._all_fail = all_fail
        self._n = 0
        self.executed: list[str] = []
        self.killed: list[str] = []

    def execute(self, spec: ProbeSpec, ctx: Any, *, steps: int) -> ProbeResult:
        self.executed.append(spec.id)
        if self._all_fail:
            spec.state = ProbeState.FAILED
            return ProbeResult(
                spec=spec, wandb_run_id=None, history=[], final_loss=None, state=ProbeState.FAILED, error="nope"
            )
        # winner = whichever spec was spawned first ("probe_1")
        loss = 0.1 if spec.id == "probe_1" else 9.0
        spec.state = ProbeState.FINISHED
        return ProbeResult(
            spec=spec, wandb_run_id="r-" + spec.id, history=[], final_loss=loss, state=ProbeState.FINISHED
        )

    def kill(self, spec: ProbeSpec) -> None:
        self.killed.append(spec.id)


def _build(
    tmp_path: Path,
    *,
    settings: Settings | None = None,
    reply: HumanReply | None = None,
    engine_hyps: list[FixHypothesis] | None = None,
    cursor: FakeCursor | None = None,
    executor: FakeExecutor | None = None,
    escalation: FakeEscalation | None = None,
    memory: FakeMemory | None = None,
    run: Any = None,
) -> tuple[Watchdog, dict[str, Any]]:
    # one checkpoint file so last_checkpoint is set
    ckpt = tmp_path / "ckpt"
    ckpt.mkdir(exist_ok=True)
    (ckpt / "last.pt").write_text("x")

    s = settings or Settings(
        api_key="k",
        telegram_chat_id="1",
        reply_poll_interval_s=0,
        probe_steps=5,
        max_probes=3,
        escalation_timeout_s=1,
    )
    eng = FakeEngine(engine_hyps if engine_hyps is not None else None)
    esc = escalation or FakeEscalation()
    dl = FakeDeadline(reply)
    mem = memory or FakeMemory()
    cur = cursor or FakeCursor()
    ex = executor or FakeExecutor()

    wd = Watchdog(
        run=run,
        settings=s,
        engine=eng,
        escalation=esc,
        deadline=dl,
        memory_=mem,
        router=FakeRouter(),
        bus=None,
        cursor=cur,
        executor=ex,
        suite=object(),  # never used in these tests
        checkpoint_dir=str(ckpt),
        entrypoint=["python", "train.py"],
    )
    return wd, {"engine": eng, "esc": esc, "dl": dl, "mem": mem, "cursor": cur, "ex": ex}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _event() -> FailureEvent:
    return FailureEvent(kind=FailureKind.NAN_LOSS, step=400, message="loss is nan")


def test_reply_stop_raises_and_remembers(tmp_path: Path) -> None:
    wd, deps = _build(tmp_path, reply=HumanReply.STOP)
    with pytest.raises(KeepaliveStop):
        wd.handle_failure(_event())

    assert deps["esc"].notify_count == 1
    assert any("stop" in n.lower() for _, n in deps["mem"].remembered)
    assert any("stopped" in r.lower() for r in deps["esc"].recaps)
    # no probes spawned
    assert deps["cursor"].spawn_count == 0


def test_reply_rollback_raises_with_checkpoint(tmp_path: Path) -> None:
    wd, deps = _build(tmp_path, reply=HumanReply.ROLLBACK)
    with pytest.raises(KeepaliveRollback) as ei:
        wd.handle_failure(_event())
    assert ei.value.checkpoint == wd.ctx.last_checkpoint
    assert wd.ctx.last_checkpoint is not None
    assert deps["esc"].notify_count == 1
    assert deps["cursor"].spawn_count == 0


def test_timeout_goes_autonomous_and_hands_off(tmp_path: Path) -> None:
    wd, deps = _build(tmp_path, reply=None)
    with pytest.raises(KeepaliveHandedOff) as ei:
        wd.handle_failure(_event())

    # spawn called once per hypothesis (engine returns 2)
    assert deps["cursor"].spawn_count == 2
    # both probes executed
    assert len(deps["ex"].executed) == 2
    winner = ei.value.winner
    assert winner.spec.id == "probe_1"
    # recap mentions the winning branch
    assert any(winner.spec.branch in r for r in deps["esc"].recaps)
    assert deps["esc"].notify_count == 1


def test_all_probes_fail_raises_stop_and_marks_failed(tmp_path: Path) -> None:
    wd, deps = _build(tmp_path, reply=None, executor=FakeExecutor(all_fail=True))
    with pytest.raises(KeepaliveStop) as ei:
        wd.handle_failure(_event())
    assert "all probes failed" in str(ei.value)
    # status FAILED observable via remember note
    assert any("all probes failed" in n for _, n in deps["mem"].remembered)


def test_empty_hypotheses_stops_without_cursor(tmp_path: Path) -> None:
    wd, deps = _build(tmp_path, reply=None, engine_hyps=[])
    with pytest.raises(KeepaliveStop) as ei:
        wd.handle_failure(_event())
    assert "no fix hypotheses" in str(ei.value)
    assert deps["cursor"].spawn_count == 0


def test_no_escalation_configured_skips_notify(tmp_path: Path) -> None:
    # settings without api_key/chat id -> escalate disabled -> straight autonomous
    s = Settings(reply_poll_interval_s=0, probe_steps=5, max_probes=3, escalation_timeout_s=1)
    wd, deps = _build(tmp_path, settings=s, reply=HumanReply.STOP)
    # reply is scripted STOP but await_human is never called since escalation disabled
    with pytest.raises(KeepaliveHandedOff):
        wd.handle_failure(_event())
    assert deps["esc"].notify_count == 0
    assert deps["cursor"].spawn_count == 2


def test_reentrancy_second_call_returns_immediately(tmp_path: Path) -> None:
    wd, deps = _build(tmp_path, reply=HumanReply.STOP)
    with pytest.raises(KeepaliveStop):
        wd.handle_failure(_event())
    notify_after_first = deps["esc"].notify_count
    # _handling is now True; second call returns immediately (no exception, no notify)
    wd.handle_failure(_event())
    assert deps["esc"].notify_count == notify_after_first


def test_context_manager_exception_routes_exception_event(tmp_path: Path) -> None:
    from .conftest import FakeRun

    run = FakeRun()
    wd, deps = _build(tmp_path, reply=HumanReply.STOP, run=run)

    # entering via the manual context manager; body raises ValueError -> __exit__
    # converts it to an EXCEPTION FailureEvent and calls handle_failure, whose
    # KeepaliveStop propagates out.
    with pytest.raises(KeepaliveStop):
        with wd:
            raise ValueError("boom")

    # engine received an incident whose failure kind is EXCEPTION
    assert deps["engine"].incidents
    assert deps["engine"].incidents[-1].failure.kind == FailureKind.EXCEPTION


def test_integration_not_connected_stops_with_recap(tmp_path: Path) -> None:
    cursor = FakeCursor(spawn_exc=IntegrationNotConnectedError())
    wd, deps = _build(tmp_path, reply=None, cursor=cursor)
    with pytest.raises(KeepaliveStop) as ei:
        wd.handle_failure(_event())
    assert "not connected" in str(ei.value).lower()
    assert any("integrations" in r.lower() or "not connected" in r.lower() for r in deps["esc"].recaps)


def test_no_redis_url_engages_local_fallbacks() -> None:
    from keepalive.watchdog import _LocalDeadlines

    wd = Watchdog(run=None, settings=Settings(api_key="k"))

    assert wd._redis_client() is None
    assert isinstance(wd.deadline, _LocalDeadlines)
    assert wd.bus is None
    assert wd.router is None
    assert wd.cache is None


def test_default_suite_inherits_loss_key() -> None:
    wd = Watchdog(run=None, settings=Settings(api_key="k"), loss_key="train/loss")
    keys = {getattr(d, "loss_key", None) for d in wd.suite.detectors}
    assert keys == {"train/loss"}


def test_agent_memory_requires_explicit_url() -> None:
    from keepalive.memory.incidents import IncidentMemory

    mem = IncidentMemory(Settings())
    assert mem.available is False
    assert mem._client() is None
    assert mem.recall(_event()) == []
