from __future__ import annotations

from keepalive.config import Settings
from keepalive.types import Incident


class VoiceNoteBuilder:
    """Writes the voice-note script; the relay synthesizes and sends it server-side."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def script_for(self, incident: Incident) -> str:
        failure = incident.failure
        diagnosis = (
            incident.diagnosis.summary
            if incident.diagnosis is not None and incident.diagnosis.summary
            else "I'm still pinning down the exact cause"
        )
        if incident.deadline_ts is not None:
            seconds = max(0, int(incident.deadline_ts - incident.created_at))
        else:
            seconds = int(self.settings.escalation_timeout_s)
        return (
            f"Hey, this is keepalive. Your training run hit a {failure.kind} at step {failure.step}. "
            f"{diagnosis}. If I don't hear from you in {seconds} seconds, I'm sending in the probes "
            f"to test fixes automatically. Tap a button, or reply one to roll back, "
            f"two to apply a fix, or three to stop the run."
        )
