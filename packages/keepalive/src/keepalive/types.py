from __future__ import annotations

import enum
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class FailureKind(enum.StrEnum):
    NAN_LOSS = "nan_loss"
    DIVERGENCE = "divergence"
    STALL = "stall"
    OOM = "oom"
    EXCEPTION = "exception"


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
    repo_owner: str
    repo_name: str
    branch: str
    entrypoint: list[str]
    checkpoint_dir: str
    loss_key: str = "loss"

    @property
    def run_path(self) -> str:
        return f"{self.entity}/{self.project}/{self.run_id}"


@runtime_checkable
class Detector(Protocol):
    name: str

    def check(self, snapshot: MetricSnapshot, history: Sequence[MetricSnapshot]) -> FailureEvent | None: ...


class KeepaliveError(Exception):
    pass


class KeepaliveStop(KeepaliveError):
    pass
