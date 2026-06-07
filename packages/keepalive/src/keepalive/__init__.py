from __future__ import annotations

from .config import Settings
from .types import (
    FailureEvent,
    FailureKind,
    KeepaliveError,
    KeepaliveStop,
    MetricSnapshot,
    RunContext,
)
from .watchdog import Watchdog, watchdog

__version__ = "0.2.0"

__all__ = [
    "FailureEvent",
    "FailureKind",
    "KeepaliveError",
    "KeepaliveStop",
    "MetricSnapshot",
    "RunContext",
    "Settings",
    "Watchdog",
    "__version__",
    "watchdog",
]
