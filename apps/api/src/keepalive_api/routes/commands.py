from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_pg_pool

logger = logging.getLogger("keepalive_api.commands")

router = APIRouter()

_CONSUME_COMMANDS = """
    UPDATE command
    SET status = 'consumed', consumed_at = now()
    WHERE project_id = $1 AND status = 'pending'
    RETURNING id, type, created_at
"""


@router.get("/v1/projects/{project_id}/commands")
async def get_commands(
    project_id: str,
    request: Request,
    _: str = Depends(require_api_key),
) -> dict[str, list[dict[str, Any]]]:
    pool = get_pg_pool(request)
    if pool is None:
        return {"commands": []}

    rows = await pool.fetch(_CONSUME_COMMANDS, project_id)
    commands = [
        {
            "id": row["id"],
            "type": row["type"],
            "created_at": row["created_at"].isoformat() if row["created_at"] is not None else None,
        }
        for row in rows
    ]
    return {"commands": commands}
