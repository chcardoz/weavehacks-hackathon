from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "keepalive" / "config.json"

_DEFAULT_API_URL = "https://weavehacks-hackathon-dashboard.vercel.app"


def _load_config_file() -> dict[str, str]:
    try:
        raw = CONFIG_PATH.read_text()
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str | int | float)}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return raw.lower() in {"1", "true", "yes"} if raw else default


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str = ""
    api_url: str = _DEFAULT_API_URL
    heartbeat_interval_s: float = 5.0
    loss_key: str = "loss"
    demo_mode: bool = False
    weave_project: str = "keepalive"

    @classmethod
    def resolve(
        cls,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        demo_mode: bool | None = None,
        loss_key: str | None = None,
    ) -> Settings:
        """Resolve settings. Precedence: explicit kwargs > env > config file > default."""
        file_cfg = _load_config_file()

        resolved_api_key = (
            api_key if api_key is not None else os.environ.get("KEEPALIVE_API_KEY") or file_cfg.get("api_key", "")
        )
        resolved_api_url = (
            api_url
            if api_url is not None
            else os.environ.get("KEEPALIVE_API_URL") or file_cfg.get("api_url") or _DEFAULT_API_URL
        )
        resolved_demo = _env_bool("KEEPALIVE_DEMO") if demo_mode is None else demo_mode
        resolved_loss_key = loss_key if loss_key is not None else os.environ.get("KEEPALIVE_LOSS_KEY", cls.loss_key)

        return cls(
            api_key=resolved_api_key,
            api_url=resolved_api_url,
            heartbeat_interval_s=_env_float("KEEPALIVE_HEARTBEAT_INTERVAL", cls.heartbeat_interval_s),
            loss_key=resolved_loss_key,
            demo_mode=resolved_demo,
            weave_project=os.environ.get("KEEPALIVE_WEAVE_PROJECT", cls.weave_project),
        )

    @classmethod
    def from_env(cls) -> Settings:
        return cls.resolve()
