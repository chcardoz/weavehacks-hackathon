from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

from keepalive_api.config import ApiSettings

if TYPE_CHECKING:
    import asyncpg
    import redis.asyncio as aioredis
    from twilio.rest import Client as TwilioClient


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def get_pg_pool(request: Request) -> asyncpg.Pool | None:
    return request.app.state.pg_pool


def get_twilio(request: Request) -> TwilioClient | None:
    return request.app.state.twilio
