from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Request

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_openai, get_pg_pool, get_redis, get_settings, get_telegram
from keepalive_api.events_log import log_event
from keepalive_api.models import NotifyRequest

logger = logging.getLogger("keepalive_api.notify")

router = APIRouter()

_MAX_TEXT_LEN = 4096  # Telegram sendMessage limit
_MAX_TTS_INPUT_LEN = 4096  # OpenAI speech input limit


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


async def _synthesize_voice(request: Request, script: str) -> str | None:
    """TTS the script with the relay's OpenAI key and host the mp3 for Telegram to fetch.

    Best-effort: any failure returns None and the text notify proceeds without a voice bubble.
    """
    openai = get_openai(request)
    if openai is None:
        logger.info("openai not configured; skipping voice synthesis")
        return None

    settings = get_settings(request)
    resp = await openai.post(
        "/audio/speech",
        json={
            "model": settings.tts_model,
            "voice": settings.tts_voice,
            "input": script[:_MAX_TTS_INPUT_LEN],
            "response_format": "mp3",
        },
    )
    if resp.is_error:
        logger.warning("tts failed (%s): %s", resp.status_code, resp.text[:500])
        return None

    note_id = secrets.token_urlsafe(8)
    await get_redis(request).set(f"audio:{note_id}", resp.content, ex=settings.voice_note_ttl_s)
    return f"{settings.public_base_url}/a/{note_id}.mp3"


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

    voice_sent = False
    if req.voice_script:
        voice_url = await _synthesize_voice(request, req.voice_script)
        if voice_url:
            voice_resp = await telegram.post("/sendVoice", json={"chat_id": req.chat_id, "voice": voice_url})
            if voice_resp.is_error:
                logger.warning("sendVoice failed (%s): %s", voice_resp.status_code, voice_resp.text)
            else:
                voice_sent = True

    await _self_log(request, req, voice_sent=voice_sent)
    return {"sent": True}


async def _self_log(request: Request, req: NotifyRequest, *, voice_sent: bool) -> None:
    """Best-effort: record a relay event that the Telegram message was sent.

    notify only knows incident_id + chat_id, so we resolve project_id via the incident
    row. If the incident isn't in the DB yet, skip self-logging silently.
    """
    pool = get_pg_pool(request)
    if pool is None:
        return
    try:
        row = await pool.fetchrow("SELECT project_id FROM incident WHERE id = $1", req.incident_id)
    except Exception:
        return
    if row is None:
        return
    await log_event(
        pool,
        project_id=str(row["project_id"]),
        incident_id=req.incident_id,
        source="relay",
        type="log",
        message=f"telegram {req.kind} sent",
        data={"voice_sent": voice_sent, "chat_id": req.chat_id},
    )
