from __future__ import annotations

import fakeredis.aioredis

from .conftest import FakeTelegram, build_client, make_settings


async def test_notify_dev_mode_returns_sent_false(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "loss is NaN", "chat_id": "123456789"},
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
            "chat_id": "123456789",
        },
        headers=auth_header,
    )
    assert resp.status_code == 200
    val = await redis.get("active:123456789")
    assert val == b"inc-42"
    ttl = await redis.ttl("active:123456789")
    assert ttl > 0


async def test_notify_recap_does_not_set_active_key(client_app, auth_header):
    client, _app, redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={
            "incident_id": "inc-99",
            "kind": "recap",
            "message": "all good now",
            "chat_id": "123456789",
        },
        headers=auth_header,
    )
    assert resp.status_code == 200
    val = await redis.get("active:123456789")
    assert val is None


async def test_notify_incident_sends_message_with_action_buttons(auth_header):
    settings = make_settings(telegram_bot_token="123:abc")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(settings, fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={
                "incident_id": "inc-1",
                "message": "loss spiked",
                "trace_url": "http://weave/trace/xyz",
                "chat_id": "123456789",
            },
            headers=auth_header,
        )
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}

    sends = fake.calls_to("/sendMessage")
    assert len(sends) == 1
    payload = sends[0]
    assert payload["chat_id"] == "123456789"
    assert payload["text"] == "loss spiked"
    rows = payload["reply_markup"]["inline_keyboard"]
    actions = rows[0]
    assert [b["callback_data"] for b in actions] == ["inc-1:1", "inc-1:2", "inc-1:3"]
    assert rows[1][0]["url"] == "http://weave/trace/xyz"


async def test_notify_with_voice_note_sends_voice(auth_header):
    settings = make_settings(telegram_bot_token="123:abc")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(settings, fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={
                "incident_id": "inc-1",
                "message": "loss spiked",
                "voice_note_url": "https://api.keepalive.club/a/abc.mp3",
                "chat_id": "123456789",
            },
            headers=auth_header,
        )
    assert resp.status_code == 200
    voices = fake.calls_to("/sendVoice")
    assert len(voices) == 1
    assert voices[0] == {"chat_id": "123456789", "voice": "https://api.keepalive.club/a/abc.mp3"}


async def test_notify_recap_has_no_action_buttons(auth_header):
    settings = make_settings(telegram_bot_token="123:abc")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(settings, fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={
                "incident_id": "inc-1",
                "kind": "recap",
                "message": "winner promoted",
                "trace_url": "http://weave/trace/xyz",
                "chat_id": "123456789",
            },
            headers=auth_header,
        )
    assert resp.status_code == 200
    payload = fake.calls_to("/sendMessage")[0]
    rows = payload["reply_markup"]["inline_keyboard"]
    assert len(rows) == 1  # just the trace link, no 1/2/3 buttons
    assert rows[0][0]["url"] == "http://weave/trace/xyz"


async def test_notify_plain_recap_omits_keyboard_and_voice(auth_header):
    settings = make_settings(telegram_bot_token="123:abc")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(settings, fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={"incident_id": "inc-1", "kind": "recap", "message": "just text", "chat_id": "1"},
            headers=auth_header,
        )
    assert resp.status_code == 200
    payload = fake.calls_to("/sendMessage")[0]
    assert payload["text"] == "just text"
    assert "reply_markup" not in payload
    assert fake.calls_to("/sendVoice") == []
