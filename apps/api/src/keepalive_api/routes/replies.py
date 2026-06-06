from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_redis
from keepalive_api.models import ReplyResponse

router = APIRouter()


@router.get("/v1/incidents/{incident_id}/reply")
async def get_reply(incident_id: str, request: Request, _: str = Depends(require_api_key)) -> ReplyResponse:
    redis = get_redis(request)
    value = await redis.get(f"reply:{incident_id}")
    if value is None:
        return ReplyResponse(reply=None)
    reply = value.decode() if isinstance(value, bytes) else str(value)
    return ReplyResponse(reply=reply)
