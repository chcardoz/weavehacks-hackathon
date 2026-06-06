from __future__ import annotations

import httpx

from keepalive.config import Settings
from keepalive.types import HumanReply, Incident


def _short_message(incident: Incident) -> str:
    failure = incident.failure
    parts = [f"keepalive: {failure.kind} at step {failure.step}"]
    if incident.diagnosis is not None and incident.diagnosis.summary:
        parts.append(incident.diagnosis.summary)
    parts.append("tap a button or reply 1=rollback 2=apply fix 3=stop")
    if incident.deadline_ts is not None:
        remaining = max(0, int(incident.deadline_ts - incident.created_at))
        parts.append(f"deadline {remaining}s")
    return ". ".join(parts)


class EscalationClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None) -> None:
        self.settings = settings
        self.http = http or httpx.Client(
            base_url=settings.api_url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=15,
        )

    def notify_incident(self, incident: Incident, voice_script: str | None = None) -> None:
        payload = {
            "incident_id": incident.id,
            "kind": "incident",
            "message": _short_message(incident),
            "voice_script": voice_script,
            "trace_url": incident.trace_url,
            "chat_id": self.settings.telegram_chat_id,
        }
        resp = self.http.post("/v1/notify", json=payload)
        resp.raise_for_status()

    def fetch_reply(self, incident_id: str) -> HumanReply | None:
        try:
            resp = self.http.get(f"/v1/incidents/{incident_id}/reply")
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        raw = data.get("reply")
        if raw is None:
            return None
        try:
            return HumanReply(str(raw))
        except ValueError:
            return None

    def send_recap(self, incident: Incident, message: str) -> None:
        payload = {
            "incident_id": incident.id,
            "kind": "recap",
            "message": message,
            "voice_script": None,
            "trace_url": incident.trace_url,
            "chat_id": self.settings.telegram_chat_id,
        }
        resp = self.http.post("/v1/notify", json=payload)
        resp.raise_for_status()
