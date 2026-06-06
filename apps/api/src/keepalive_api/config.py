from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApiSettings:
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    public_base_url: str = "http://localhost:8000"
    dev_keys: frozenset[str] = frozenset()
    voice_note_ttl_s: int = 86400

    @classmethod
    def from_env(cls) -> "ApiSettings":
        raw_keys = os.environ.get("KEEPALIVE_DEV_KEYS", "")
        dev_keys = frozenset(k.strip() for k in raw_keys.split(",") if k.strip())
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            twilio_account_sid=os.environ.get("TWILIO_ACCOUNT_SID", ""),
            twilio_auth_token=os.environ.get("TWILIO_AUTH_TOKEN", ""),
            twilio_from_number=os.environ.get("TWILIO_FROM_NUMBER", ""),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000"),
            dev_keys=dev_keys,
            voice_note_ttl_s=int(os.environ.get("VOICE_NOTE_TTL_S", "86400")),
        )

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number)
