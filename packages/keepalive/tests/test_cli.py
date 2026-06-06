from __future__ import annotations

from typer.testing import CliRunner

from keepalive import __version__
from keepalive.cli import app

runner = CliRunner()


def test_run_without_command_exits_2() -> None:
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 2


def test_version_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
