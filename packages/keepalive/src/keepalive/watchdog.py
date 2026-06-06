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
        escalate: tuple[str, ...] = ("sms",),
        loss_key: str | None = None,
        entrypoint: list[str] | None = None,
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

            self._suite = DetectorSuite()
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
            try:
                from .memory.router import SignalRouter

                self._router = SignalRouter(self.settings.redis_url)
            except Exception:
                self._router = None
        return self._router

    @property
    def cache(self) -> Any:
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

    def start(self) -> None:
        if self._started:
            return
        from .tracing import init_tracing

        _safely(lambda: init_tracing(self.settings.weave_project), "init_tracing")
        if self._run is not None:
            from .detect.monitor import MetricHook

            self._hook = MetricHook(self.suite, on_failure=self.handle_failure)
            _safely(lambda: self._hook.install(self._run), "install_hook")
        self._started = True

    def stop(self) -> None:
        if self._hook is not None:
            _safely(self._hook.uninstall, "uninstall_hook")
            self._hook = None
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

    def _handle_failure(self, event: FailureEvent) -> None:
        if self._handling:
            return
        self._handling = True
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
        incident.status = IncidentStatus.DIAGNOSING

        category_hint = _safely(lambda: self.router.classify(event.message), "router.classify") if self.router else None

        diagnosis: Diagnosis | None
        with incident_attributes(incident):
            diagnosis = self.engine.diagnose(incident, RunDataFetcher(ctx))
        incident.diagnosis = diagnosis
        if category_hint and diagnosis is not None and not diagnosis.category:
            diagnosis.category = category_hint

        incident.trace_url = _safely(current_trace_url, "trace_url")

        escalate_enabled = "sms" in self._escalate and bool(self.settings.api_key) and bool(self.settings.phone_number)
        reply: HumanReply | None = None
        if escalate_enabled:
            voice = VoiceNoteBuilder(self.settings)
            voice_url = _safely(
                lambda: self.escalation.upload_voice_note(incident.id, voice.synthesize(voice.script_for(incident))),
                "upload_voice_note",
            )
            _safely(
                lambda: self.escalation.notify_incident(incident, voice_note_url=voice_url),
                "notify_incident",
            )
            incident.status = IncidentStatus.ESCALATED
            incident.deadline_ts = _safely(lambda: self.deadline.arm(incident.id, self._timeout), "deadline.arm")
            reply = _safely(
                lambda: self.deadline.await_human(
                    incident.id,
                    self.escalation.fetch_reply,
                    poll_interval=self.settings.reply_poll_interval_s,
                ),
                "await_human",
            )
            incident.reply = reply

        if reply == HumanReply.STOP:
            incident.status = IncidentStatus.STOPPED
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
            _safely(lambda: self.escalation.send_recap(incident, "No fix hypotheses generated."), "recap")
            raise KeepaliveStop("no fix hypotheses")

        specs = []
        for hyp in hypotheses:
            try:
                spec = self.cursor.spawn_probe(hyp, ctx, incident.id)
                spec = self.cursor.wait_for_branch(spec)
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
            _safely(lambda: self.escalation.send_recap(incident, "All probe agents failed to start."), "recap")
            raise KeepaliveStop("no probes spawned")

        incident.probes = specs
        winner, _results = race(
            specs,
            self.executor,
            ctx,
            steps=self.settings.probe_steps,
            on_update=lambda r: self._publish(
                "probe_result",
                {"probe_id": r.spec.id, "state": str(r.state), "final_loss": r.final_loss},
            ),
        )

        if winner is None:
            incident.status = IncidentStatus.FAILED
            _safely(lambda: self.memory.remember(incident, "all probes failed"), "remember")
            _safely(lambda: self.escalation.send_recap(incident, "All probes failed; no winner."), "recap")
            raise KeepaliveStop("all probes failed")

        incident.status = IncidentStatus.RESOLVED
        incident.winner_probe_id = winner.spec.id
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
    escalate: tuple[str, ...] = ("sms",),
    timeout: float | None = None,
    checkpoint_dir: str = "checkpoints",
    loss_key: str | None = None,
    settings: Settings | None = None,
    executor: Any = None,
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
        **collaborators,
    )
    with wd:
        yield wd
