from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import fakeredis.aioredis
import httpx
import pytest

from keepalive_api.config import ApiSettings
from keepalive_api.main import create_app

DEV_KEY = "ka_live_test"


def make_settings(**overrides: object) -> ApiSettings:
    """Dev settings: dev key, no telegram creds, no database, fakeable redis url."""
    base: dict[str, object] = {
        "dev_keys": frozenset({DEV_KEY}),
        "database_url": "",
        "telegram_bot_token": "",
        "telegram_webhook_secret": "",
        "public_base_url": "http://localhost:8000",
        # redis_url is never connected to (we swap app.state.redis for a fake), but
        # from_url() is called during lifespan startup; a redis:// url constructs fine offline.
        "redis_url": "redis://localhost:6379/0",
    }
    base.update(overrides)
    return ApiSettings(**base)  # type: ignore[arg-type]


@asynccontextmanager
async def build_client(
    settings: ApiSettings | None = None,
    *,
    fake_redis: fakeredis.aioredis.FakeRedis | None = None,
    telegram: object | None = None,
) -> AsyncIterator[tuple[httpx.AsyncClient, object]]:
    """Create the app, run its lifespan, then swap in fakes on app.state.

    Yields (client, app) so tests can inspect/mutate app.state.
    """
    resolved = settings or make_settings()
    app = create_app(resolved)

    redis = fake_redis if fake_redis is not None else fakeredis.aioredis.FakeRedis(decode_responses=False)

    async with app.router.lifespan_context(app):
        # Replace the real (unconnected) redis client created during startup with a fake.
        # Close the real one so lifespan shutdown doesn't double-manage it.
        real_redis = app.state.redis
        real_telegram = app.state.telegram
        app.state.redis = redis
        if telegram is not None:
            app.state.telegram = telegram
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            try:
                yield client, app
            finally:
                # restore so lifespan shutdown closes the original objects it created
                app.state.redis = real_redis
                app.state.telegram = real_telegram


@pytest.fixture
def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {DEV_KEY}"}


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=False)


@pytest.fixture
async def client_app(fake_redis: fakeredis.aioredis.FakeRedis):
    """Default client with dev settings (telegram None) and a shared fake redis.

    Yields (client, app, redis).
    """
    async with build_client(make_settings(), fake_redis=fake_redis) as (client, app):
        yield client, app, fake_redis


class FakeTelegram:
    """Stands in for the httpx.AsyncClient on app.state.telegram."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def post(self, path: str, json: dict[str, object] | None = None) -> httpx.Response:
        payload = json or {}
        self.calls.append((path, payload))
        return httpx.Response(
            200,
            json={"ok": True, "result": {}},
            request=httpx.Request("POST", f"https://api.telegram.org/botTEST{path}"),
        )

    def calls_to(self, path: str) -> list[dict[str, object]]:
        return [payload for p, payload in self.calls if p == path]
