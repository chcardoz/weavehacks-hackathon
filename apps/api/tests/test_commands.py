from __future__ import annotations

from datetime import datetime

import fakeredis.aioredis

from .conftest import FakeConnection, FakePgPool, build_client, make_settings


class FakeRow(dict):
    """Minimal asyncpg.Record stand-in: supports row["col"] access."""


async def test_commands_no_pg_pool_returns_empty(client_app, auth_header):
    client, app, _redis = client_app
    assert app.state.pg_pool is None
    resp = await client.get("/v1/projects/run-1/commands", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json() == {"commands": []}


async def test_commands_without_auth_returns_401(client_app):
    client, _app, _redis = client_app
    resp = await client.get("/v1/projects/run-1/commands")
    assert resp.status_code == 401


async def test_commands_consumes_pending_and_iso_formats(auth_header):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    created = datetime(2026, 6, 7, 1, 54, 2)
    row = FakeRow(id="cmd-uuid", type="inject_nan", created_at=created)
    conn = FakeConnection(fetch_rules=[("UPDATE command", [row])])
    pool = FakePgPool(conn)
    async with build_client(make_settings(), fake_redis=redis) as (client, app):
        app.state.pg_pool = pool
        resp = await client.get("/v1/projects/run-a/commands", headers=auth_header)

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"commands": [{"id": "cmd-uuid", "type": "inject_nan", "created_at": "2026-06-07T01:54:02"}]}
    # the consuming UPDATE was issued with the project_id arg
    assert conn.fetch_calls
    sql, args = conn.fetch_calls[0]
    assert "UPDATE command" in sql
    assert "status = 'consumed'" in sql
    assert args[0] == "run-a"


async def test_commands_empty_when_none_pending(auth_header):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    conn = FakeConnection(fetch_rules=[("UPDATE command", [])])
    pool = FakePgPool(conn)
    async with build_client(make_settings(), fake_redis=redis) as (client, app):
        app.state.pg_pool = pool
        resp = await client.get("/v1/projects/run-a/commands", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json() == {"commands": []}
