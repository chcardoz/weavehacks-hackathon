from __future__ import annotations

import pytest

from keepalive_api.config import ApiSettings

_ENV_VARS = [
    "KEEPALIVE_DEV_KEYS",
    "DATABASE_URL",
    "REDIS_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "PUBLIC_BASE_URL",
    "VOICE_NOTE_TTL_S",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults_when_unset():
    s = ApiSettings.from_env()
    assert s.database_url == ""
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.telegram_bot_token == ""
    assert s.telegram_webhook_secret == ""
    assert s.public_base_url == "http://localhost:8000"
    assert s.dev_keys == frozenset()
    assert s.voice_note_ttl_s == 86400
    assert s.telegram_configured is False


def test_dev_keys_comma_list_and_strip(monkeypatch):
    monkeypatch.setenv("KEEPALIVE_DEV_KEYS", " ka_live_a , ka_live_b ,,  ka_live_c ")
    s = ApiSettings.from_env()
    assert s.dev_keys == frozenset({"ka_live_a", "ka_live_b", "ka_live_c"})


def test_dev_keys_single(monkeypatch):
    monkeypatch.setenv("KEEPALIVE_DEV_KEYS", "ka_live_only")
    s = ApiSettings.from_env()
    assert s.dev_keys == frozenset({"ka_live_only"})


def test_dev_keys_empty_string_yields_empty_set(monkeypatch):
    monkeypatch.setenv("KEEPALIVE_DEV_KEYS", "   ")
    s = ApiSettings.from_env()
    assert s.dev_keys == frozenset()


def test_env_overrides_applied(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("REDIS_URL", "redis://r:6380/2")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.keepalive.club")
    monkeypatch.setenv("VOICE_NOTE_TTL_S", "60")
    s = ApiSettings.from_env()
    assert s.database_url == "postgres://x"
    assert s.redis_url == "redis://r:6380/2"
    assert s.public_base_url == "https://api.keepalive.club"
    assert s.voice_note_ttl_s == 60


def test_telegram_configured_requires_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    assert ApiSettings.from_env().telegram_configured is False  # secret alone is not enough

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "110201543:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    s = ApiSettings.from_env()
    assert s.telegram_configured is True
    assert s.telegram_webhook_secret == "s3cret"
