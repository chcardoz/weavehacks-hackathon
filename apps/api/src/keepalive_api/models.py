from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NotifyRequest(BaseModel):
    incident_id: str
    kind: Literal["incident", "recap"] = "incident"
    message: str
    voice_script: str | None = None
    trace_url: str | None = None
    chat_id: str


class ReplyResponse(BaseModel):
    reply: str | None
