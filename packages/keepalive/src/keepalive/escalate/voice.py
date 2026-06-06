from __future__ import annotations

from typing import Any

from keepalive.config import Settings
from keepalive.types import Incident


class VoiceNoteBuilder:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client

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
            f"to test fixes automatically. Reply one to roll back, two to apply a fix, "
            f"or three to stop the run."
        )

    def synthesize(self, text: str) -> bytes:
        client = self.client
        if client is None:
            import openai

            client = openai.OpenAI(api_key=self.settings.openai_api_key)
        response = client.audio.speech.create(
            model=self.settings.tts_model,
            voice=self.settings.tts_voice,
            input=text,
            response_format="mp3",
        )
        content = getattr(response, "content", None)
        if isinstance(content, bytes):
            return content
        read = getattr(response, "read", None)
        if callable(read):
            return read()
        if isinstance(response, bytes):
            return response
        raise TypeError("TTS response did not expose bytes via .content or .read()")
