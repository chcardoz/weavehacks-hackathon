from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_redis, get_settings, get_twilio
from keepalive_api.models import NotifyRequest

logger = logging.getLogger("keepalive_api.notify")

router = APIRouter()

_MAX_SMS_LEN = 1600


def _compose_body(req: NotifyRequest) -> str:
    parts = [req.message]
    if req.voice_note_url:
        parts.append(f"🎧 voice note: {req.voice_note_url}")
    if req.trace_url:
        parts.append(f"🧵 trace: {req.trace_url}")
    body = "\n".join(parts)
    return body[:_MAX_SMS_LEN]


@router.post("/v1/notify")
async def notify(req: NotifyRequest, request: Request, _: str = Depends(require_api_key)) -> dict[str, bool]:
    settings = get_settings(request)
    redis = get_redis(request)
    twilio = get_twilio(request)

    body = _compose_body(req)

    if req.kind == "incident":
        await redis.set(f"active:{req.to_phone}", req.incident_id, ex=86400)

    if twilio is None:
        logger.info("twilio not configured; dev-mode notify to %s: %s", req.to_phone, body)
        return {"sent": False}

    await run_in_threadpool(
        twilio.messages.create,
        to=req.to_phone,
        from_=settings.twilio_from_number,
        body=body,
    )
    return {"sent": True}
