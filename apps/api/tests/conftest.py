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
    """Dev settings: dev key, no twilio creds, no database, fakeable redis url."""
    base: dict[str, object] = {
        "dev_keys": frozenset({DEV_KEY}),
        "database_url": "",
        "twilio_account_sid": "",
        "twilio_auth_token": "",
        "twilio_from_number": "",
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
    twilio: object | None = None,
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
        app.state.redis = redis
        if twilio is not None:
            app.state.twilio = twilio
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            try:
                yield client, app
            finally:
                # restore so lifespan shutdown closes the original object it created
                app.state.redis = real_redis


@pytest.fixture
def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {DEV_KEY}"}


@pytest.fixture
def fake_redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=False)


@pytest.fixture
async def client_app(fake_redis: fakeredis.aioredis.FakeRedis):
    """Default client with dev settings (twilio None) and a shared fake redis.

    Yields (client, app, redis).
    """
    async with build_client(make_settings(), fake_redis=fake_redis) as (client, app):
        yield client, app, fake_redis


class FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return type("Msg", (), {"sid": "SM_fake"})()


class FakeTwilio:
    def __init__(self) -> None:
        self.messages = FakeMessages()
