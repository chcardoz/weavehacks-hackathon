from __future__ import annotations


async def test_no_auth_header_is_401(client_app):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "to_phone": "+15551230000"},
    )
    assert resp.status_code == 401


async def test_wrong_key_is_401(client_app):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "to_phone": "+15551230000"},
        headers={"Authorization": "Bearer ka_live_wrong"},
    )
    assert resp.status_code == 401


async def test_non_bearer_scheme_is_401(client_app):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "to_phone": "+15551230000"},
        headers={"Authorization": "Basic ka_live_test"},
    )
    assert resp.status_code == 401


async def test_dev_key_is_not_401(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "to_phone": "+15551230000"},
        headers=auth_header,
    )
    assert resp.status_code != 401
    assert resp.status_code == 200


async def test_reply_route_requires_auth(client_app):
    client, _app, _redis = client_app
    resp = await client.get("/v1/incidents/i1/reply")
    assert resp.status_code == 401
