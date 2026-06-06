from __future__ import annotations

from urllib.parse import urljoin

import httpx

from keepalive.config import Settings
from keepalive.types import HumanReply, Incident


def _short_message(incident: Incident) -> str:
    failure = incident.failure
    parts = [f"keepalive: {failure.kind} at step {failure.step}"]
    if incident.diagnosis is not None and incident.diagnosis.summary:
        parts.append(incident.diagnosis.summary)
    parts.append("reply 1=rollback 2=apply fix 3=stop")
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

    def notify_incident(self, incident: Incident, voice_note_url: str | None = None) -> None:
        payload = {
            "incident_id": incident.id,
            "kind": "incident",
            "message": _short_message(incident),
            "voice_note_url": voice_note_url,
            "trace_url": incident.trace_url,
            "to_phone": self.settings.phone_number,
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
            "voice_note_url": None,
            "trace_url": incident.trace_url,
            "to_phone": self.settings.phone_number,
        }
        resp = self.http.post("/v1/notify", json=payload)
        resp.raise_for_status()

    def upload_voice_note(self, incident_id: str, mp3: bytes) -> str:
        resp = self.http.post(
            "/v1/voice-notes",
            params={"incident_id": incident_id},
            content=mp3,
            headers={"Content-Type": "audio/mpeg"},
        )
        resp.raise_for_status()
        url = resp.json()["url"]
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return urljoin(self.settings.api_url, url)
