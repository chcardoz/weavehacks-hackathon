from __future__ import annotations

import dataclasses
import queue
import subprocess
import sys
import threading
from typing import Any

import typer

from .config import Settings
from .types import (
    FailureEvent,
    FailureKind,
    KeepaliveHandedOff,
    KeepaliveRollback,
    KeepaliveStop,
)
from .watchdog import Watchdog

app = typer.Typer(add_completion=False, help="keepalive — a watchdog for GPU training runs.")


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


def _dispatch(wd: Watchdog, event: FailureEvent) -> int:
    try:
        wd.handle_failure(event)
    except KeepaliveHandedOff as handed:
        print(f"keepalive: training handed off to probe {handed.winner.spec.id} ({handed.winner.spec.branch})")
        return 0
    except KeepaliveRollback as rb:
        print(f"keepalive: rolled back to {rb.checkpoint}")
        return 0
    except KeepaliveStop:
        print("keepalive: run stopped.")
        return 1
    return 0


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run(
    ctx: typer.Context,
    run_path: str | None = typer.Option(None, "--run-path", help="entity/project/run_id for history polling"),
    timeout: float | None = typer.Option(None, "--timeout", help="escalation timeout in seconds"),
    checkpoint_dir: str = typer.Option("checkpoints", "--checkpoint-dir"),
    loss_key: str | None = typer.Option(None, "--loss-key"),
) -> None:
    cmd = list(ctx.args)
    if not cmd:
        typer.echo("usage: keepalive run -- python train.py ...", err=True)
        raise typer.Exit(code=2)

    settings = Settings.from_env()
    if timeout is not None:
        settings = dataclasses.replace(settings, escalation_timeout_s=timeout)

    wd = Watchdog(
        run=None,
        settings=settings,
        entrypoint=cmd,
        checkpoint_dir=checkpoint_dir,
        timeout=timeout,
        loss_key=loss_key,
    )
    wd.start()

    poller = None
    if run_path:
        try:
            from .detect.monitor import HistoryPoller

            poller = HistoryPoller(run_path, loss_key=loss_key or settings.loss_key)
        except Exception:
            poller = None

    events: queue.Queue[FailureEvent] = queue.Queue()
    child = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, bufsize=1)
    tailer = threading.Thread(target=_tail_stderr, args=(child.stderr, events, wd.suite), daemon=True)
    tailer.start()

    exit_code = 0
    try:
        while child.poll() is None:
            if poller is not None:
                try:
                    for snap in poller.poll():
                        ev = wd.suite.observe(snap)
                        if ev is not None:
                            events.put(ev)
                except Exception:
                    pass
            idle = None
            try:
                idle = wd.suite.idle_check()
            except Exception:
                idle = None
            if idle is not None:
                events.put(idle)

            try:
                event = events.get(timeout=1.0)
            except queue.Empty:
                continue

            child.terminate()
            exit_code = _dispatch(wd, event)
            break
        else:
            code = child.returncode if child.returncode is not None else 0
            try:
                event = events.get_nowait()
            except queue.Empty:
                event = None
            if event is not None:
                exit_code = _dispatch(wd, event)
            elif code != 0:
                synthetic = FailureEvent(
                    kind=FailureKind.EXCEPTION,
                    step=-1,
                    message=f"process exited {code}",
                )
                exit_code = _dispatch(wd, synthetic)
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
