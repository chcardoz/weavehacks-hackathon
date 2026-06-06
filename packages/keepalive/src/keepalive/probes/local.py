from __future__ import annotations

import contextlib
import os
import subprocess
from pathlib import Path

from ..config import Settings
from ..types import ProbeResult, ProbeSpec, ProbeState, RunContext
from . import judge
from .sandbox import _probe_env


class LocalExecutor:
    def __init__(self, settings: Settings, repo_root: Path | str | None = None) -> None:
        self._settings = settings
        self._repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
        self._procs: dict[str, subprocess.Popen[str]] = {}

    def execute(self, spec: ProbeSpec, ctx: RunContext, *, steps: int) -> ProbeResult:
        if spec.branch is None:
            spec.state = ProbeState.FAILED
            return ProbeResult(
                spec=spec, wandb_run_id=None, history=[], final_loss=None, state=ProbeState.FAILED, error="no branch"
            )
        spec.state = ProbeState.RUNNING
        worktree_dir = self._repo_root / ".keepalive" / "worktrees" / spec.id
        error: str | None = None
        stderr_tail = ""
        returncode: int | None = None
        try:
            subprocess.run(
                ["git", "fetch", "origin", spec.branch],
                cwd=self._repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            worktree_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", str(worktree_dir), f"origin/{spec.branch}"],
                cwd=self._repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            env = os.environ | _probe_env(self._settings, ctx, spec, steps)
            proc = subprocess.Popen(
                ctx.entrypoint,
                cwd=worktree_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._procs[spec.id] = proc
            try:
                _, stderr = proc.communicate(timeout=self._settings.probe_run_timeout_s)
                returncode = proc.returncode
                stderr_tail = (stderr or "")[-500:]
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    _, stderr = proc.communicate(timeout=10.0)
                    stderr_tail = (stderr or "")[-500:]
                except Exception:
                    pass
                returncode = proc.returncode
                error = "probe run timed out"
        except subprocess.CalledProcessError as exc:
            error = f"git worktree setup failed: {(exc.stderr or '')[-500:]}"
        except Exception as exc:
            error = f"local executor error: {exc}"
        finally:
            self._procs.pop(spec.id, None)
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree_dir)],
                    cwd=self._repo_root,
                    check=False,
                    capture_output=True,
                    text=True,
                )

        return self._collect_result(spec, ctx, error, returncode, stderr_tail)

    def _collect_result(
        self,
        spec: ProbeSpec,
        ctx: RunContext,
        error: str | None,
        returncode: int | None,
        stderr_tail: str,
    ) -> ProbeResult:
        wandb_run_id: str | None = None
        final_loss = None
        history: list = []
        try:
            import wandb

            api = wandb.Api()
            wandb_run_id = judge.find_probe_run(api, ctx.entity, ctx.project, f"watchdog-{ctx.run_id}", spec.id)
            if wandb_run_id is not None:
                final_loss, history = judge.fetch_probe_metrics(
                    f"{ctx.entity}/{ctx.project}/{wandb_run_id}", api=api, loss_key=ctx.loss_key
                )
        except Exception:
            pass

        succeeded = (returncode == 0 or wandb_run_id is not None) and error != "probe run timed out"
        if succeeded and error is None:
            spec.state = ProbeState.FINISHED
            return ProbeResult(
                spec=spec, wandb_run_id=wandb_run_id, history=history, final_loss=final_loss, state=ProbeState.FINISHED
            )
        spec.state = ProbeState.FAILED
        detail = error or f"probe exited {returncode}: {stderr_tail}"
        return ProbeResult(
            spec=spec,
            wandb_run_id=wandb_run_id,
            history=history,
            final_loss=final_loss,
            state=ProbeState.FAILED,
            error=detail,
        )

    def kill(self, spec: ProbeSpec) -> None:
        proc = self._procs.get(spec.id)
        if proc is not None:
            with contextlib.suppress(Exception):
                proc.terminate()
            self._procs.pop(spec.id, None)
