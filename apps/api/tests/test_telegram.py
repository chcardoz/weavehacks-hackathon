from __future__ import annotations

import fakeredis.aioredis

from .conftest import FakeTelegram, build_client, make_settings


def callback_update(data: str, chat_id: int = 123456789) -> dict[str, object]:
    return {
        "update_id": 100,
        "callback_query": {
            "id": "cb-1",
            "from": {"id": chat_id, "is_bot": False, "first_name": "Chris"},
            "message": {"message_id": 12, "chat": {"id": chat_id, "type": "private"}, "text": "incident"},
            "chat_instance": "-1",
            "data": data,
        },
    }


def message_update(text: str, chat_id: int = 123456789) -> dict[str, object]:
    return {
        "update_id": 101,
        "message": {
            "message_id": 13,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False, "first_name": "Chris"},
            "text": text,
        },
    }


async def test_button_tap_sets_reply_and_answers_callback():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(make_settings(), fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post("/telegram", json=callback_update("inc-7:2"))
    assert resp.status_code == 200
    assert (await redis.get("reply:inc-7")) == b"2"
    answers = fake.calls_to("/answerCallbackQuery")
    assert len(answers) == 1
    assert answers[0]["callback_query_id"] == "cb-1"
    assert "applying the fix" in str(answers[0]["text"])


async def test_button_tap_works_for_incident_ids_containing_colons():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(make_settings(), fake_redis=redis, telegram=fake) as (client, _app):
        await client.post("/telegram", json=callback_update("inc:weird:id:1"))
    assert (await redis.get("reply:inc:weird:id")) == b"1"


async def test_unknown_callback_data_answers_help_and_sets_nothing():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(make_settings(), fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post("/telegram", json=callback_update("garbage"))
    assert resp.status_code == 200
    assert await redis.keys("reply:*") == []
    answers = fake.calls_to("/answerCallbackQuery")
    assert len(answers) == 1


async def test_typed_reply_with_active_incident_sets_reply(client_app):
    client, _app, redis = client_app
    await redis.set("active:123456789", "inc-7")
    resp = await client.post("/telegram", json=message_update("2"))
    assert resp.status_code == 200
    assert (await redis.get("reply:inc-7")) == b"2"


async def test_typed_reply_strips_whitespace(client_app):
    client, _app, redis = client_app
    await redis.set("active:123456789", "inc-8")
    resp = await client.post("/telegram", json=message_update("  1  "))
    assert resp.status_code == 200
    assert (await redis.get("reply:inc-8")) == b"1"


async def test_typed_reply_no_active_incident_sends_notice():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(make_settings(), fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post("/telegram", json=message_update("3", chat_id=555))
    assert resp.status_code == 200
    sends = fake.calls_to("/sendMessage")
    assert len(sends) == 1
    assert "No active incident" in str(sends[0]["text"])


async def test_start_command_replies_with_chat_id():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    fake = FakeTelegram()
    async with build_client(make_settings(), fake_redis=redis, telegram=fake) as (client, _app):
        resp = await client.post("/telegram", json=message_update("/start", chat_id=987654))
    assert resp.status_code == 200
    sends = fake.calls_to("/sendMessage")
    assert len(sends) == 1
    assert "KEEPALIVE_TELEGRAM_CHAT_ID=987654" in str(sends[0]["text"])


async def test_unknown_text_sends_help(client_app):
    # dev mode (telegram None): handler logs instead of sending; still 200
    client, _app, _redis = client_app
    resp = await client.post("/telegram", json=message_update("9"))
    assert resp.status_code == 200


async def test_secret_token_required_when_configured():
    settings = make_settings(telegram_webhook_secret="s3cret")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    async with build_client(settings, fake_redis=redis, telegram=FakeTelegram()) as (client, _app):
        missing = await client.post("/telegram", json=message_update("2"))
        bad = await client.post(
            "/telegram",
            json=message_update("2"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )
        good = await client.post(
            "/telegram",
            json=message_update("2"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
        )
    assert missing.status_code == 403
    assert bad.status_code == 403
    assert good.status_code == 200


async def test_no_secret_configured_skips_validation(client_app):
    client, _app, redis = client_app
    await redis.set("active:123456789", "inc-x")
    resp = await client.post(
        "/telegram",
        json=message_update("2"),
        headers={"X-Telegram-Bot-Api-Secret-Token": "totally-bogus"},
    )
    assert resp.status_code == 200


async def test_empty_update_is_ok(client_app):
    client, _app, _redis = client_app
    resp = await client.post("/telegram", json={"update_id": 1})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
