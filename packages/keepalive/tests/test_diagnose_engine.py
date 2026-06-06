from __future__ import annotations

import json
import types as _types
from typing import Any

import pytest

from keepalive.config import Settings
from keepalive.diagnose.engine import DiagnosisEngine, _diagnosis_from_dict
from keepalive.types import (
    Diagnosis,
    FailureEvent,
    FailureKind,
    Incident,
    RunContext,
)


# --------------------------------------------------------------------------- #
# Helpers: minimal OpenAI-shaped fakes                                          #
# --------------------------------------------------------------------------- #
def make_tool_call(call_id: str, name: str, arguments: dict[str, Any] | str) -> Any:
    args_str = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return _types.SimpleNamespace(
        id=call_id,
        function=_types.SimpleNamespace(name=name, arguments=args_str),
    )


def make_response(content: str = "", tool_calls: list[Any] | None = None) -> Any:
    message = _types.SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = _types.SimpleNamespace(message=message)
    return _types.SimpleNamespace(choices=[choice])


class FakeChat:
    """Fake OpenAI client: queue responses, record create() calls."""

    def __init__(self, responses: list[Any] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []
        self.chat = _types.SimpleNamespace(completions=_types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeChat ran out of queued responses")
        return self._responses.pop(0)


class RaisingChat:
    """Client that explodes if .chat.completions.create is ever called."""

    def __init__(self) -> None:
        self.chat = _types.SimpleNamespace(completions=_types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        raise AssertionError("client must not be called (cache hit expected)")


class FakeFetcher:
    """RunDataFetcher-shaped fake recording its calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_run_history(self, keys: Any = None, last_n: int = 50) -> Any:
        self.calls.append(("get_run_history", {"keys": keys, "last_n": last_n}))
        return [{"_step": 400, "loss": float("nan")}]

    def get_logs(self, tail: int = 100) -> str:
        self.calls.append(("get_logs", {"tail": tail}))
        return "some logs"

    def get_config(self) -> dict[str, Any]:
        self.calls.append(("get_config", {}))
        return {"lr": 0.1}


class DictCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str]] = []

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> None:
        self.set_calls.append((key, value))
        self.store[key] = value


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #
def make_run() -> RunContext:
    return RunContext(
        run_id="run123",
        project="proj",
        entity="team",
        run_url="https://wandb.ai/team/proj/run123",
        commit_sha="abc123",
        repo_url="https://github.com/x/y",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
    )


def make_incident() -> Incident:
    failure = FailureEvent(
        kind=FailureKind.NAN_LOSS,
        step=400,
        message="loss became NaN",
        metrics={"loss": float("nan")},
    )
    return Incident(id="inc_1", run=make_run(), failure=failure)


@pytest.fixture
def settings() -> Settings:
    return Settings(diagnosis_model="gpt-5.4", max_probes=3)


# --------------------------------------------------------------------------- #
# Tests                                                                         #
# --------------------------------------------------------------------------- #
def test_diagnose_happy_path_clamps_confidence_and_assigns_ids(settings: Settings) -> None:
    submit_args = {
        "summary": "NaN loss from LR spike",
        "category": "divergence",
        "confidence": 1.7,  # out of range -> clamp to 1.0
        "hypotheses": [
            {"title": "lower lr", "rationale": "r1", "instructions": "i1"},
            {"title": "grad clip", "rationale": "r2", "instructions": "i2"},
        ],
    }
    responses = [
        make_response(tool_calls=[make_tool_call("t1", "get_run_history", {"last_n": 10})]),
        make_response(tool_calls=[make_tool_call("t2", "submit_diagnosis", submit_args)]),
    ]
    client = FakeChat(responses)
    engine = DiagnosisEngine(settings, client=client)

    diag = engine.diagnose(make_incident(), FakeFetcher())  # type: ignore[arg-type]

    assert isinstance(diag, Diagnosis)
    assert diag.summary == "NaN loss from LR spike"
    assert diag.category == "divergence"
    assert diag.confidence == 1.0  # clamped into [0, 1]
    assert len(diag.hypotheses) == 2
    for hyp in diag.hypotheses:
        assert hyp.id.startswith("hyp_")
    assert diag.raw["model"] == "gpt-5.4"


def test_diagnose_caps_hypotheses_at_max_probes() -> None:
    settings = Settings(diagnosis_model="gpt-5.4", max_probes=3)
    five = [{"title": f"h{i}", "rationale": "r", "instructions": "i"} for i in range(5)]
    submit_args = {
        "summary": "s",
        "category": "c",
        "confidence": 0.5,
        "hypotheses": five,
    }
    client = FakeChat([make_response(tool_calls=[make_tool_call("t1", "submit_diagnosis", submit_args)])])
    engine = DiagnosisEngine(settings, client=client)

    diag = engine.diagnose(make_incident(), FakeFetcher())  # type: ignore[arg-type]

    assert len(diag.hypotheses) == 3  # capped at max_probes


def test_tool_dispatch_records_calls_and_grows_tool_messages(settings: Settings) -> None:
    submit_args = {
        "summary": "s",
        "category": "c",
        "confidence": 0.4,
        "hypotheses": [{"title": "h", "rationale": "r", "instructions": "i"}],
    }
    # Round 1: three data tool calls; Round 2: submit.
    responses = [
        make_response(
            tool_calls=[
                make_tool_call("a", "get_run_history", {"last_n": 5}),
                make_tool_call("b", "get_logs", {"tail": 20}),
                make_tool_call("c", "get_config", {}),
            ]
        ),
        make_response(tool_calls=[make_tool_call("d", "submit_diagnosis", submit_args)]),
    ]
    client = FakeChat(responses)
    fetcher = FakeFetcher()
    engine = DiagnosisEngine(settings, client=client)

    engine.diagnose(make_incident(), fetcher)  # type: ignore[arg-type]

    names = [name for name, _ in fetcher.calls]
    assert names == ["get_run_history", "get_logs", "get_config"]
    assert fetcher.calls[0][1]["last_n"] == 5
    assert fetcher.calls[1][1]["tail"] == 20

    # Inspect the messages passed to the LAST create() call: should contain tool entries.
    last_messages = client.calls[-1]["messages"]
    tool_msgs = [m for m in last_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 3  # one per data tool call from round 1


def test_recall_wired_into_system_prompt(settings: Settings) -> None:
    submit_args = {
        "summary": "s",
        "category": "c",
        "confidence": 0.5,
        "hypotheses": [{"title": "h", "rationale": "r", "instructions": "i"}],
    }
    client = FakeChat([make_response(tool_calls=[make_tool_call("t1", "submit_diagnosis", submit_args)])])
    engine = DiagnosisEngine(settings, client=client, recall=lambda f: ["seen before"])

    engine.diagnose(make_incident(), FakeFetcher())  # type: ignore[arg-type]

    first_messages = client.calls[0]["messages"]
    system = first_messages[0]
    assert system["role"] == "system"
    assert "seen before" in system["content"]


def test_cache_hit_returns_without_calling_client(settings: Settings) -> None:
    incident = make_incident()
    cache = DictCache()
    # Pre-populate cache with a diagnosis JSON for this incident's key.
    payload = {
        "summary": "cached summary",
        "category": "divergence",
        "confidence": 0.9,
        "hypotheses": [{"id": "hyp_xyz", "title": "t", "rationale": "r", "instructions": "i"}],
        "raw": {"model": "gpt-5.4"},
    }
    key = engine_cache_key(settings, incident)
    cache.store[key] = json.dumps(payload)

    engine = DiagnosisEngine(settings, client=RaisingChat(), cache=cache)
    diag = engine.diagnose(incident, FakeFetcher())  # type: ignore[arg-type]

    assert diag.summary == "cached summary"
    assert diag.confidence == 0.9
    assert len(diag.hypotheses) == 1
    assert diag.hypotheses[0].id == "hyp_xyz"


def test_cache_miss_then_set_with_roundtrippable_json(settings: Settings) -> None:
    submit_args = {
        "summary": "fresh",
        "category": "divergence",
        "confidence": 0.6,
        "hypotheses": [{"title": "h", "rationale": "r", "instructions": "i"}],
    }
    client = FakeChat([make_response(tool_calls=[make_tool_call("t1", "submit_diagnosis", submit_args)])])
    cache = DictCache()
    engine = DiagnosisEngine(settings, client=client, cache=cache)

    incident = make_incident()
    diag = engine.diagnose(incident, FakeFetcher())  # type: ignore[arg-type]

    assert len(cache.set_calls) == 1
    _stored_key, stored_value = cache.set_calls[0]
    # Round-trips back into a Diagnosis with matching fields.
    restored = _diagnosis_from_dict(json.loads(stored_value))
    assert restored.summary == diag.summary == "fresh"
    assert restored.category == "divergence"
    assert restored.confidence == pytest.approx(0.6)
    assert len(restored.hypotheses) == 1


def test_fallback_diagnosis_when_never_submitted(settings: Settings) -> None:
    # Client always returns plain content with no tool calls, for all 8 rounds.
    responses = [make_response(content="thinking...") for _ in range(8)]
    client = FakeChat(responses)
    engine = DiagnosisEngine(settings, client=client)
    incident = make_incident()

    diag = engine.diagnose(incident, FakeFetcher())  # type: ignore[arg-type]

    assert diag.confidence == 0.0
    assert diag.hypotheses == []
    assert diag.summary == incident.failure.message
    assert diag.category == str(incident.failure.kind)


def test_wandb_inference_model_selection() -> None:
    settings = Settings(
        use_wandb_inference=True,
        wandb_inference_model="openai/gpt-oss-120b",
        diagnosis_model="gpt-5.4",
        max_probes=3,
    )
    submit_args = {
        "summary": "s",
        "category": "c",
        "confidence": 0.5,
        "hypotheses": [{"title": "h", "rationale": "r", "instructions": "i"}],
    }
    client = FakeChat([make_response(tool_calls=[make_tool_call("t1", "submit_diagnosis", submit_args)])])
    engine = DiagnosisEngine(settings, client=client)

    engine.diagnose(make_incident(), FakeFetcher())  # type: ignore[arg-type]

    assert client.calls[0]["model"] == "openai/gpt-oss-120b"


# --------------------------------------------------------------------------- #
# Tiny shim so the cache test mirrors the engine's private key derivation.     #
# --------------------------------------------------------------------------- #
def engine_cache_key(settings: Settings, incident: Incident) -> str:
    eng = DiagnosisEngine(settings)
    return eng._cache_key(incident)
