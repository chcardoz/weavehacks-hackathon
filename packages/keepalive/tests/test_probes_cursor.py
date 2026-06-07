from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from keepalive.config import Settings
from keepalive.probes.cursor import CursorClient, IntegrationNotConnectedError
from keepalive.types import FixHypothesis, ProbeSpec, ProbeState, RunContext


def _settings() -> Settings:
    return Settings(cursor_api_key="ck", cursor_api_url="https://api.cursor.com")


def _ctx() -> RunContext:
    return RunContext(
        run_id="run1",
        project="proj",
        entity="ent",
        run_url="https://wandb.ai/run1",
        commit_sha="abc123def",
        repo_url="https://github.com/me/repo",
        entrypoint=["python", "train.py"],
        checkpoint_dir="/ckpt",
    )


def _hyp() -> FixHypothesis:
    return FixHypothesis(
        id="hyp1",
        title="Lower the learning rate",
        rationale="LR too high causes divergence",
        instructions="Set lr=1e-4 in the optimizer config",
    )


def _client(handler: Any) -> CursorClient:
    http = httpx.Client(base_url="https://api.cursor.com/v1", transport=httpx.MockTransport(handler))
    c = CursorClient(_settings(), http=http)
    # Force the REST path: ensure no SDK is used even if installed in the env.
    c._sdk = None
    c._sdk_kind = None
    return c


def test_spawn_probe_builds_rest_body_and_sets_spec() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"id": "agent-1"})

    client = _client(handler)
    ctx = _ctx()
    hyp = _hyp()
    spec = client.spawn_probe(hyp, ctx, "inc1")

    body = captured["body"]
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/agents")

    # prompt.text contains hypothesis title + instructions
    text = body["prompt"]["text"]
    assert hyp.title in text
    assert hyp.instructions in text

    # v1 contract: repos[] with url + startingRef, autoCreatePR off
    assert body["repos"] == [{"url": ctx.repo_url, "startingRef": ctx.commit_sha}]
    assert body["autoCreatePR"] is False
    assert "source" not in body
    assert "target" not in body

    # NO agentId anywhere in body
    flat = json.dumps(body)
    assert "agentId" not in flat

    # response wiring; Cursor names the branch, so it stays unset until wait_for_branch
    assert spec.agent_id == "agent-1"
    assert spec.state == ProbeState.WRITING
    assert spec.branch is None
    assert spec.incident_id == "inc1"


def test_spawn_probe_parses_nested_agent_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"agent": {"id": "bc-42"}, "run": {"id": "run-1"}})

    client = _client(handler)
    spec = client.spawn_probe(_hyp(), _ctx(), "inc1")
    assert spec.agent_id == "bc-42"


@pytest.mark.parametrize("status", [403, 404])
def test_spawn_probe_unconnected_status_raises(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="integration not connected")

    client = _client(handler)
    with pytest.raises(IntegrationNotConnectedError):
        client.spawn_probe(_hyp(), _ctx(), "inc1")


def test_spawn_probe_400_body_mentions_integration_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="this repository is not connected to the integration")

    client = _client(handler)
    with pytest.raises(IntegrationNotConnectedError):
        client.spawn_probe(_hyp(), _ctx(), "inc1")


def test_wait_for_branch_running_then_finished_with_git_branches() -> None:
    responses = [
        httpx.Response(200, json={"status": "RUNNING"}),
        httpx.Response(
            200,
            json={
                "status": "FINISHED",
                "git": {"branches": [{"repoUrl": "github.com/me/repo", "branch": "cursor/probe-x"}]},
            },
        ),
    ]
    calls = {"i": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        resp = responses[calls["i"]]
        calls["i"] += 1
        return resp

    client = _client(handler)
    spec = ProbeSpec(id="p1", incident_id="inc1", hypothesis=_hyp(), agent_id="agent-1")
    out = client.wait_for_branch(spec, timeout_s=100.0, poll_s=1.0, sleep_fn=lambda s: sleeps.append(s))

    assert out.branch == "cursor/probe-x"
    assert out.state == ProbeState.READY
    assert sleeps == [1.0]  # one poll happened between RUNNING and FINISHED


def test_wait_for_branch_git_branches_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "RUNNING", "git": {"branches": ["b"]}})

    client = _client(handler)
    spec = ProbeSpec(id="p2", incident_id="inc1", hypothesis=_hyp(), agent_id="agent-1")
    out = client.wait_for_branch(spec, timeout_s=100.0, poll_s=1.0, sleep_fn=lambda s: None)
    assert out.branch == "b"
    assert out.state == ProbeState.READY


def test_wait_for_branch_legacy_name_key_still_parses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "RUNNING", "git": {"branches": [{"name": "cursor/legacy"}]}})

    client = _client(handler)
    spec = ProbeSpec(id="p6", incident_id="inc1", hypothesis=_hyp(), agent_id="agent-1")
    out = client.wait_for_branch(spec, timeout_s=100.0, poll_s=1.0, sleep_fn=lambda s: None)
    assert out.branch == "cursor/legacy"
    assert out.state == ProbeState.READY


def test_wait_for_branch_failed_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "FAILED"})

    client = _client(handler)
    spec = ProbeSpec(id="p3", incident_id="inc1", hypothesis=_hyp(), agent_id="agent-1")
    out = client.wait_for_branch(spec, timeout_s=100.0, poll_s=1.0, sleep_fn=lambda s: None)
    assert out.state == ProbeState.FAILED


def test_wait_for_branch_timeout() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "RUNNING"})

    client = _client(handler)
    spec = ProbeSpec(id="p4", incident_id="inc1", hypothesis=_hyp(), agent_id="agent-1")
    # timeout_s=0 => deadline already passed; one poll happens then FAILED.
    out = client.wait_for_branch(spec, timeout_s=0.0, poll_s=1.0, sleep_fn=lambda s: sleeps.append(s))
    assert out.state == ProbeState.FAILED
    assert sleeps == []  # no sleep; deadline reached before sleeping


def test_wait_for_branch_no_agent_id_fails_immediately() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - should not be hit
        raise AssertionError("HTTP should not be called when agent_id is None")

    client = _client(handler)
    spec = ProbeSpec(id="p5", incident_id="inc1", hypothesis=_hyp())
    out = client.wait_for_branch(spec, timeout_s=10.0, sleep_fn=lambda s: None)
    assert out.state == ProbeState.FAILED
