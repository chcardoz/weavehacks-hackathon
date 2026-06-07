from __future__ import annotations

from .config import Settings
from .demo import CommandPoller, FaultInjector
from .reporter import EventReporter, NullReporter, build_reporter
from .types import (
    Diagnosis,
    FailureEvent,
    FailureKind,
    FixHypothesis,
    HumanReply,
    Incident,
    IncidentStatus,
    KeepaliveError,
    KeepaliveHandedOff,
    KeepaliveRollback,
    KeepaliveStop,
    MetricSnapshot,
    ProbeExecutor,
    ProbeResult,
    ProbeSpec,
    ProbeState,
    RunContext,
)
from .watchdog import Watchdog, watchdog

__version__ = "0.1.0"

__all__ = [
    "CommandPoller",
    "Diagnosis",
    "EventReporter",
    "FailureEvent",
    "FailureKind",
    "FaultInjector",
    "FixHypothesis",
    "HumanReply",
    "Incident",
    "IncidentStatus",
    "KeepaliveError",
    "KeepaliveHandedOff",
    "KeepaliveRollback",
    "KeepaliveStop",
    "MetricSnapshot",
    "NullReporter",
    "ProbeExecutor",
    "ProbeResult",
    "ProbeSpec",
    "ProbeState",
    "RunContext",
    "Settings",
    "Watchdog",
    "__version__",
    "build_reporter",
    "watchdog",
]
