from __future__ import annotations

import enum
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class FailureKind(enum.StrEnum):
    NAN_LOSS = "nan_loss"
    DIVERGENCE = "divergence"
    STALL = "stall"
    OOM = "oom"
    EXCEPTION = "exception"


class IncidentStatus(enum.StrEnum):
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    ESCALATED = "escalated"
    HUMAN_RESPONDED = "human_responded"
    AUTONOMOUS = "autonomous"
    PROBING = "probing"
    RESOLVED = "resolved"
    STOPPED = "stopped"
    FAILED = "failed"


class HumanReply(enum.StrEnum):
    ROLLBACK = "1"
    APPLY_FIX = "2"
    STOP = "3"


class ProbeState(enum.StrEnum):
    PENDING = "pending"
    WRITING = "writing"
    READY = "ready"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    KILLED = "killed"


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    step: int
    metrics: dict[str, float]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class FailureEvent:
    kind: FailureKind
    step: int
    message: str
    metrics: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    project: str
    entity: str
    run_url: str
    commit_sha: str
    repo_url: str
    entrypoint: list[str]
    checkpoint_dir: str
    last_checkpoint: str | None = None
    loss_key: str = "loss"

    @property
    def run_path(self) -> str:
        return f"{self.entity}/{self.project}/{self.run_id}"


@dataclass(frozen=True, slots=True)
class FixHypothesis:
    id: str
    title: str
    rationale: str
    instructions: str


@dataclass(slots=True)
class Diagnosis:
    summary: str
    category: str
    confidence: float
    hypotheses: list[FixHypothesis]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProbeSpec:
    id: str
    incident_id: str
    hypothesis: FixHypothesis
    branch: str | None = None
    agent_id: str | None = None
    state: ProbeState = ProbeState.PENDING


@dataclass(slots=True)
class ProbeResult:
    spec: ProbeSpec
    wandb_run_id: str | None
    history: list[MetricSnapshot]
    final_loss: float | None
    state: ProbeState
    error: str | None = None


@dataclass(slots=True)
class Incident:
    id: str
    run: RunContext
    failure: FailureEvent
    status: IncidentStatus = IncidentStatus.DETECTED
    diagnosis: Diagnosis | None = None
    deadline_ts: float | None = None
    probes: list[ProbeSpec] = field(default_factory=list)
    winner_probe_id: str | None = None
    reply: HumanReply | None = None
    trace_url: str | None = None
    created_at: float = field(default_factory=time.time)


@runtime_checkable
class Detector(Protocol):
    name: str

    def check(self, snapshot: MetricSnapshot, history: Sequence[MetricSnapshot]) -> FailureEvent | None: ...


@runtime_checkable
class ProbeExecutor(Protocol):
    def execute(self, spec: ProbeSpec, ctx: RunContext, *, steps: int) -> ProbeResult: ...

    def kill(self, spec: ProbeSpec) -> None: ...


class KeepaliveError(Exception):
    pass


class KeepaliveStop(KeepaliveError):
    pass


class KeepaliveRollback(KeepaliveError):
    def __init__(self, checkpoint: str | None) -> None:
        super().__init__(f"rollback to {checkpoint}")
        self.checkpoint = checkpoint


class KeepaliveHandedOff(KeepaliveError):
    def __init__(self, incident: Incident, winner: ProbeResult) -> None:
        super().__init__(f"training handed off to probe {winner.spec.id}")
        self.incident = incident
        self.winner = winner
