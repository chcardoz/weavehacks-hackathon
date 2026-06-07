from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger("keepalive_api.events_log")

_INSERT_EVENT = """
    INSERT INTO event (project_id, incident_id, agent_id, source, level, type, message, data, created_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
"""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def log_event(
    pool: asyncpg.Pool | None,
    *,
    project_id: str,
    incident_id: str | None = None,
    agent_id: str | None = None,
    source: str = "relay",
    level: str = "info",
    type: str = "log",
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Best-effort self-logging insert of an event row. Swallows all exceptions."""
    if pool is None:
        return
    try:
        await pool.execute(
            _INSERT_EVENT,
            project_id,
            incident_id,
            agent_id,
            source,
            level,
            type,
            message,
            json.dumps(data or {}),
            _now(),
        )
    except Exception:
        logger.warning("self-log failed for project_id=%s type=%s", project_id, type, exc_info=True)
