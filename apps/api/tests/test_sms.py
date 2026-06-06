from __future__ import annotations

import fakeredis.aioredis

from .conftest import FakeTwilio, build_client, make_settings

XML = "application/xml"


async def test_action_reply_with_active_incident_sets_reply(client_app):
    client, _app, redis = client_app
    await redis.set("active:+15551230000", "inc-7")
    resp = await client.post("/sms", data={"From": "+15551230000", "Body": "2"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(XML)
    assert "Got it" in resp.text
    assert "applying the fix" in resp.text
    stored = await redis.get("reply:inc-7")
    assert stored == b"2"


async def test_action_reply_strips_whitespace(client_app):
    client, _app, redis = client_app
    await redis.set("active:+15551230000", "inc-8")
    resp = await client.post("/sms", data={"From": "+15551230000", "Body": "  1  "})
    assert resp.status_code == 200
    assert "rolling back" in resp.text
    assert (await redis.get("reply:inc-8")) == b"1"


async def test_action_reply_no_active_incident(client_app):
    client, _app, _redis = client_app
    resp = await client.post("/sms", data={"From": "+15559999999", "Body": "3"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(XML)
    assert "No active incident" in resp.text


async def test_help_text_for_unknown_body(client_app):
    client, _app, _redis = client_app
    resp = await client.post("/sms", data={"From": "+15551230000", "Body": "9"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(XML)
    assert "Reply 1 to roll back" in resp.text


async def test_no_twilio_skips_signature_validation(client_app):
    # twilio is None in default dev settings -> no signature required, no 403
    client, _app, redis = client_app
    await redis.set("active:+1", "inc-x")
    resp = await client.post(
        "/sms",
        data={"From": "+1", "Body": "2"},
        headers={"X-Twilio-Signature": "totally-bogus"},
    )
    assert resp.status_code == 200


async def test_bad_signature_with_twilio_configured_is_403():
    # Validation runs only when app.state.twilio is not None AND uses settings.twilio_auth_token.
    settings = make_settings(
        twilio_account_sid="AC123",
        twilio_auth_token="real-token",
        twilio_from_number="+15550009999",
    )
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    async with build_client(settings, fake_redis=redis, twilio=FakeTwilio()) as (client, _app):
        resp = await client.post(
            "/sms",
            data={"From": "+1", "Body": "2"},
            headers={"X-Twilio-Signature": "bad"},
        )
    assert resp.status_code == 403


async def test_missing_signature_with_twilio_configured_is_403():
    settings = make_settings(
        twilio_account_sid="AC123",
        twilio_auth_token="real-token",
        twilio_from_number="+15550009999",
    )
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    async with build_client(settings, fake_redis=redis, twilio=FakeTwilio()) as (client, _app):
        resp = await client.post("/sms", data={"From": "+1", "Body": "2"})
    assert resp.status_code == 403
