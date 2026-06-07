from __future__ import annotations

import shlex

from keepalive.config import Settings
from keepalive.probes.sandbox import SandboxExecutor, _portable_entrypoint
from keepalive.types import FixHypothesis, ProbeSpec, ProbeState, RunContext


def _ctx(entrypoint: list[str]) -> RunContext:
    return RunContext(
        run_id="run1",
        project="proj",
        entity="ent",
        run_url="u",
        commit_sha="sha",
        repo_url="https://github.com/me/repo",
        entrypoint=entrypoint,
        checkpoint_dir="/ckpt",
        last_checkpoint="/ckpt/last.pt",
        loss_key="loss",
    )


def _spec() -> ProbeSpec:
    h = FixHypothesis(id="h", title="t", rationale="r", instructions="i")
    return ProbeSpec(id="probe_1", incident_id="inc1", hypothesis=h, branch="cursor/probe-x", state=ProbeState.READY)


def test_portable_entrypoint_swaps_absolute_python() -> None:
    assert _portable_entrypoint(["/venv/bin/python3", "train.py"]) == ["python", "train.py"]
    assert _portable_entrypoint(["/usr/local/bin/python3.13", "-m", "train"]) == ["python", "-m", "train"]


def test_portable_entrypoint_keeps_bare_commands() -> None:
    assert _portable_entrypoint(["python", "train.py"]) == ["python", "train.py"]
    assert _portable_entrypoint(["accelerate", "launch", "train.py"]) == ["accelerate", "launch", "train.py"]
    assert _portable_entrypoint([]) == []


def test_portable_entrypoint_keeps_absolute_non_python() -> None:
    assert _portable_entrypoint(["/usr/bin/torchrun", "train.py"]) == ["/usr/bin/torchrun", "train.py"]


def test_build_script_quotes_entrypoint_args() -> None:
    ex = SandboxExecutor(Settings(wandb_api_key="wk"))
    ctx = _ctx(["/venv/bin/python3", "train.py", "--config", "my config.yaml", "--overrides", '{"lr": 1e-4}'])
    script = ex._build_script(_spec(), ctx, steps=300)

    assert "python train.py" in script
    assert "/venv/bin/python3" not in script
    assert shlex.quote("my config.yaml") in script
    assert shlex.quote('{"lr": 1e-4}') in script
    # the assembled command round-trips through shell tokenization intact
    tail = script.rsplit(" && ", 1)[1]
    tokens = shlex.split(tail)
    assert tokens[0] == "env"
    assert tokens[-6:] == ["python", "train.py", "--config", "my config.yaml", "--overrides", '{"lr": 1e-4}']


def test_build_script_checks_out_branch_and_exports_env() -> None:
    ex = SandboxExecutor(Settings(wandb_api_key="wk"))
    script = ex._build_script(_spec(), _ctx(["python", "train.py"]), steps=42)
    assert "git clone https://github.com/me/repo repo" in script
    assert "git checkout cursor/probe-x" in script
    assert "WANDB_RUN_GROUP=watchdog-run1" in script
    assert "KEEPALIVE_MAX_STEPS=42" in script
