from __future__ import annotations

AUDIO = b"ID3fake-mp3-bytes-\x00\x01\x02"


async def seed_note(redis, note_id: str = "abc123") -> str:
    await redis.set(f"audio:{note_id}", AUDIO, ex=86400)
    return note_id


async def test_player_page_serves_html_with_audio_tag(client_app):
    client, _app, redis = client_app
    note_id = await seed_note(redis)

    page = await client.get(f"/a/{note_id}")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<audio" in page.text
    assert f"/a/{note_id}.mp3" in page.text


async def test_mp3_returns_bytes_with_audio_content_type(client_app):
    client, _app, redis = client_app
    note_id = await seed_note(redis)

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


async def test_upload_route_is_gone(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.post("/v1/voice-notes?incident_id=i1", content=AUDIO, headers=auth_header)
    assert resp.status_code in (404, 405)
