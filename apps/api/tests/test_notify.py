from __future__ import annotations

import fakeredis.aioredis

from .conftest import FakeTwilio, build_client, make_settings


async def test_notify_dev_mode_returns_sent_false(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "loss is NaN", "to_phone": "+15551230000"},
        headers=auth_header,
    )
    assert resp.status_code == 200
    assert resp.json() == {"sent": False}


async def test_notify_incident_sets_active_key(client_app, auth_header):
    client, _app, redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={
            "incident_id": "inc-42",
            "kind": "incident",
            "message": "diverging",
            "to_phone": "+15551230000",
        },
        headers=auth_header,
    )
    assert resp.status_code == 200
    val = await redis.get("active:+15551230000")
    assert val == b"inc-42"
    ttl = await redis.ttl("active:+15551230000")
    assert ttl > 0


async def test_notify_recap_does_not_set_active_key(client_app, auth_header):
    client, _app, redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={
            "incident_id": "inc-99",
            "kind": "recap",
            "message": "all good now",
            "to_phone": "+15551230000",
        },
        headers=auth_header,
    )
    assert resp.status_code == 200
    val = await redis.get("active:+15551230000")
    assert val is None


async def test_notify_with_twilio_calls_create_with_expected_kwargs(auth_header):
    settings = make_settings(
        twilio_account_sid="AC123",
        twilio_auth_token="tok",
        twilio_from_number="+15550009999",
    )
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTwilio()
    async with build_client(settings, fake_redis=redis, twilio=fake) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={
                "incident_id": "inc-1",
                "message": "loss spiked",
                "voice_note_url": "http://localhost:8000/a/abc",
                "trace_url": "http://weave/trace/xyz",
                "to_phone": "+15551112222",
            },
            headers=auth_header,
        )
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert len(fake.messages.calls) == 1
    call = fake.messages.calls[0]
    assert call["to"] == "+15551112222"
    assert call["from_"] == "+15550009999"
    body = call["body"]
    assert "loss spiked" in body
    assert "http://localhost:8000/a/abc" in body
    assert "http://weave/trace/xyz" in body


async def test_notify_body_omits_links_when_absent(auth_header):
    settings = make_settings(
        twilio_account_sid="AC123",
        twilio_auth_token="tok",
        twilio_from_number="+15550009999",
    )
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTwilio()
    async with build_client(settings, fake_redis=redis, twilio=fake) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={"incident_id": "inc-1", "message": "just text", "to_phone": "+1"},
            headers=auth_header,
        )
    assert resp.status_code == 200
    body = fake.messages.calls[0]["body"]
    assert body == "just text"
    assert "voice note" not in body
    assert "trace" not in body
