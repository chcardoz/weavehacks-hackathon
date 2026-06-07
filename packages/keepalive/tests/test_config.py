from __future__ import annotations

import json
from pathlib import Path

import pytest

import keepalive.config as config
from keepalive.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in (
        "KEEPALIVE_API_KEY",
        "KEEPALIVE_API_URL",
        "KEEPALIVE_DEMO",
        "KEEPALIVE_LOSS_KEY",
        "KEEPALIVE_HEARTBEAT_INTERVAL",
        "KEEPALIVE_WEAVE_PROJECT",
    ):
        monkeypatch.delenv(var, raising=False)
    # point the config-file path at an empty temp location by default
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")


def _write_config(data: dict[str, str]) -> None:
    config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_PATH.write_text(json.dumps(data))


def test_default_api_url() -> None:
    s = Settings.resolve()
    assert s.api_url == "https://keepalive.club"
    assert s.api_key == ""


def test_config_file_used_when_env_absent() -> None:
    _write_config({"api_key": "ka_live_file", "api_url": "https://file.example"})
    s = Settings.resolve()
    assert s.api_key == "ka_live_file"
    assert s.api_url == "https://file.example"


def test_env_beats_config_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config({"api_key": "ka_live_file", "api_url": "https://file.example"})
    monkeypatch.setenv("KEEPALIVE_API_KEY", "ka_live_env")
    s = Settings.resolve()
    assert s.api_key == "ka_live_env"
    # api_url not in env -> still from file
    assert s.api_url == "https://file.example"


def test_explicit_kwargs_beat_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config({"api_key": "ka_live_file"})
    monkeypatch.setenv("KEEPALIVE_API_KEY", "ka_live_env")
    s = Settings.resolve(api_key="ka_live_explicit", api_url="https://explicit.example")
    assert s.api_key == "ka_live_explicit"
    assert s.api_url == "https://explicit.example"


def test_demo_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KEEPALIVE_DEMO", "1")
    assert Settings.resolve().demo_mode is True


def test_malformed_config_file_ignored() -> None:
    config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_PATH.write_text("not json{")
    s = Settings.resolve()
    assert s.api_key == ""
    assert s.api_url == "https://keepalive.club"
