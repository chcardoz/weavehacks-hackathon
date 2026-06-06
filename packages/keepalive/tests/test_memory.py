from __future__ import annotations

import importlib.util
import types as _types
from typing import Any

import pytest

from keepalive.config import Settings
from keepalive.memory.cache import DiagnosisCache
from keepalive.memory.incidents import IncidentMemory, _extract_texts
from keepalive.memory.router import SignalRouter
from keepalive.types import (
    Diagnosis,
    FailureEvent,
    FailureKind,
    Incident,
    RunContext,
)

_HAS_AGENT_MEMORY = importlib.util.find_spec("agent_memory_client") is not None


def make_incident() -> Incident:
    run = RunContext(
        run_id="run123",
        project="proj",
        entity="team",
        run_url="https://wandb.ai/team/proj/run123",
        commit_sha="abc",
        repo_url="https://github.com/x/y",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
    )
    failure = FailureEvent(kind=FailureKind.NAN_LOSS, step=400, message="loss NaN")
    inc = Incident(id="inc_1", run=run, failure=failure)
    inc.diagnosis = Diagnosis(summary="lr spike", category="divergence", confidence=0.6, hypotheses=[])
    return inc


# --------------------------------------------------------------------------- #
# IncidentMemory                                                                #
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(_HAS_AGENT_MEMORY, reason="agent_memory_client installed; no-op path not exercised")
def test_incident_memory_unavailable_is_safe_noop() -> None:
    mem = IncidentMemory(Settings(), client=None)
    assert mem.available is False
    # No exceptions, recall returns empty list.
    assert mem.recall(make_incident().failure) == []
    mem.remember(make_incident(), "rolled back")  # must not raise


class FakeMemoryResult:
    def __init__(self, texts: list[str]) -> None:
        self.memories = [_types.SimpleNamespace(text=t) for t in texts]


class FakeAsyncMemoryClient:
    def __init__(self, search_texts: list[str] | None = None, raise_on: set[str] | None = None) -> None:
        self.search_texts = search_texts or []
        self.raise_on = raise_on or set()
        self.created_records: list[Any] = []
        self.search_queries: list[str] = []

    async def create_long_term_memory(self, records: Any) -> None:
        if "create" in self.raise_on:
            raise RuntimeError("create boom")
        self.created_records.append(records)

    async def search_long_term_memory(self, text: str, limit: int = 3) -> Any:
        self.search_queries.append(text)
        if "search" in self.raise_on:
            raise RuntimeError("search boom")
        return FakeMemoryResult(self.search_texts)


def test_incident_memory_available_when_injected() -> None:
    mem = IncidentMemory(Settings(), client=FakeAsyncMemoryClient())
    assert mem.available is True


def test_remember_builds_text_with_kind_and_resolution() -> None:
    fake = FakeAsyncMemoryClient()
    mem = IncidentMemory(Settings(), client=fake)
    mem.remember(make_incident(), "rolled back to checkpoint")

    assert len(fake.created_records) == 1
    records = fake.created_records[0]
    text = records[0]["text"]
    assert "nan_loss" in text  # failure kind
    assert "rolled back to checkpoint" in text  # resolution
    assert "lr spike" in text  # diagnosis summary


def test_recall_extracts_texts_from_search_result() -> None:
    fake = FakeAsyncMemoryClient(search_texts=["seen this NaN before", "and again"])
    mem = IncidentMemory(Settings(), client=fake)

    out = mem.recall(make_incident().failure)

    assert out == ["seen this NaN before", "and again"]
    assert fake.search_queries  # query was issued
    assert "nan_loss" in fake.search_queries[0]


def test_recall_swallows_errors_returns_empty() -> None:
    fake = FakeAsyncMemoryClient(raise_on={"search"})
    mem = IncidentMemory(Settings(), client=fake)
    assert mem.recall(make_incident().failure) == []


def test_remember_swallows_errors() -> None:
    fake = FakeAsyncMemoryClient(raise_on={"create"})
    mem = IncidentMemory(Settings(), client=fake)
    # Must not raise.
    mem.remember(make_incident(), "applied fix")


def test_extract_texts_handles_dict_and_object_shapes() -> None:
    obj_result = _types.SimpleNamespace(memories=[_types.SimpleNamespace(text="a"), {"text": "b"}])
    assert _extract_texts(obj_result) == ["a", "b"]

    dict_result = {"memories": [{"text": "c"}]}
    assert _extract_texts(dict_result) == ["c"]

    list_result = [{"text": "d"}, _types.SimpleNamespace(text="e")]
    assert _extract_texts(list_result) == ["d", "e"]


# --------------------------------------------------------------------------- #
# SignalRouter                                                                  #
# --------------------------------------------------------------------------- #
class FakeRouter:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(self, text: str) -> Any:
        self.calls.append(text)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_signal_router_classify_returns_name() -> None:
    router = FakeRouter(_types.SimpleNamespace(name="oom"))
    sr = SignalRouter("redis://bogus:6379/0", router=router)
    assert sr.classify("CUDA out of memory") == "oom"


def test_signal_router_none_match_returns_none() -> None:
    router = FakeRouter(None)
    sr = SignalRouter("redis://bogus:6379/0", router=router)
    assert sr.classify("whatever") is None


def test_signal_router_empty_name_returns_none() -> None:
    router = FakeRouter(_types.SimpleNamespace(name=None))
    sr = SignalRouter("redis://bogus:6379/0", router=router)
    assert sr.classify("whatever") is None


def test_signal_router_raising_returns_none() -> None:
    router = FakeRouter(RuntimeError("boom"))
    sr = SignalRouter("redis://bogus:6379/0", router=router)
    assert sr.classify("whatever") is None


def test_signal_router_bogus_redis_no_injected_is_graceful() -> None:
    # Construction is lazy (router only built inside _router()), and a bogus
    # redis_url / missing redisvl falls into the except branch -> None.
    sr = SignalRouter("redis://nonexistent-host-12345:6379/0")
    assert sr.classify("CUDA out of memory") is None


# --------------------------------------------------------------------------- #
# DiagnosisCache                                                                #
# --------------------------------------------------------------------------- #
class FakeSemanticCache:
    def __init__(self, hits: list[dict[str, Any]] | None = None, raise_on: set[str] | None = None) -> None:
        self.hits = hits or []
        self.raise_on = raise_on or set()
        self.stored: list[tuple[str, str]] = []

    def check(self, prompt: str) -> list[dict[str, Any]]:
        if "check" in self.raise_on:
            raise RuntimeError("check boom")
        return self.hits

    def store(self, prompt: str, response: str) -> None:
        if "store" in self.raise_on:
            raise RuntimeError("store boom")
        self.stored.append((prompt, response))


def test_diagnosis_cache_get_returns_stored_response() -> None:
    fake = FakeSemanticCache(hits=[{"response": "cached-diagnosis"}])
    dc = DiagnosisCache("redis://bogus:6379/0", cache=fake)
    assert dc.get("some prompt") == "cached-diagnosis"


def test_diagnosis_cache_get_miss_returns_none() -> None:
    fake = FakeSemanticCache(hits=[])
    dc = DiagnosisCache("redis://bogus:6379/0", cache=fake)
    assert dc.get("some prompt") is None


def test_diagnosis_cache_set_stores() -> None:
    fake = FakeSemanticCache()
    dc = DiagnosisCache("redis://bogus:6379/0", cache=fake)
    dc.set("prompt", "response")
    assert fake.stored == [("prompt", "response")]


def test_diagnosis_cache_get_swallows_errors() -> None:
    fake = FakeSemanticCache(raise_on={"check"})
    dc = DiagnosisCache("redis://bogus:6379/0", cache=fake)
    assert dc.get("prompt") is None


def test_diagnosis_cache_set_swallows_errors() -> None:
    fake = FakeSemanticCache(raise_on={"store"})
    dc = DiagnosisCache("redis://bogus:6379/0", cache=fake)
    # Must not raise.
    dc.set("prompt", "response")
