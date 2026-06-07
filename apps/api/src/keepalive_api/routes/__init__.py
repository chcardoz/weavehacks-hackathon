from __future__ import annotations

from fastapi import APIRouter

from keepalive_api.routes import commands, events, llm, notify, replies, telegram, voice

api_router = APIRouter()
api_router.include_router(notify.router)
api_router.include_router(telegram.router)
api_router.include_router(replies.router)
api_router.include_router(voice.router)
api_router.include_router(llm.router)
api_router.include_router(events.router)
api_router.include_router(commands.router)

__all__ = ["api_router"]
