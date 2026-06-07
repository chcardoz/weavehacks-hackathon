from __future__ import annotations


async def test_reply_null_when_absent(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.get("/v1/incidents/no-such/reply", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json() == {"reply": None}


async def test_reply_returned_when_present(client_app, auth_header):
    client, _app, redis = client_app
    await redis.set("reply:inc-3", "3")
    resp = await client.get("/v1/incidents/inc-3/reply", headers=auth_header)
    assert resp.status_code == 200
    assert resp.json() == {"reply": "3"}
