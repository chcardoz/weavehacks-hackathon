from __future__ import annotations

import json
from typing import Any

import httpx

from keepalive.config import Settings
from keepalive.escalate.client import EscalationClient
from keepalive.types import (
    Diagnosis,
    FailureEvent,
    FailureKind,
    HumanReply,
    Incident,
    RunContext,
)


def make_settings(**over: Any) -> Settings:
    base = {
        "api_key": "ka_live_test",
        "api_url": "https://api.test",
        "telegram_chat_id": "123456789",
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def make_incident(with_diagnosis: bool = False) -> Incident:
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
    failure = FailureEvent(kind=FailureKind.OOM, step=400, message="CUDA OOM")
    inc = Incident(id="inc_1", run=run, failure=failure)
    inc.trace_url = "https://weave.example/trace/1"
    if with_diagnosis:
        inc.diagnosis = Diagnosis(summary="ran out of vram", category="oom", confidence=0.8, hypotheses=[])
    return inc


def make_client(handler: Any, settings: Settings | None = None) -> tuple[EscalationClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    transport = httpx.MockTransport(wrapped)
    s = settings or make_settings()
    http = httpx.Client(base_url=s.api_url, transport=transport)
    return EscalationClient(s, http=http), captured


def test_notify_incident_posts_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client, captured = make_client(handler)
    client.notify_incident(make_incident(), voice_note_url="https://audio/x.mp3")

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/v1/notify"
    body = json.loads(req.content)
    assert body["incident_id"] == "inc_1"
    assert body["kind"] == "incident"
    assert body["chat_id"] == "123456789"
    assert body["voice_note_url"] == "https://audio/x.mp3"
    assert body["trace_url"] == "https://weave.example/trace/1"
    msg = body["message"]
    assert "oom" in msg  # failure kind present
    assert "1" in msg and "2" in msg and "3" in msg  # reply options


def test_fetch_reply_apply_fix() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": "2"})

    client, _ = make_client(handler)
    assert client.fetch_reply("inc_1") is HumanReply.APPLY_FIX


def test_fetch_reply_null_reply_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": None})

    client, _ = make_client(handler)
    assert client.fetch_reply("inc_1") is None


def test_fetch_reply_http_500_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client, _ = make_client(handler)
    assert client.fetch_reply("inc_1") is None


def test_fetch_reply_transport_error_returns_none() -> None:
    # Source wraps everything in a bare `except Exception`, so transport
    # errors are also swallowed and yield None.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    client, _ = make_client(handler)
    assert client.fetch_reply("inc_1") is None


def test_send_recap_posts_recap_kind() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client, captured = make_client(handler)
    client.send_recap(make_incident(), "all fixed, winner promoted")

    body = json.loads(captured[0].content)
    assert captured[0].url.path == "/v1/notify"
    assert body["kind"] == "recap"
    assert body["message"] == "all fixed, winner promoted"


def test_upload_voice_note_absolute_url_passthrough() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": "https://cdn.example/a.mp3"})

    client, captured = make_client(handler)
    url = client.upload_voice_note("inc_1", b"\x00\x01mp3bytes")

    assert url == "https://cdn.example/a.mp3"
    req = captured[0]
    assert req.url.path == "/v1/voice-notes"
    assert req.headers["Content-Type"] == "audio/mpeg"
    assert req.content == b"\x00\x01mp3bytes"
    assert req.url.params["incident_id"] == "inc_1"


def test_upload_voice_note_relative_url_joined() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": "/a/x.mp3"})

    settings = make_settings(api_url="https://api.test")
    client, _ = make_client(handler, settings=settings)
    url = client.upload_voice_note("inc_1", b"bytes")

    assert url == "https://api.test/a/x.mp3"
