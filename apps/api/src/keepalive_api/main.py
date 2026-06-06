from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from keepalive_api.config import ApiSettings
from keepalive_api.routes import api_router


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    resolved = settings or ApiSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved
        app.state.redis = aioredis.from_url(resolved.redis_url, decode_responses=False)

        if resolved.database_url:
            import asyncpg

            app.state.pg_pool = await asyncpg.create_pool(resolved.database_url)
        else:
            app.state.pg_pool = None

        if resolved.telegram_configured:
            import httpx

            app.state.telegram = httpx.AsyncClient(
                base_url=f"https://api.telegram.org/bot{resolved.telegram_bot_token}",
                timeout=15,
            )
        else:
            app.state.telegram = None

        if resolved.openai_configured:
            import httpx

            app.state.openai = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={"Authorization": f"Bearer {resolved.openai_api_key}"},
                timeout=120,
            )
        else:
            app.state.openai = None

        try:
            yield
        finally:
            await app.state.redis.aclose()
            if app.state.pg_pool is not None:
                await app.state.pg_pool.close()
            if app.state.telegram is not None:
                await app.state.telegram.aclose()
            if app.state.openai is not None:
                await app.state.openai.aclose()

    app = FastAPI(title="keepalive-api", lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(api_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("keepalive_api.main:app", host="0.0.0.0", port=8000)
