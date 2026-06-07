from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    return raw.lower() in {"1", "true", "yes"} if raw else default


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str = ""
    api_url: str = "https://api.keepalive.club"
    telegram_chat_id: str = ""
    openai_api_key: str = ""
    diagnosis_model: str = "gpt-5.4"
    use_wandb_inference: bool = False
    wandb_inference_base_url: str = "https://api.inference.wandb.ai/v1"
    wandb_inference_model: str = "openai/gpt-oss-120b"
    wandb_api_key: str = ""
    cursor_api_key: str = ""
    cursor_api_url: str = "https://api.cursor.com"
    redis_url: str = ""
    agent_memory_url: str = ""
    escalation_timeout_s: float = 120.0
    reply_poll_interval_s: float = 2.0
    probe_steps: int = 300
    max_probes: int = 3
    probe_branch_timeout_s: float = 600.0
    probe_run_timeout_s: float = 900.0
    metrics_poll_interval_s: float = 10.0
    metrics_poll_timeout_s: float = 120.0
    weave_project: str = "keepalive"
    loss_key: str = "loss"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            api_key=_env("KEEPALIVE_API_KEY"),
            api_url=_env("KEEPALIVE_API_URL", cls.api_url),
            telegram_chat_id=_env("KEEPALIVE_TELEGRAM_CHAT_ID"),
            openai_api_key=_env("OPENAI_API_KEY"),
            diagnosis_model=_env("KEEPALIVE_DIAGNOSIS_MODEL", cls.diagnosis_model),
            use_wandb_inference=_env_bool("KEEPALIVE_USE_WANDB_INFERENCE"),
            wandb_inference_base_url=_env("KEEPALIVE_WANDB_INFERENCE_URL", cls.wandb_inference_base_url),
            wandb_inference_model=_env("KEEPALIVE_WANDB_INFERENCE_MODEL", cls.wandb_inference_model),
            wandb_api_key=_env("WANDB_API_KEY"),
            cursor_api_key=_env("CURSOR_API_KEY"),
            cursor_api_url=_env("CURSOR_API_URL", cls.cursor_api_url),
            redis_url=_env("REDIS_URL"),
            agent_memory_url=_env("AGENT_MEMORY_URL"),
            escalation_timeout_s=_env_float("KEEPALIVE_TIMEOUT", cls.escalation_timeout_s),
            reply_poll_interval_s=_env_float("KEEPALIVE_REPLY_POLL_INTERVAL", cls.reply_poll_interval_s),
            probe_steps=_env_int("KEEPALIVE_PROBE_STEPS", cls.probe_steps),
            max_probes=_env_int("KEEPALIVE_MAX_PROBES", cls.max_probes),
            probe_branch_timeout_s=_env_float("KEEPALIVE_PROBE_BRANCH_TIMEOUT", cls.probe_branch_timeout_s),
            probe_run_timeout_s=_env_float("KEEPALIVE_PROBE_RUN_TIMEOUT", cls.probe_run_timeout_s),
            metrics_poll_interval_s=_env_float("KEEPALIVE_METRICS_POLL_INTERVAL", cls.metrics_poll_interval_s),
            metrics_poll_timeout_s=_env_float("KEEPALIVE_METRICS_POLL_TIMEOUT", cls.metrics_poll_timeout_s),
            weave_project=_env("KEEPALIVE_WEAVE_PROJECT", cls.weave_project),
            loss_key=_env("KEEPALIVE_LOSS_KEY", cls.loss_key),
        )
