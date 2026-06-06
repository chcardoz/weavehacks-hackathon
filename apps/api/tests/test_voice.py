from __future__ import annotations

from .conftest import make_settings

AUDIO = b"ID3fake-mp3-bytes-\x00\x01\x02"


async def test_upload_returns_absolute_url(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/voice-notes?incident_id=i1",
        content=AUDIO,
        headers=auth_header,
    )
    assert resp.status_code == 200
    url = resp.json()["url"]
    assert url.startswith("http://localhost:8000/a/")
    note_id = url.rsplit("/a/", 1)[1]
    assert note_id


async def test_upload_empty_body_is_400(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/voice-notes?incident_id=i1",
        content=b"",
        headers=auth_header,
    )
    assert resp.status_code == 400


async def test_upload_requires_auth(client_app):
    client, _app, _redis = client_app
    resp = await client.post("/v1/voice-notes?incident_id=i1", content=AUDIO)
    assert resp.status_code == 401


async def test_player_page_serves_html_with_audio_tag(client_app, auth_header):
    client, _app, _redis = client_app
    up = await client.post("/v1/voice-notes?incident_id=i1", content=AUDIO, headers=auth_header)
    note_id = up.json()["url"].rsplit("/a/", 1)[1]

    page = await client.get(f"/a/{note_id}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<audio" in page.text
    assert f"/a/{note_id}.mp3" in page.text


async def test_mp3_returns_bytes_with_audio_content_type(client_app, auth_header):
    client, _app, _redis = client_app
    up = await client.post("/v1/voice-notes?incident_id=i1", content=AUDIO, headers=auth_header)
    note_id = up.json()["url"].rsplit("/a/", 1)[1]

    mp3 = await client.get(f"/a/{note_id}.mp3")
    assert mp3.status_code == 200
    assert mp3.headers["content-type"] == "audio/mpeg"
    assert mp3.content == AUDIO


async def test_unknown_mp3_is_404(client_app):
    client, _app, _redis = client_app
    resp = await client.get("/a/does-not-exist.mp3")
    assert resp.status_code == 404


async def test_unknown_page_is_404(client_app):
    client, _app, _redis = client_app
    resp = await client.get("/a/does-not-exist")
    assert resp.status_code == 404


async def test_upload_respects_voice_note_ttl(auth_header):
    import fakeredis.aioredis

    from .conftest import build_client

    settings = make_settings(voice_note_ttl_s=1234)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=False)
    async with build_client(settings, fake_redis=redis) as (client, _app):
        up = await client.post("/v1/voice-notes?incident_id=i1", content=AUDIO, headers=auth_header)
        note_id = up.json()["url"].rsplit("/a/", 1)[1]
        ttl = await redis.ttl(f"audio:{note_id}")
        assert 0 < ttl <= 1234
