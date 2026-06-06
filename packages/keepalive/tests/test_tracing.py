from __future__ import annotations

import pytest

import keepalive.tracing as tracing
from keepalive.tracing import (
    current_trace_url,
    incident_attributes,
    init_tracing,
    traced,
)
from keepalive.types import (
    FailureEvent,
    FailureKind,
    Incident,
    RunContext,
)


@pytest.fixture(autouse=True)
def clear_init_cache() -> None:
    tracing._initialized.clear()


def _incident() -> Incident:
    run = RunContext(
        run_id="r1",
        project="p",
        entity="e",
        run_url="https://wandb.ai/e/p/r1",
        commit_sha="abc123",
        repo_url="https://github.com/x/y",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
    )
    failure = FailureEvent(kind=FailureKind.NAN_LOSS, step=5, message="boom")
    return Incident(id="inc1", run=run, failure=failure)


def test_traced_bare_decorator_computes() -> None:
    @traced
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_traced_with_name_computes() -> None:
    @traced(name="mul")
    def mul(a: int, b: int) -> int:
        return a * b

    assert mul(4, 5) == 20


def test_incident_attributes_yields() -> None:
    with incident_attributes(_incident()):
        pass


def test_current_trace_url_no_init() -> None:
    result = current_trace_url()
    assert result is None or isinstance(result, str)


def test_init_tracing_returns_false_when_weave_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import weave

    def boom(_project: str) -> None:
        raise RuntimeError("offline")

    monkeypatch.setattr(weave, "init", boom)
    assert init_tracing("not-a-real-project") is False


def test_init_tracing_returns_true_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    import weave

    calls: list[str] = []

    def fake_init(project: str) -> None:
        calls.append(project)

    monkeypatch.setattr(weave, "init", fake_init)
    assert init_tracing("offline-project") is True
    assert init_tracing("offline-project") is True
    assert calls == ["offline-project"]
