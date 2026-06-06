from __future__ import annotations

import shlex
from typing import Any

from ..config import Settings
from ..types import ProbeResult, ProbeSpec, ProbeState, RunContext
from . import judge


def _probe_env(settings: Settings, ctx: RunContext, spec: ProbeSpec, steps: int) -> dict[str, str]:
    return {
        "WANDB_API_KEY": settings.wandb_api_key,
        "WANDB_PROJECT": ctx.project,
        "WANDB_ENTITY": ctx.entity,
        "WANDB_RUN_GROUP": f"watchdog-{ctx.run_id}",
        "WANDB_JOB_TYPE": "probe",
        "WANDB_NAME": spec.id,
        "WANDB_RESUME": "allow",
        "KEEPALIVE_RESUME_FROM": ctx.last_checkpoint or "",
        "KEEPALIVE_MAX_STEPS": str(steps),
    }


class _Session:
    def __init__(self, raw: Any, exec_fn: Any, cleanup_fn: Any | None) -> None:
        self._raw = raw
        self._exec_fn = exec_fn
        self._cleanup_fn = cleanup_fn

    def run_command(self, cmd: str) -> Any:
        return self._exec_fn(cmd)

    def cleanup(self) -> None:
        if self._cleanup_fn is not None:
            try:
                self._cleanup_fn()
            except Exception:
                pass


class SandboxExecutor:
    def __init__(self, settings: Settings, session_factory: Any | None = None) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._sessions: dict[str, Any] = {}

    def _open_session(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory()
        from wandb.sandbox import Sandbox

        raw = Sandbox()
        exec_fn = None
        for name in ("run_command", "exec", "run"):
            candidate = getattr(raw, name, None)
            if callable(candidate):
                exec_fn = candidate
                break
        if exec_fn is None:
            raise RuntimeError("wandb Sandbox exposes no run_command/exec/run method")
        cleanup_fn = None
        for name in ("terminate", "stop", "close"):
            candidate = getattr(raw, name, None)
            if callable(candidate):
                cleanup_fn = candidate
                break
        return _Session(raw, exec_fn, cleanup_fn)

    def _build_script(self, spec: ProbeSpec, ctx: RunContext, steps: int) -> str:
        env = _probe_env(self._settings, ctx, spec, steps)
        env_prefix = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
        entry = " ".join(ctx.entrypoint)
        branch = spec.branch or ""
        return (
            f"set -e && git clone {shlex.quote(ctx.repo_url)} repo && cd repo "
            f"&& git checkout {shlex.quote(branch)} "
            "&& (pip install -e . || pip install -r requirements.txt || true) "
            f"&& env {env_prefix} {entry}"
        )

    def execute(self, spec: ProbeSpec, ctx: RunContext, *, steps: int) -> ProbeResult:
        spec.state = ProbeState.RUNNING
        session: Any | None = None
        error: str | None = None
        try:
            session = self._open_session()
            self._sessions[spec.id] = session
            script = self._build_script(spec, ctx, steps)
            result = session.run_command(script)
            returncode = getattr(result, "returncode", 0)
            stdout = getattr(result, "stdout", "") or ""
            if returncode != 0:
                error = f"probe command exited {returncode}: {stdout[-500:]}"
        except Exception as exc:  # noqa: BLE001
            error = f"sandbox error: {exc}"
        finally:
            if session is not None:
                session.cleanup()
            self._sessions.pop(spec.id, None)

        return self._collect_result(spec, ctx, error)

    def _collect_result(self, spec: ProbeSpec, ctx: RunContext, error: str | None) -> ProbeResult:
        wandb_run_id: str | None = None
        final_loss = None
        history: list = []
        try:
            import wandb

            api = wandb.Api()
            wandb_run_id = judge.find_probe_run(
                api, ctx.entity, ctx.project, f"watchdog-{ctx.run_id}", spec.id
            )
            if wandb_run_id is not None:
                final_loss, history = judge.fetch_probe_metrics(
                    f"{ctx.entity}/{ctx.project}/{wandb_run_id}", api=api, loss_key=ctx.loss_key
                )
        except Exception as exc:  # noqa: BLE001
            if error is None:
                error = f"metric fetch failed: {exc}"

        if error is None and wandb_run_id is not None:
            spec.state = ProbeState.FINISHED
            return ProbeResult(
                spec=spec,
                wandb_run_id=wandb_run_id,
                history=history,
                final_loss=final_loss,
                state=ProbeState.FINISHED,
            )
        spec.state = ProbeState.FAILED
        return ProbeResult(
            spec=spec,
            wandb_run_id=wandb_run_id,
            history=history,
            final_loss=final_loss,
            state=ProbeState.FAILED,
            error=error or "probe produced no wandb run",
        )

    def kill(self, spec: ProbeSpec) -> None:
        session = self._sessions.get(spec.id)
        if session is not None:
            cleanup = getattr(session, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    pass
            else:
                for name in ("terminate", "stop", "close"):
                    fn = getattr(session, name, None)
                    if callable(fn):
                        try:
                            fn()
                        except Exception:
                            pass
                        break
            self._sessions.pop(spec.id, None)
