from __future__ import annotations

import httpx

from .conftest import FakeOpenAI, build_client, make_settings


def _payload(model: str = "gpt-5.4") -> dict[str, object]:
    return {"model": model, "messages": [{"role": "user", "content": "diagnose this"}]}


async def test_proxy_forwards_to_openai(auth_header: dict[str, str]) -> None:
    fake = FakeOpenAI()
    async with build_client(openai=fake) as (client, _):
        resp = await client.post("/v1/llm/chat/completions", json=_payload(), headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["id"] == "chatcmpl-test"
    assert fake.calls_to("/chat/completions") == [_payload()]


async def test_proxy_requires_api_key() -> None:
    async with build_client(openai=FakeOpenAI()) as (client, _):
        resp = await client.post("/v1/llm/chat/completions", json=_payload())
    assert resp.status_code == 401


async def test_proxy_503_when_not_configured(auth_header: dict[str, str]) -> None:
    async with build_client() as (client, _):
        resp = await client.post("/v1/llm/chat/completions", json=_payload(), headers=auth_header)
    assert resp.status_code == 503


async def test_proxy_rejects_disallowed_model(auth_header: dict[str, str]) -> None:
    fake = FakeOpenAI()
    async with build_client(openai=fake) as (client, _):
        resp = await client.post("/v1/llm/chat/completions", json=_payload("gpt-3.5-turbo"), headers=auth_header)
    assert resp.status_code == 400
    assert fake.calls == []


async def test_proxy_rejects_streaming(auth_header: dict[str, str]) -> None:
    body = {**_payload(), "stream": True}
    async with build_client(openai=FakeOpenAI()) as (client, _):
        resp = await client.post("/v1/llm/chat/completions", json=body, headers=auth_header)
    assert resp.status_code == 400


async def test_proxy_rejects_invalid_json(auth_header: dict[str, str]) -> None:
    async with build_client(openai=FakeOpenAI()) as (client, _):
        resp = await client.post(
            "/v1/llm/chat/completions",
            content=b"not json",
            headers={**auth_header, "Content-Type": "application/json"},
        )
    assert resp.status_code == 400


async def test_proxy_rate_limit(auth_header: dict[str, str]) -> None:
    settings = make_settings(llm_rate_limit_per_min=2)
    async with build_client(settings, openai=FakeOpenAI()) as (client, _):
        codes = []
        for _i in range(3):
            resp = await client.post("/v1/llm/chat/completions", json=_payload(), headers=auth_header)
            codes.append(resp.status_code)
    assert codes == [200, 200, 429]


async def test_proxy_passes_through_upstream_errors(auth_header: dict[str, str]) -> None:
    upstream = httpx.Response(
        400,
        json={"error": {"message": "bad request"}},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    fake = FakeOpenAI(responses={"/chat/completions": upstream})
    async with build_client(openai=fake) as (client, _):
        resp = await client.post("/v1/llm/chat/completions", json=_payload(), headers=auth_header)
    assert resp.status_code == 400
    assert resp.json()["error"]["message"] == "bad request"


async def test_custom_model_allow_list(auth_header: dict[str, str]) -> None:
    settings = make_settings(llm_allowed_models=frozenset({"gpt-5.4-mini"}))
    async with build_client(settings, openai=FakeOpenAI()) as (client, _):
        ok = await client.post("/v1/llm/chat/completions", json=_payload("gpt-5.4-mini"), headers=auth_header)
        blocked = await client.post("/v1/llm/chat/completions", json=_payload("gpt-5.4"), headers=auth_header)
    assert ok.status_code == 200
    assert blocked.status_code == 400
