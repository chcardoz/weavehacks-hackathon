from __future__ import annotations

import fakeredis.aioredis
import httpx

from .conftest import FakeOpenAI, FakeTelegram, build_client, make_settings

MP3 = b"ID3fake-mp3-bytes"


def _tts_response(status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        content=MP3 if status == 200 else b"{}",
        headers={"content-type": "audio/mpeg" if status == 200 else "application/json"},
        request=httpx.Request("POST", "https://api.openai.com/v1/audio/speech"),
    )


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


async def test_notify_with_voice_script_synthesizes_and_sends_voice(auth_header):
    settings = make_settings(telegram_bot_token="123:abc", voice_note_ttl_s=1234)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    telegram = FakeTelegram()
    openai = FakeOpenAI(responses={"/audio/speech": _tts_response()})
    async with build_client(settings, fake_redis=redis, telegram=telegram, openai=openai) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={
                "incident_id": "inc-1",
                "message": "loss spiked",
                "voice_script": "Your run hit a NaN at step 400.",
                "chat_id": "123456789",
            },
            headers=auth_header,
        )
    assert resp.status_code == 200

    tts_calls = openai.calls_to("/audio/speech")
    assert len(tts_calls) == 1
    assert tts_calls[0]["input"] == "Your run hit a NaN at step 400."
    assert tts_calls[0]["model"] == "gpt-4o-mini-tts"

    voices = telegram.calls_to("/sendVoice")
    assert len(voices) == 1
    voice_url = voices[0]["voice"]
    assert voice_url.startswith("http://localhost:8000/a/")

    note_id = voice_url.rsplit("/a/", 1)[1]
    assert await redis.get(f"audio:{note_id}") == MP3
    ttl = await redis.ttl(f"audio:{note_id}")
    assert 0 < ttl <= 1234


async def test_notify_tts_failure_still_sends_message(auth_header):
    settings = make_settings(telegram_bot_token="123:abc")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    telegram = FakeTelegram()
    openai = FakeOpenAI(responses={"/audio/speech": _tts_response(500)})
    async with build_client(settings, fake_redis=redis, telegram=telegram, openai=openai) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={
                "incident_id": "inc-1",
                "message": "loss spiked",
                "voice_script": "speak this",
                "chat_id": "123456789",
            },
            headers=auth_header,
        )
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert len(telegram.calls_to("/sendMessage")) == 1
    assert telegram.calls_to("/sendVoice") == []


async def test_notify_voice_script_without_openai_skips_voice(auth_header):
    settings = make_settings(telegram_bot_token="123:abc")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    telegram = FakeTelegram()
    async with build_client(settings, fake_redis=redis, telegram=telegram) as (client, _app):
        resp = await client.post(
            "/v1/notify",
            json={
                "incident_id": "inc-1",
                "message": "loss spiked",
                "voice_script": "speak this",
                "chat_id": "123456789",
            },
            headers=auth_header,
        )
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert len(telegram.calls_to("/sendMessage")) == 1
    assert telegram.calls_to("/sendVoice") == []


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
