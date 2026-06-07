from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from typing import Any

from .config import Settings
from .types import (
    Diagnosis,
    FailureEvent,
    FailureKind,
    HumanReply,
    Incident,
    IncidentStatus,
    KeepaliveError,
    KeepaliveHandedOff,
    KeepaliveRollback,
    KeepaliveStop,
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


def _newest_file(directory: str) -> str | None:
    if not directory or not os.path.isdir(directory):
        return None
    newest: str | None = None
    newest_mtime = -1.0
    for entry in os.scandir(directory):
        if not entry.is_file():
            continue
        mtime = entry.stat().st_mtime
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest = entry.path
    return newest


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
    repo_url = _normalize_repo_url(_git("remote", "get-url", "origin"))
    entry = entrypoint if entrypoint else [sys.executable, *sys.argv]
    last_checkpoint = _newest_file(checkpoint_dir)

    return RunContext(
        run_id=run_id,
        project=project,
        entity=entity,
        run_url=run_url,
        commit_sha=commit_sha,
        repo_url=repo_url,
        entrypoint=list(entry),
        checkpoint_dir=checkpoint_dir,
        last_checkpoint=last_checkpoint,
        loss_key=loss_key,
    )


class _LocalDeadlines:
    def __init__(self) -> None:
        self._armed: dict[str, float] = {}

    def arm(self, incident_id: str, timeout_s: float) -> float:
        due = time.time() + timeout_s
        self._armed[incident_id] = due
        return due

    def due(self, now: float | None = None) -> list[str]:
        now = time.time() if now is None else now
        return [i for i, ts in self._armed.items() if ts <= now]

    def disarm(self, incident_id: str) -> None:
        self._armed.pop(incident_id, None)

    def await_human(
        self,
        incident_id: str,
        fetch_reply: Callable[[str], HumanReply | None],
        poll_interval: float = 2.0,
        now_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> HumanReply | None:
        deadline = self._armed.get(incident_id, now_fn())
        while now_fn() < deadline:
            try:
                reply = fetch_reply(incident_id)
            except Exception:
                reply = None
            if reply is not None:
                self.disarm(incident_id)
                return reply
            sleep_fn(poll_interval)
        self.disarm(incident_id)
        return None


def _safely(fn: Callable[[], Any], what: str = "") -> Any:
    try:
        return fn()
    except Exception as exc:
        _log.warning("keepalive: best-effort step failed (%s): %r", what or fn, exc)
        return None


class Watchdog:
    def __init__(
        self,
        run: Any = None,
        settings: Settings | None = None,
        *,
        executor: Any = None,
        suite: Any = None,
        engine: Any = None,
        escalation: Any = None,
        deadline: Any = None,
        memory_: Any = None,
        router: Any = None,
        bus: Any = None,
        cursor: Any = None,
        checkpoint_dir: str = "checkpoints",
        timeout: float | None = None,
        escalate: tuple[str, ...] = ("telegram",),
        loss_key: str | None = None,
        entrypoint: list[str] | None = None,
        reporter: Any = None,
        demo_mode: bool | None = None,
        optimizer: Any = None,
    ) -> None:
        self._run = run
        self.settings = settings or Settings.from_env()
        self._escalate = tuple(escalate)
        self._timeout = timeout if timeout is not None else self.settings.escalation_timeout_s
        self._loss_key = loss_key or self.settings.loss_key
        self._ctx = _capture_run_context(run, checkpoint_dir, self._loss_key, entrypoint)

        self._suite = suite
        self._engine = engine
        self._escalation = escalation
        self._deadline = deadline
        self._memory = memory_
        self._router = router
        self._bus = bus
        self._cursor = cursor
        self._executor = executor

        self._demo_mode = self.settings.demo_mode if demo_mode is None else demo_mode
        self._optimizer = optimizer
        self._reporter = reporter
        self._injector: Any = None
        self._command_poller: Any = None
        self._active_incident = False

        self._redis: Any = None
        self._hook: Any = None
        self._handling = False
        self._started = False
        self._last_step = -1

    @property
    def ctx(self) -> RunContext:
        return self._ctx

    def _redis_client(self) -> Any:
        if self._redis is not None:
            return self._redis
        if not self.settings.redis_url:
            return None
        try:
            import redis  # type: ignore[import-not-found]

            self._redis = redis.Redis.from_url(self.settings.redis_url)
            self._redis.ping()
        except Exception:
            self._redis = None
        return self._redis

    @property
    def suite(self) -> Any:
        if self._suite is None:
            from .detect.rules import DetectorSuite

            self._suite = DetectorSuite(loss_key=self._loss_key)
        return self._suite

    @property
    def engine(self) -> Any:
        if self._engine is None:
            from .diagnose.engine import DiagnosisEngine

            self._engine = DiagnosisEngine(self.settings)
        return self._engine

    @property
    def escalation(self) -> Any:
        if self._escalation is None:
            from .escalate.client import EscalationClient

            self._escalation = EscalationClient(self.settings)
        return self._escalation

    @property
    def deadline(self) -> Any:
        if self._deadline is None:
            client = self._redis_client()
            if client is None:
                self._deadline = _LocalDeadlines()
            else:
                try:
                    from .escalate.deadline import DeadlineClock

                    self._deadline = DeadlineClock(client)
                except Exception:
                    self._deadline = _LocalDeadlines()
        return self._deadline

    @property
    def memory(self) -> Any:
        if self._memory is None:
            try:
                from .memory.incidents import IncidentMemory

                self._memory = IncidentMemory(self.settings)
            except Exception:
                self._memory = None
        return self._memory

    @property
    def router(self) -> Any:
        if self._router is None:
            if not self.settings.redis_url:
                return None
            try:
                from .memory.router import SignalRouter

                self._router = SignalRouter(self.settings.redis_url)
            except Exception:
                self._router = None
        return self._router

    @property
    def cache(self) -> Any:
        if not self.settings.redis_url:
            return None
        try:
            from .memory.cache import DiagnosisCache

            return DiagnosisCache(self.settings.redis_url)
        except Exception:
            return None

    @property
    def bus(self) -> Any:
        if self._bus is None:
            client = self._redis_client()
            if client is None:
                self._bus = None
            else:
                try:
                    from .events import EventBus

                    self._bus = EventBus(client)
                except Exception:
                    self._bus = None
        return self._bus

    @property
    def cursor(self) -> Any:
        if self._cursor is None:
            from .probes.cursor import CursorClient

            self._cursor = CursorClient(self.settings)
        return self._cursor

    @property
    def executor(self) -> Any:
        if self._executor is None:
            try:
                from .probes.sandbox import SandboxExecutor

                self._executor = SandboxExecutor(self.settings)
            except Exception:
                from .probes.local import LocalExecutor

                self._executor = LocalExecutor(self.settings)
        return self._executor

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        bus = self.bus
        if bus is None:
            return
        _safely(lambda: bus.publish(event_type, payload), f"publish:{event_type}")

    @property
    def reporter(self) -> Any:
        if self._reporter is None:
            from .reporter import build_reporter

            self._reporter = _safely(
                lambda: build_reporter(
                    self.settings,
                    self._run,
                    self._ctx.commit_sha,
                    demo_mode=self._demo_mode,
                ),
                "build_reporter",
            )
            if self._reporter is None:
                from .reporter import NullReporter

                self._reporter = NullReporter()
        return self._reporter

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
        from .demo import CommandPoller, FaultInjector

        stall_seconds = self.settings.metrics_poll_timeout_s + 5.0
        self._injector = FaultInjector(
            loss_key=self._loss_key,
            stall_seconds=stall_seconds,
            lr_scale_fn=self._lr_scale_fn if self._optimizer is not None else None,
        )
        project_id = getattr(self.reporter, "project_id", "") or self._ctx.run_id
        self._command_poller = _safely(
            lambda: CommandPoller(self.settings, project_id, self._injector, self.reporter),
            "command_poller",
        )
        if self._command_poller is not None:
            _safely(self._command_poller.start, "command_poller_start")

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
            lambda: self.reporter.emit(
                "run.started",
                "watchdog started",
                include_project=True,
            ),
            "emit_started",
        )
        self._started = True

    def _on_metrics(self, step: int, metrics: dict[str, float]) -> None:
        loss = metrics.get(self._loss_key)
        _safely(lambda: self.reporter.heartbeat(step, loss), "heartbeat")

    def stop(self) -> None:
        if self._hook is not None:
            _safely(self._hook.uninstall, "uninstall_hook")
            self._hook = None
        if self._command_poller is not None:
            _safely(self._command_poller.close, "command_poller_close")
            self._command_poller = None
        if self._started and not self._active_incident:
            _safely(
                lambda: self.reporter.emit("run.stopped", "watchdog stopped", data={"reason": "completed"}),
                "emit_stopped",
            )
        if self._reporter is not None:
            _safely(self._reporter.close, "reporter_close")
            self._reporter = None
        self._started = False

    def __enter__(self) -> Watchdog:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        try:
            if exc is None:
                return False
            if isinstance(exc, KeepaliveError):
                return False
            if isinstance(exc, Exception):
                event = FailureEvent(
                    kind=FailureKind.EXCEPTION,
                    step=self._last_step,
                    message=repr(exc),
                )
                self.handle_failure(event)
                return False
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

    def _emit(self, type: str, message: str, **kwargs: Any) -> None:
        _safely(lambda: self.reporter.emit(type, message, **kwargs), f"emit:{type}")

    def _handle_failure(self, event: FailureEvent) -> None:
        if self._handling:
            return
        self._handling = True
        self._active_incident = True
        if event.step >= 0:
            self._last_step = event.step

        from .diagnose.tools import RunDataFetcher
        from .escalate.voice import VoiceNoteBuilder
        from .probes.cursor import IntegrationNotConnectedError
        from .probes.executor import race
        from .tracing import current_trace_url, incident_attributes

        ctx = self._ctx
        incident = Incident(id=new_id("inc"), run=ctx, failure=event)
        self._publish("failure_detected", {"incident_id": incident.id, "kind": str(event.kind)})
        self._emit(
            "incident.detected",
            event.message,
            incident_id=incident.id,
            level="error",
            data={"kind": str(event.kind), "step": event.step},
            include_project=True,
        )
        incident.status = IncidentStatus.DIAGNOSING

        category_hint = _safely(lambda: self.router.classify(event.message), "router.classify") if self.router else None

        diagnosis: Diagnosis | None
        with incident_attributes(incident):
            diagnosis = self.engine.diagnose(incident, RunDataFetcher(ctx))
        incident.diagnosis = diagnosis
        if category_hint and diagnosis is not None and not diagnosis.category:
            diagnosis.category = category_hint

        incident.trace_url = _safely(current_trace_url, "trace_url")
        if diagnosis is not None:
            self._emit(
                "incident.diagnosed",
                diagnosis.summary,
                incident_id=incident.id,
                data={
                    "diagnosis": diagnosis.summary,
                    "hypotheses": [h.title for h in diagnosis.hypotheses],
                },
            )

        # "sms" accepted as a legacy alias for the remote escalation channel.
        escalate_enabled = (
            bool({"telegram", "sms"} & set(self._escalate))
            and bool(self.settings.api_key)
            and bool(self.settings.telegram_chat_id)
        )
        reply: HumanReply | None = None
        if escalate_enabled:
            voice = VoiceNoteBuilder(self.settings)
            script = _safely(lambda: voice.script_for(incident), "voice.script_for")
            _safely(
                lambda: self.escalation.notify_incident(incident, voice_script=script),
                "notify_incident",
            )
            incident.status = IncidentStatus.ESCALATED
            incident.deadline_ts = _safely(lambda: self.deadline.arm(incident.id, self._timeout), "deadline.arm")
            esc_data: dict[str, Any] = {"deadline_ts": incident.deadline_ts}
            if incident.trace_url:
                esc_data["weave_url"] = incident.trace_url
            self._emit("incident.escalated", "escalated to human", incident_id=incident.id, data=esc_data)
            reply = _safely(
                lambda: self.deadline.await_human(
                    incident.id,
                    self.escalation.fetch_reply,
                    poll_interval=self.settings.reply_poll_interval_s,
                ),
                "await_human",
            )
            incident.reply = reply
            if reply is not None:
                self._emit(
                    "incident.human_reply",
                    f"human replied {reply.value}",
                    incident_id=incident.id,
                    data={"reply": reply.value},
                )
            else:
                self._emit("incident.deadline_expired", "deadline expired", incident_id=incident.id, data={})

        if reply == HumanReply.STOP:
            incident.status = IncidentStatus.STOPPED
            self._emit(
                "incident.stopped",
                "human stopped the run",
                incident_id=incident.id,
                level="warn",
                data={"reason": "human stop"},
            )
            _safely(lambda: self.memory.remember(incident, "human stopped the run"), "remember")
            _safely(lambda: self.escalation.send_recap(incident, "Run stopped by human."), "recap")
            raise KeepaliveStop("human stopped the run")

        if reply == HumanReply.ROLLBACK:
            incident.status = IncidentStatus.RESOLVED
            _safely(
                lambda: self.memory.remember(incident, f"human rolled back to {ctx.last_checkpoint}"),
                "remember",
            )
            _safely(
                lambda: self.escalation.send_recap(incident, f"Rolled back to {ctx.last_checkpoint}."),
                "recap",
            )
            raise KeepaliveRollback(ctx.last_checkpoint)

        incident.status = IncidentStatus.AUTONOMOUS
        self._publish("authority_transferred", {"incident_id": incident.id})

        incident.status = IncidentStatus.PROBING
        hypotheses = diagnosis.hypotheses[: self.settings.max_probes] if diagnosis else []
        if not hypotheses:
            incident.status = IncidentStatus.FAILED
            self._emit(
                "incident.stopped",
                "no fix hypotheses generated",
                incident_id=incident.id,
                level="error",
                data={"reason": "no hypotheses"},
            )
            _safely(lambda: self.escalation.send_recap(incident, "No fix hypotheses generated."), "recap")
            raise KeepaliveStop("no fix hypotheses")

        specs = []
        for hyp in hypotheses:
            try:
                spec = self.cursor.spawn_probe(hyp, ctx, incident.id)
                self._emit(
                    "agent.spawned",
                    f"spawned probe for {hyp.title}",
                    incident_id=incident.id,
                    agent_id=spec.id,
                    data={"hypothesis": hyp.title, "cursor_agent_id": spec.agent_id},
                )
                spec = self.cursor.wait_for_branch(spec)
                if spec.branch:
                    self._emit(
                        "agent.status",
                        f"branch pushed {spec.branch}",
                        incident_id=incident.id,
                        agent_id=spec.id,
                        data={"state": "branch_pushed", "branch": spec.branch},
                    )
                else:
                    self._emit(
                        "agent.status",
                        "probe failed to push a branch",
                        incident_id=incident.id,
                        agent_id=spec.id,
                        level="warn",
                        data={"state": "failed"},
                    )
                specs.append(spec)
            except IntegrationNotConnectedError:
                _safely(
                    lambda: self.escalation.send_recap(
                        incident,
                        "Cursor repo not connected: Dashboard -> Integrations -> connect the training repo.",
                    ),
                    "recap",
                )
                raise KeepaliveStop("cursor integration not connected") from None
            except Exception as exc:
                _log.warning("keepalive: probe spawn skipped: %r", exc)
                continue

        if not specs:
            incident.status = IncidentStatus.FAILED
            self._emit(
                "incident.stopped",
                "all probe agents failed to start",
                incident_id=incident.id,
                level="error",
                data={"reason": "no probes spawned"},
            )
            _safely(lambda: self.escalation.send_recap(incident, "All probe agents failed to start."), "recap")
            raise KeepaliveStop("no probes spawned")

        from .types import ProbeState

        for spec in specs:
            if spec.state == ProbeState.READY and spec.branch:
                self._emit(
                    "agent.status",
                    "probe run started",
                    incident_id=incident.id,
                    agent_id=spec.id,
                    data={"state": "running"},
                )

        incident.probes = specs

        def _on_update(r: Any) -> None:
            self._publish(
                "probe_result",
                {"probe_id": r.spec.id, "state": str(r.state), "final_loss": r.final_loss},
            )
            state = "finished" if r.state == ProbeState.FINISHED else "failed"
            status_data: dict[str, Any] = {"state": state}
            if r.wandb_run_id is not None:
                status_data["wandb_run_id"] = r.wandb_run_id
            if r.error is not None:
                status_data["error"] = r.error
            self._emit(
                "agent.status",
                f"probe {state}",
                incident_id=incident.id,
                agent_id=r.spec.id,
                level="info" if state == "finished" else "warn",
                data=status_data,
            )
            if r.final_loss is not None:
                self._emit(
                    "agent.metrics",
                    f"final loss {r.final_loss}",
                    incident_id=incident.id,
                    agent_id=r.spec.id,
                    data={"final_loss": r.final_loss},
                )

        winner, _results = race(
            specs,
            self.executor,
            ctx,
            steps=self.settings.probe_steps,
            on_update=_on_update,
        )

        if winner is None:
            incident.status = IncidentStatus.FAILED
            self._emit(
                "incident.stopped",
                "all probes failed; no winner",
                incident_id=incident.id,
                level="error",
                data={"reason": "all probes failed"},
            )
            _safely(lambda: self.memory.remember(incident, "all probes failed"), "remember")
            _safely(lambda: self.escalation.send_recap(incident, "All probes failed; no winner."), "recap")
            raise KeepaliveStop("all probes failed")

        incident.status = IncidentStatus.RESOLVED
        incident.winner_probe_id = winner.spec.id
        self._emit(
            "incident.promoted",
            f"promoted {winner.spec.id}",
            incident_id=incident.id,
            agent_id=winner.spec.id,
            data={"winner_agent_id": winner.spec.id, "final_loss": winner.final_loss},
        )
        self._promote_parent(winner)
        _safely(
            lambda: self.memory.remember(
                incident,
                f"winner {winner.spec.id} branch {winner.spec.branch} final_loss {winner.final_loss}",
            ),
            "remember",
        )
        _safely(
            lambda: self.escalation.send_recap(
                incident,
                f"Recovered via {winner.spec.branch} (loss {winner.final_loss}). Trace: {incident.trace_url}",
            ),
            "recap",
        )
        raise KeepaliveHandedOff(incident, winner)

    def _promote_parent(self, winner: Any) -> None:
        def _tag() -> None:
            run = self._run
            if run is None or not hasattr(run, "update"):
                import wandb  # type: ignore[import-not-found]

                run = wandb.Api().run(self._ctx.run_path)
            run.tags = (*tuple(getattr(run, "tags", ()) or ()), "keepalive-recovered")
            note = f"keepalive recovered via probe {winner.spec.id} branch {winner.spec.branch}"
            existing = getattr(run, "notes", "") or ""
            run.notes = (existing + "\n" + note).strip()
            run.update()

        _safely(_tag, "promote_parent")


@contextlib.contextmanager
def watchdog(
    run: Any = None,
    *,
    escalate: tuple[str, ...] = ("telegram",),
    timeout: float | None = None,
    checkpoint_dir: str = "checkpoints",
    loss_key: str | None = None,
    settings: Settings | None = None,
    executor: Any = None,
    demo_mode: bool | None = None,
    optimizer: Any = None,
    **collaborators: Any,
) -> Iterator[Watchdog]:
    wd = Watchdog(
        run,
        settings=settings,
        executor=executor,
        checkpoint_dir=checkpoint_dir,
        timeout=timeout,
        escalate=escalate,
        loss_key=loss_key,
        demo_mode=demo_mode,
        optimizer=optimizer,
        **collaborators,
    )
    with wd:
        yield wd
