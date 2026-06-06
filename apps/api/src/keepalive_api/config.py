from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApiSettings:
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    public_base_url: str = "http://localhost:8000"
    dev_keys: frozenset[str] = frozenset()
    voice_note_ttl_s: int = 86400

    @classmethod
    def from_env(cls) -> ApiSettings:
        raw_keys = os.environ.get("KEEPALIVE_DEV_KEYS", "")
        dev_keys = frozenset(k.strip() for k in raw_keys.split(",") if k.strip())
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000"),
            dev_keys=dev_keys,
            voice_note_ttl_s=int(os.environ.get("VOICE_NOTE_TTL_S", "86400")),
        )

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)
