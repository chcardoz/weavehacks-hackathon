from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from typing import Any

import typer

from .config import CONFIG_PATH, Settings
from .types import FailureEvent, FailureKind
from .watchdog import Watchdog

app = typer.Typer(add_completion=False, help="keepalive — a watchdog for GPU training runs.")


@app.command()
def login(
    api_key: str | None = typer.Option(None, "--api-key", help="ka_live_ API key (prompted if omitted)"),
    api_url: str | None = typer.Option(None, "--api-url", help="override the API base URL"),
) -> None:
    """Store the keepalive API key in ~/.config/keepalive/config.json (chmod 600)."""
    raw_key = api_key if api_key is not None else typer.prompt("keepalive API key", hide_input=True)
    key = str(raw_key).strip()

    if not key.startswith("ka_live_"):
        typer.echo("error: API key must start with 'ka_live_'", err=True)
        raise typer.Exit(code=1)

    config: dict[str, str] = {"api_key": key}
    if api_url:
        config["api_url"] = api_url.strip()

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    os.chmod(CONFIG_PATH, 0o600)
    typer.echo(f"saved credentials to {CONFIG_PATH}")


def _tail_stderr(stream: Any, events: queue.Queue[FailureEvent], suite: Any) -> None:
    for raw in iter(stream.readline, ""):
        line = raw.rstrip("\n")
        print(line, file=sys.stderr)
        try:
            event = suite.scan_logline(line)
        except Exception:
            event = None
        if event is not None:
            events.put(event)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run(
    ctx: typer.Context,
    checkpoint_dir: str | None = typer.Option(None, "--checkpoint-dir"),
    loss_key: str | None = typer.Option(None, "--loss-key"),
    demo: bool = typer.Option(False, "--demo", help="arm demo fault injection"),
) -> None:
    """Supervise an unmodified training script: tail stderr, report failures."""
    cmd = list(ctx.args)
    if not cmd:
        typer.echo("usage: keepalive run -- python train.py ...", err=True)
        raise typer.Exit(code=2)

    settings = Settings.resolve()

    wd = Watchdog(
        run=None,
        settings=settings,
        entrypoint=cmd,
        checkpoint_dir=checkpoint_dir,
        loss_key=loss_key,
        demo_mode=demo or None,
    )
    wd.start()

    events: queue.Queue[FailureEvent] = queue.Queue()
    child = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, bufsize=1)
    tailer = threading.Thread(target=_tail_stderr, args=(child.stderr, events, wd.suite), daemon=True)
    tailer.start()

    exit_code = 0
    try:
        return_code = child.wait()
        # drain any failure scanned from stderr
        try:
            event = events.get_nowait()
        except queue.Empty:
            event = None
        if event is not None:
            wd.handle_failure(event)
            exit_code = return_code or 1
        elif return_code != 0:
            wd.handle_failure(
                FailureEvent(
                    kind=FailureKind.EXCEPTION,
                    step=-1,
                    message=f"process exited {return_code}",
                )
            )
            exit_code = return_code
        else:
            exit_code = 0
    finally:
        wd.stop()
        if child.poll() is None:
            child.terminate()

    raise typer.Exit(code=exit_code)


@app.command()
def version() -> None:
    from . import __version__

    typer.echo(__version__)


if __name__ == "__main__":
    app()
