from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

import keepalive.config as config
from keepalive import __version__
from keepalive.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _config_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "cfg" / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    # cli.py imports CONFIG_PATH by name, so patch it there too
    import keepalive.cli as cli

    monkeypatch.setattr(cli, "CONFIG_PATH", path)
    return path


def test_run_without_command_exits_2() -> None:
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2


def test_version_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_login_writes_config_file(_config_path: Path) -> None:
    result = runner.invoke(app, ["login", "--api-key", "ka_live_abc123", "--api-url", "https://x.example"])
    assert result.exit_code == 0
    assert _config_path.exists()
    data = json.loads(_config_path.read_text())
    assert data == {"api_key": "ka_live_abc123", "api_url": "https://x.example"}
    # chmod 600
    mode = stat.S_IMODE(_config_path.stat().st_mode)
    assert mode == 0o600


def test_login_prompts_when_key_omitted(_config_path: Path) -> None:
    result = runner.invoke(app, ["login"], input="ka_live_prompted\n")
    assert result.exit_code == 0
    data = json.loads(_config_path.read_text())
    assert data["api_key"] == "ka_live_prompted"
    assert "api_url" not in data


def test_login_rejects_bad_prefix(_config_path: Path) -> None:
    result = runner.invoke(app, ["login", "--api-key", "wrong_prefix"])
    assert result.exit_code == 1
    assert not _config_path.exists()
