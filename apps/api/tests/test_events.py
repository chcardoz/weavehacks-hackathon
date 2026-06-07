from __future__ import annotations

import fakeredis.aioredis

from .conftest import FakeConnection, FakePgPool, build_client, make_settings


async def test_events_without_auth_returns_401(client_app):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/events",
        json={"events": [{"project_id": "run-1", "type": "log", "message": "hi"}]},
    )
    assert resp.status_code == 401


async def test_events_no_pg_pool_accepts_zero(client_app, auth_header):
    client, app, _redis = client_app
    assert app.state.pg_pool is None
    resp = await client.post(
        "/v1/events",
        json={"events": [{"project_id": "run-1", "type": "log", "message": "hi"}]},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 0}


async def test_events_over_cap_rejected(client_app, auth_header):
    client, _app, _redis = client_app
    events = [{"project_id": "run-1", "type": "log", "message": str(i)} for i in range(101)]
    resp = await client.post("/v1/events", json={"events": events}, headers=auth_header)
    assert resp.status_code == 422


async def test_run_started_and_incident_detected_batch(auth_header):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    conn = FakeConnection()
    pool = FakePgPool(conn)
    async with build_client(make_settings(), fake_redis=redis) as (client, app):
        app.state.pg_pool = pool
        resp = await client.post(
            "/v1/events",
            json={
                "events": [
                    {
                        "project_id": "run-a",
                        "project": {"name": "nanogpt", "wandb_run_id": "a1"},
                        "type": "run.started",
                        "message": "started",
                        "data": {"step": 0},
                    },
                    {
                        "project_id": "run-a",
                        "incident_id": "inc-1",
                        "type": "incident.detected",
                        "message": "NaN loss",
                        "data": {"kind": "nan_loss", "step": 400},
                    },
                ]
            },
            headers=auth_header,
        )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 2}

    # both event rows inserted
    event_inserts = conn.executes_matching("INSERT INTO event")
    assert len(event_inserts) == 2

    # project upsert from run.started
    assert conn.executes_matching("INSERT INTO project")
    # incident insert from incident.detected
    incident_inserts = conn.executes_matching("INSERT INTO incident")
    assert len(incident_inserts) == 1
    assert incident_inserts[0][1][0] == "inc-1"  # incident id arg
    # project status -> incident
    status_updates = conn.executes_matching("UPDATE project SET status")
    assert any(args[1] == "incident" for _sql, args in status_updates)
    # last_event_at bump for the single distinct project
    assert conn.executes_matching("UPDATE project SET last_event_at")


async def test_unknown_type_only_inserts_event(auth_header):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    conn = FakeConnection()
    pool = FakePgPool(conn)
    async with build_client(make_settings(), fake_redis=redis) as (client, app):
        app.state.pg_pool = pool
        resp = await client.post(
            "/v1/events",
            json={"events": [{"project_id": "run-z", "type": "mystery.thing", "message": "?"}]},
            headers=auth_header,
        )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": 1}
    assert len(conn.executes_matching("INSERT INTO event")) == 1
    # no project/incident/agent mutations from an unknown type (only the last_event_at bump)
    assert conn.executes_matching("INSERT INTO project") == []
    assert conn.executes_matching("INSERT INTO incident") == []
    assert conn.executes_matching("INSERT INTO agent") == []
