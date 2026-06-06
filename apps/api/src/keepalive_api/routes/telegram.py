from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from keepalive_api.deps import get_redis, get_settings, get_telegram

logger = logging.getLogger("keepalive_api.telegram")

router = APIRouter()

_ACTION_REPLIES = {
    "1": "rolling back to the last good checkpoint.",
    "2": "applying the fix.",
    "3": "stopping the run.",
}
_HELP_TEXT = "Tap a button on the incident message, or reply 1 to roll back, 2 to apply the fix, or 3 to stop the run."


async def _send_text(telegram: httpx.AsyncClient | None, chat_id: object, text: str) -> None:
    if telegram is None:
        logger.info("telegram not configured; dev-mode reply to %s: %s", chat_id, text)
        return
    resp = await telegram.post("/sendMessage", json={"chat_id": chat_id, "text": text})
    if resp.is_error:
        logger.warning("sendMessage failed (%s): %s", resp.status_code, resp.text)


async def _answer_callback(telegram: httpx.AsyncClient | None, callback_id: str, text: str) -> None:
    """Always answer the callback query, or the user's client shows a spinner forever."""
    if telegram is None:
        return
    resp = await telegram.post("/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})
    if resp.is_error:
        logger.warning("answerCallbackQuery failed (%s): %s", resp.status_code, resp.text)


async def _handle_callback(callback: dict[str, Any], redis: Any, telegram: httpx.AsyncClient | None) -> None:
    # callback_data is "{incident_id}:{choice}" (set by /v1/notify's inline keyboard).
    incident_id, _, choice = str(callback.get("data", "")).rpartition(":")
    if incident_id and choice in _ACTION_REPLIES:
        await redis.set(f"reply:{incident_id}", choice, ex=86400)
        await _answer_callback(telegram, callback["id"], f"Got it — {_ACTION_REPLIES[choice]}")
    else:
        await _answer_callback(telegram, callback["id"], _HELP_TEXT)


async def _handle_message(message: dict[str, Any], redis: Any, telegram: httpx.AsyncClient | None) -> None:
    chat_id = message["chat"]["id"]
    text = str(message.get("text", "")).strip()

    if text.startswith("/start"):
        await _send_text(
            telegram,
            chat_id,
            f"keepalive is watching. Your chat id is {chat_id} — set KEEPALIVE_TELEGRAM_CHAT_ID={chat_id} on your training box.",
        )
        return

    if text in _ACTION_REPLIES:
        incident_id_raw = await redis.get(f"active:{chat_id}")
        if incident_id_raw is None:
            await _send_text(telegram, chat_id, "No active incident.")
            return
        incident_id = incident_id_raw.decode() if isinstance(incident_id_raw, bytes) else str(incident_id_raw)
        await redis.set(f"reply:{incident_id}", text, ex=86400)
        await _send_text(telegram, chat_id, f"Got it — {_ACTION_REPLIES[text]}")
        return

    await _send_text(telegram, chat_id, _HELP_TEXT)


@router.post("/telegram")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    settings = get_settings(request)
    redis = get_redis(request)
    telegram = get_telegram(request)

    if settings.telegram_webhook_secret:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="invalid telegram secret token")

    update = await request.json()

    callback = update.get("callback_query")
    if callback is not None:
        await _handle_callback(callback, redis, telegram)
        return {"ok": True}

    message = update.get("message")
    if message is not None and message.get("chat"):
        await _handle_message(message, redis, telegram)

    return {"ok": True}
