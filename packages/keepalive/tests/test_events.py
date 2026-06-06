from __future__ import annotations

import fakeredis
import pytest

from keepalive.events import EventBus


@pytest.fixture
def bus() -> EventBus:
    client = fakeredis.FakeRedis(decode_responses=False)
    return EventBus(client, stream="test:events", group="test")


def test_publish_returns_id_and_entry_exists(bus: EventBus) -> None:
    entry_id = bus.publish("failure", {"kind": "nan_loss", "step": 5})
    assert entry_id
    assert bus.redis.xlen(bus.stream) == 1


def test_ensure_group_then_consume_merges_type(bus: EventBus) -> None:
    bus.publish("failure", {"kind": "nan_loss", "step": 5})
    bus.ensure_group()
    out = bus.consume(block_ms=0)
    assert len(out) == 1
    entry_id, payload = out[0]
    assert isinstance(entry_id, str)
    assert payload["type"] == "failure"
    assert payload["kind"] == "nan_loss"
    assert payload["step"] == 5


def test_ack(bus: EventBus) -> None:
    bus.publish("failure", {"step": 1})
    bus.ensure_group()
    out = bus.consume(block_ms=0)
    entry_id = out[0][0]
    bus.ack(entry_id)
    again = bus.consume(block_ms=0)
    assert again == []


def test_ensure_group_twice_does_not_raise(bus: EventBus) -> None:
    bus.ensure_group()
    bus.ensure_group()
