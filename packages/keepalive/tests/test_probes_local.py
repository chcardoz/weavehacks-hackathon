from __future__ import annotations

from typing import Any

import pytest

from keepalive.config import Settings
from keepalive.probes.local import LocalExecutor
from keepalive.types import FixHypothesis, ProbeSpec, ProbeState, RunContext


def _ctx() -> RunContext:
    return RunContext(
        run_id="run1",
        project="proj",
        entity="ent",
        run_url="u",
        commit_sha="sha",
        repo_url="https://github.com/me/repo",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
        last_checkpoint="/ckpt/last.pt",
        loss_key="loss",
    )


def _spec(branch: str | None = "cursor/probe-x") -> ProbeSpec:
    h = FixHypothesis(id="h", title="t", rationale="r", instructions="i")
    return ProbeSpec(id="probe_1", incident_id="inc1", hypothesis=h, branch=branch, state=ProbeState.READY)


class _FakeProc:
    def __init__(self, returncode: int = 0, communicate_exc: Exception | None = None) -> None:
        self.returncode = returncode
        self._exc = communicate_exc
        self.terminated = False

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if self._exc is not None:
            raise self._exc
        return ("", "")

    def terminate(self) -> None:
        self.terminated = True


@pytest.fixture
def patched(mocker: Any) -> dict[str, Any]:
    calls: dict[str, Any] = {"run_cmds": [], "popen": None}

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        calls["run_cmds"].append((cmd, kwargs))
        return mocker.Mock(returncode=0, stdout="", stderr="")

    proc = _FakeProc(returncode=0)

    def fake_popen(cmd: list[str], **kwargs: Any) -> Any:
        calls["popen"] = {"cmd": cmd, "kwargs": kwargs}
        calls["proc"] = proc
        return proc

    fake_subprocess = mocker.patch("keepalive.probes.local.subprocess")
    fake_subprocess.run.side_effect = fake_run
    fake_subprocess.Popen.side_effect = fake_popen
    # Preserve real exception classes used in except clauses.
    import subprocess as real_subprocess

    fake_subprocess.CalledProcessError = real_subprocess.CalledProcessError
    fake_subprocess.TimeoutExpired = real_subprocess.TimeoutExpired
    fake_subprocess.PIPE = real_subprocess.PIPE

    # _collect_result does `import wandb; api = wandb.Api()` before calling judge.*;
    # stub Api so it doesn't touch the network, then judge.* are patched below.
    mocker.patch("wandb.Api", return_value=mocker.Mock())
    mocker.patch("keepalive.probes.local.judge.find_probe_run", return_value="wrun-1")
    mocker.patch("keepalive.probes.local.judge.fetch_probe_metrics", return_value=(0.5, []))

    calls["subprocess"] = fake_subprocess
    calls["proc_obj"] = proc
    return calls


def test_execute_runs_worktree_and_entrypoint_with_env(patched: dict[str, Any], tmp_path: Any) -> None:
    ex = LocalExecutor(Settings(wandb_api_key="wk"), repo_root=tmp_path)
    spec = _spec()
    ctx = _ctx()
    result = ex.execute(spec, ctx, steps=42)

    # git fetch + worktree add commands ran
    run_cmds = [c[0] for c in patched["run_cmds"]]
    assert ["git", "fetch", "origin", spec.branch] in run_cmds
    assert any(c[:3] == ["git", "worktree", "add"] for c in run_cmds)

    popen = patched["popen"]
    assert popen["cmd"] == ctx.entrypoint
    env = popen["kwargs"]["env"]
    assert env["WANDB_RUN_GROUP"] == f"watchdog-{ctx.run_id}"
    assert env["WANDB_JOB_TYPE"] == "probe"
    assert env["WANDB_NAME"] == spec.id
    assert env["KEEPALIVE_MAX_STEPS"] == "42"

    assert result.state == ProbeState.FINISHED
    assert result.final_loss == 0.5
    assert result.wandb_run_id == "wrun-1"


def test_execute_no_branch_fails_without_subprocess() -> None:
    ex = LocalExecutor(Settings(), repo_root="/repo")
    spec = _spec(branch=None)
    result = ex.execute(spec, _ctx(), steps=5)
    assert result.state == ProbeState.FAILED
    assert result.error == "no branch"


def test_worktree_cleanup_runs_in_finally_even_when_communicate_raises(patched: dict[str, Any], tmp_path: Any) -> None:
    # Replace proc with one whose communicate raises a generic exception.
    boom = _FakeProc(returncode=1, communicate_exc=RuntimeError("comm fail"))

    def fake_popen(cmd: list[str], **kwargs: Any) -> Any:
        return boom

    patched["subprocess"].Popen.side_effect = fake_popen

    ex = LocalExecutor(Settings(), repo_root=tmp_path)
    result = ex.execute(_spec(), _ctx(), steps=5)

    # cleanup (worktree remove) must have been invoked despite the error
    run_cmds = [c[0] for c in patched["run_cmds"]]
    assert any(c[:3] == ["git", "worktree", "remove"] for c in run_cmds)
    # find_probe_run still returned a run id, so result may be FINISHED;
    # the load-bearing assertion is that cleanup ran. State must be set.
    assert result.state in (ProbeState.FINISHED, ProbeState.FAILED)


def test_execute_returncode_nonzero_no_wandb_fails(patched: dict[str, Any], mocker: Any, tmp_path: Any) -> None:
    # No wandb run found -> failure path.
    mocker.patch("keepalive.probes.local.judge.find_probe_run", return_value=None)
    bad = _FakeProc(returncode=2)
    patched["subprocess"].Popen.side_effect = lambda cmd, **kw: bad

    ex = LocalExecutor(Settings(), repo_root=tmp_path)
    result = ex.execute(_spec(), _ctx(), steps=5)
    assert result.state == ProbeState.FAILED


def test_kill_terminates_tracked_process(patched: dict[str, Any]) -> None:
    ex = LocalExecutor(Settings(), repo_root="/repo")
    proc = _FakeProc()
    spec = _spec()
    ex._procs[spec.id] = proc
    ex.kill(spec)
    assert proc.terminated is True
    assert spec.id not in ex._procs
