from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NotifyRequest(BaseModel):
    incident_id: str
    kind: Literal["incident", "recap"] = "incident"
    message: str
    voice_note_url: str | None = None
    trace_url: str | None = None
    to_phone: str


class ReplyResponse(BaseModel):
    reply: str | None


class VoiceNoteResponse(BaseModel):
    url: str
