from __future__ import annotations

from collections.abc import Callable

import fakeredis
import pytest

from keepalive.escalate.deadline import DeadlineClock
from keepalive.types import HumanReply


@pytest.fixture
def redis_client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


def test_arm_returns_deadline_and_sets_zscore(redis_client: fakeredis.FakeRedis) -> None:
    clock = DeadlineClock(redis_client)
    deadline = clock.arm("inc_1", timeout_s=100.0)

    stored = redis_client.zscore(clock.key, "inc_1")
    assert stored is not None
    assert float(stored) == pytest.approx(deadline)


def test_due_before_and_after_deadline(redis_client: fakeredis.FakeRedis) -> None:
    clock = DeadlineClock(redis_client)
    deadline = clock.arm("inc_1", timeout_s=100.0)

    # now well before deadline -> not due
    assert clock.due(now=deadline - 50) == []
    # now at/after deadline -> due
    assert clock.due(now=deadline + 1) == ["inc_1"]


def test_disarm_removes_member(redis_client: fakeredis.FakeRedis) -> None:
    clock = DeadlineClock(redis_client)
    deadline = clock.arm("inc_1", timeout_s=10.0)
    clock.disarm("inc_1")

    assert redis_client.zscore(clock.key, "inc_1") is None
    assert clock.due(now=deadline + 100) == []


def _clock_fns(start: float, step: float) -> tuple[Callable[[], float], Callable[[float], None]]:
    """now_fn reads a mutable cell; sleep_fn advances it by `step`."""
    state = {"t": start}

    def now_fn() -> float:
        return state["t"]

    def sleep_fn(_seconds: float) -> None:
        state["t"] += step

    return now_fn, sleep_fn


def test_await_human_returns_reply_on_third_poll(redis_client: fakeredis.FakeRedis) -> None:
    clock = DeadlineClock(redis_client)
    # Arm via direct zadd so deadline is far in the future relative to our clock.
    redis_client.zadd(clock.key, {"inc_1": 1000.0})

    poll_count = {"n": 0}

    def fetch_reply(incident_id: str) -> HumanReply | None:
        poll_count["n"] += 1
        if poll_count["n"] == 3:
            return HumanReply.APPLY_FIX
        return None

    now_fn, sleep_fn = _clock_fns(start=0.0, step=1.0)
    reply = clock.await_human("inc_1", fetch_reply, poll_interval=1.0, now_fn=now_fn, sleep_fn=sleep_fn)

    assert reply is HumanReply.APPLY_FIX
    assert poll_count["n"] == 3
    # disarmed after success
    assert redis_client.zscore(clock.key, "inc_1") is None


def test_await_human_returns_none_at_deadline(redis_client: fakeredis.FakeRedis) -> None:
    clock = DeadlineClock(redis_client)
    redis_client.zadd(clock.key, {"inc_1": 5.0})  # deadline at t=5

    def fetch_reply(incident_id: str) -> HumanReply | None:
        return None  # human never replies

    now_fn, sleep_fn = _clock_fns(start=0.0, step=1.0)
    reply = clock.await_human("inc_1", fetch_reply, poll_interval=1.0, now_fn=now_fn, sleep_fn=sleep_fn)

    assert reply is None
    # disarmed after timeout
    assert redis_client.zscore(clock.key, "inc_1") is None


def test_await_human_missing_deadline_returns_immediately(
    redis_client: fakeredis.FakeRedis,
) -> None:
    clock = DeadlineClock(redis_client)
    # Nothing armed for this incident.
    calls = {"n": 0}

    def fetch_reply(incident_id: str) -> HumanReply | None:
        calls["n"] += 1
        return None

    # When no zscore exists, deadline defaults to now_fn(); since the first
    # fetch yields None and now >= deadline, it returns None on the first pass.
    now_fn, sleep_fn = _clock_fns(start=100.0, step=1.0)
    reply = clock.await_human("inc_1", fetch_reply, poll_interval=1.0, now_fn=now_fn, sleep_fn=sleep_fn)

    assert reply is None
    assert calls["n"] == 1  # one fetch, then immediate timeout
