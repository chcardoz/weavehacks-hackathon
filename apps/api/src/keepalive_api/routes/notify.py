from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_redis, get_telegram
from keepalive_api.models import NotifyRequest

logger = logging.getLogger("keepalive_api.notify")

router = APIRouter()

_MAX_TEXT_LEN = 4096  # Telegram sendMessage limit


def _keyboard(req: NotifyRequest) -> dict[str, object] | None:
    """Inline keyboard: action buttons for incidents, plus a trace link if present.

    callback_data is capped at 64 bytes by Telegram — "{incident_id}:{choice}" fits
    comfortably for our inc_* ids.
    """
    rows: list[list[dict[str, str]]] = []
    if req.kind == "incident":
        rows.append(
            [
                {"text": "⏪ Roll back", "callback_data": f"{req.incident_id}:1"},
                {"text": "🔧 Apply fix", "callback_data": f"{req.incident_id}:2"},
                {"text": "🛑 Stop", "callback_data": f"{req.incident_id}:3"},
            ]
        )
    if req.trace_url:
        rows.append([{"text": "🧵 View trace", "url": req.trace_url}])
    return {"inline_keyboard": rows} if rows else None


@router.post("/v1/notify")
async def notify(req: NotifyRequest, request: Request, _: str = Depends(require_api_key)) -> dict[str, bool]:
    redis = get_redis(request)
    telegram = get_telegram(request)

    if req.kind == "incident":
        await redis.set(f"active:{req.chat_id}", req.incident_id, ex=86400)

    if telegram is None:
        logger.info("telegram not configured; dev-mode notify to %s: %s", req.chat_id, req.message)
        return {"sent": False}

    payload: dict[str, object] = {"chat_id": req.chat_id, "text": req.message[:_MAX_TEXT_LEN]}
    keyboard = _keyboard(req)
    if keyboard is not None:
        payload["reply_markup"] = keyboard
    resp = await telegram.post("/sendMessage", json=payload)
    resp.raise_for_status()

    if req.voice_note_url:
        # Best-effort: Telegram fetches the mp3 from our public voice-note URL and
        # renders it as a voice bubble. A failed voice send must not fail the notify.
        voice_resp = await telegram.post("/sendVoice", json={"chat_id": req.chat_id, "voice": req.voice_note_url})
        if voice_resp.is_error:
            logger.warning("sendVoice failed (%s): %s", voice_resp.status_code, voice_resp.text)

    return {"sent": True}
