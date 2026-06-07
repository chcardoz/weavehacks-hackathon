from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from typing import Any

from .config import Settings
from .types import (
    FailureEvent,
    FailureKind,
    KeepaliveError,
    RunContext,
    new_id,
)

_log = logging.getLogger("keepalive")


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _normalize_repo_url(url: str) -> str:
    if url.startswith("git@"):
        host, _, path = url.partition(":")
        host = host.removeprefix("git@")
        path = path.removesuffix(".git")
        return f"https://{host}/{path}"
    return url.removesuffix(".git")


def _parse_owner_repo(url: str) -> tuple[str, str]:
    """Parse owner/name from an origin remote (ssh or https form)."""
    if not url:
        return "", ""
    cleaned = url
    if cleaned.startswith("git@"):
        # git@github.com:owner/name(.git)
        _, _, path = cleaned.partition(":")
    else:
        # https://github.com/owner/name(.git) or http://...
        cleaned = cleaned.removeprefix("https://").removeprefix("http://")
        _, _, path = cleaned.partition("/")
    path = path.removesuffix(".git").strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "", ""


def _capture_run_context(
    run: Any,
    checkpoint_dir: str,
    loss_key: str,
    entrypoint: list[str] | None,
) -> RunContext:
    run_id = str(getattr(run, "id", None) or os.environ.get("WANDB_RUN_ID", "") or new_id("run"))
    entity = str(getattr(run, "entity", None) or os.environ.get("WANDB_ENTITY", ""))
    project = str(getattr(run, "project", None) or os.environ.get("WANDB_PROJECT", ""))

    run_url = ""
    if run is not None:
        getter = getattr(run, "get_url", None)
        if callable(getter):
            try:
                run_url = str(getter() or "")
            except Exception:
                run_url = ""
        if not run_url:
            run_url = str(getattr(run, "url", "") or "")

    commit_sha = _git("rev-parse", "HEAD")
    origin = _git("remote", "get-url", "origin")
    repo_url = _normalize_repo_url(origin)
    repo_owner, repo_name = _parse_owner_repo(origin)
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    entry = entrypoint if entrypoint else [sys.executable, *sys.argv]

    return RunContext(
        run_id=run_id,
        project=project,
        entity=entity,
        run_url=run_url,
        commit_sha=commit_sha,
        repo_url=repo_url,
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch=branch,
        entrypoint=list(entry),
        checkpoint_dir=checkpoint_dir,
        loss_key=loss_key,
    )


def _safely(fn: Callable[[], Any], what: str = "") -> Any:
    try:
        return fn()
    except Exception as exc:
        _log.warning("keepalive: best-effort step failed (%s): %r", what or fn, exc)
        return None


class Watchdog:
    """Thin client: detect hard failures, report metrics/events, poll demo commands.

    No local diagnosis, escalation, or probe racing — those live server-side. On a
    detected failure we emit ``incident.detected`` and KEEP GOING; the server fixes
    via PRs.
    """

    def __init__(
        self,
        run: Any = None,
        settings: Settings | None = None,
        *,
        prompt: str | None = None,
        threshold: float = 0.6,
        max_agents: int = 3,
        checkpoint_dir: str | None = None,
        demo_mode: bool | None = None,
        loss_key: str | None = None,
        entrypoint: list[str] | None = None,
        reporter: Any = None,
        optimizer: Any = None,
    ) -> None:
        self._run = run
        self.settings = settings or Settings.from_env()
        self._prompt = prompt
        self._threshold = threshold
        self._max_agents = max_agents
        self._checkpoint_dir = checkpoint_dir
        self._loss_key = loss_key or self.settings.loss_key
        self._demo_mode = self.settings.demo_mode if demo_mode is None else demo_mode
        self._optimizer = optimizer

        self._ctx = _capture_run_context(run, checkpoint_dir or "", self._loss_key, entrypoint)

        self._reporter = reporter
        self._suite: Any = None
        self._injector: Any = None
        self._command_poller: Any = None
        self._hook: Any = None
        self._handling = False
        self._started = False
        self._stopped = False
        self._last_step = -1

    @property
    def ctx(self) -> RunContext:
        return self._ctx

    @property
    def suite(self) -> Any:
        if self._suite is None:
            from .detect.rules import DetectorSuite

            self._suite = DetectorSuite(loss_key=self._loss_key)
        return self._suite

    @property
    def reporter(self) -> Any:
        if self._reporter is None:
            from .reporter import NullReporter, build_reporter

            self._reporter = _safely(
                lambda: build_reporter(self.settings, self._run, self._project_meta()),
                "build_reporter",
            )
            if self._reporter is None:
                self._reporter = NullReporter()
        return self._reporter

    def _project_meta(self) -> dict[str, Any]:
        ctx = self._ctx
        meta: dict[str, Any] = {
            "name": str(getattr(self._run, "name", "") or ctx.project or ""),
            "repo_owner": ctx.repo_owner,
            "repo_name": ctx.repo_name,
            "branch": ctx.branch,
            "commit_sha": ctx.commit_sha,
            "wandb_run_id": ctx.run_id,
            "wandb_url": ctx.run_url,
            "demo_mode": self._demo_mode,
            "threshold": self._threshold,
            "max_agents": self._max_agents,
        }
        if self._prompt is not None:
            meta["monitoring_prompt"] = self._prompt
        return meta

    # -- demo --------------------------------------------------------------

    def _lr_scale_fn(self, factor: float) -> None:
        opt = self._optimizer
        if opt is None:
            return
        groups = getattr(opt, "param_groups", None)
        if not groups:
            return
        for group in groups:
            if "lr" in group:
                group["lr"] = group["lr"] * factor

    def _arm_demo(self) -> None:
        if not self._demo_mode:
            return
        from .demo import FaultInjector

        self._injector = FaultInjector(
            loss_key=self._loss_key,
            stall_seconds=self.settings.heartbeat_interval_s * 4.0,
            lr_scale_fn=self._lr_scale_fn if self._optimizer is not None else None,
        )

    def _maybe_start_poller(self) -> None:
        if not self._demo_mode or self._injector is None:
            return
        if self._command_poller is not None:
            return
        server_project_id = getattr(self.reporter, "server_project_id", None)
        if not server_project_id:
            return
        from .demo import CommandPoller

        self._command_poller = _safely(
            lambda: CommandPoller(self.settings, server_project_id, self._injector, self.reporter),
            "command_poller",
        )
        if self._command_poller is not None:
            _safely(self._command_poller.start, "command_poller_start")

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        from .tracing import init_tracing

        _safely(lambda: init_tracing(self.settings.weave_project), "init_tracing")
        self._arm_demo()
        if self._run is not None:
            from .detect.monitor import MetricHook

            self._hook = MetricHook(
                self.suite,
                on_failure=self.handle_failure,
                on_metrics=self._on_metrics,
                injector=self._injector,
            )
            _safely(lambda: self._hook.install(self._run), "install_hook")
        _safely(
            lambda: self.reporter.emit("run.started", "watchdog started", include_project=True),
            "emit_started",
        )
        self._maybe_start_poller()
        self._started = True

    def _on_metrics(self, step: int, metrics: dict[str, float]) -> None:
        if step >= 0:
            self._last_step = step
        loss = metrics.get(self._loss_key)
        _safely(lambda: self.reporter.heartbeat(step, loss, metrics), "heartbeat")
        # The poller can only start once the server has returned its project id.
        self._maybe_start_poller()

    def stop(self) -> None:
        if self._stopped:
            return
        if self._hook is not None:
            _safely(self._hook.uninstall, "uninstall_hook")
            self._hook = None
        if self._command_poller is not None:
            _safely(self._command_poller.close, "command_poller_close")
            self._command_poller = None
        if self._started:
            _safely(
                lambda: self.reporter.emit("run.stopped", "watchdog stopped", data={"reason": "completed"}),
                "emit_stopped",
            )
        if self._reporter is not None:
            _safely(self._reporter.close, "reporter_close")
            self._reporter = None
        self._stopped = True
        self._started = False

    def __enter__(self) -> Watchdog:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        try:
            if exc is not None and isinstance(exc, Exception) and not isinstance(exc, KeepaliveError):
                event = FailureEvent(
                    kind=FailureKind.EXCEPTION,
                    step=self._last_step,
                    message=repr(exc),
                )
                self.handle_failure(event)
            return False
        finally:
            self.stop()

    def heartbeat(self) -> None:
        event = _safely(lambda: self.suite.idle_check(), "idle_check")
        if event is not None:
            self.handle_failure(event)

    def handle_failure(self, event: FailureEvent) -> None:
        from .tracing import traced

        return traced(self._handle_failure)(event)

    def _handle_failure(self, event: FailureEvent) -> None:
        from .tracing import attributes

        if event.step >= 0:
            self._last_step = event.step

        incident_id = new_id("inc")
        metrics_tail = [s.metrics for s in self.suite.history[-5:]]
        data: dict[str, Any] = {
            "kind": str(event.kind),
            "step": event.step,
            "message": event.message,
            "metrics_tail": metrics_tail,
        }
        attrs = {
            "incident_id": incident_id,
            "run_id": self._ctx.run_id,
            "failure_kind": str(event.kind),
        }
        with attributes(attrs):
            _safely(
                lambda: self.reporter.emit(
                    "incident.detected",
                    event.message,
                    incident_id=incident_id,
                    level="error",
                    data=data,
                    include_project=True,
                ),
                "emit_incident",
            )
        # Keep going: the server fixes via PRs. No local pause/race/escalation.


@contextlib.contextmanager
def watchdog(
    run: Any = None,
    *,
    prompt: str | None = None,
    threshold: float = 0.6,
    max_agents: int = 3,
    checkpoint_dir: str | None = None,
    demo_mode: bool | None = None,
    loss_key: str | None = None,
    settings: Settings | None = None,
    optimizer: Any = None,
    reporter: Any = None,
) -> Iterator[Watchdog]:
    wd = Watchdog(
        run,
        settings=settings,
        prompt=prompt,
        threshold=threshold,
        max_agents=max_agents,
        checkpoint_dir=checkpoint_dir,
        demo_mode=demo_mode,
        loss_key=loss_key,
        optimizer=optimizer,
        reporter=reporter,
    )
    with wd:
        yield wd
