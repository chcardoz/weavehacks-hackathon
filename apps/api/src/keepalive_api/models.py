from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NotifyRequest(BaseModel):
    incident_id: str
    kind: Literal["incident", "recap"] = "incident"
    message: str
    voice_script: str | None = None
    trace_url: str | None = None
    chat_id: str


class ReplyResponse(BaseModel):
    reply: str | None


class ProjectMeta(BaseModel):
    """Optional project metadata carried on events; upserts the project row."""

    name: str | None = None
    repo: str | None = None
    wandb_run_id: str | None = None
    wandb_url: str | None = None
    commit_sha: str | None = None
    demo_mode: bool | None = None


class EventIn(BaseModel):
    project_id: str
    project: ProjectMeta | None = None
    incident_id: str | None = None
    agent_id: str | None = None
    source: str = "library"
    level: str = "info"
    type: str = "log"
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    ts: str | None = None


class EventsRequest(BaseModel):
    # Cap at 100 items: extra events are rejected with 422 (see route validation).
    events: list[EventIn]
