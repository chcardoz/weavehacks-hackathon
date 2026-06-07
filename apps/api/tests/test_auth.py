from __future__ import annotations

from keepalive_api.auth import hash_api_key


def test_hash_matches_better_auth_default_key_hasher():
    # Reference produced by @better-auth/api-key's defaultKeyHasher:
    # sha256 over the raw key, base64url-encoded with padding stripped.
    assert hash_api_key("ka_live_test123") == "ux6yJWUKm9_kuG33qXfNOnmkzbtexaSXql2nH5Swv3k"


def test_hash_is_urlsafe_and_unpadded():
    digest = hash_api_key("ka_live_" + "x" * 43)
    assert "=" not in digest
    assert "+" not in digest
    assert "/" not in digest


async def test_no_auth_header_is_401(client_app):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "chat_id": "123456789"},
    )
    assert resp.status_code == 401


async def test_wrong_key_is_401(client_app):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "chat_id": "123456789"},
        headers={"Authorization": "Bearer ka_live_wrong"},
    )
    assert resp.status_code == 401


async def test_non_bearer_scheme_is_401(client_app):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "chat_id": "123456789"},
        headers={"Authorization": "Basic ka_live_test"},
    )
    assert resp.status_code == 401


async def test_dev_key_is_not_401(client_app, auth_header):
    client, _app, _redis = client_app
    resp = await client.post(
        "/v1/notify",
        json={"incident_id": "i1", "message": "hi", "chat_id": "123456789"},
        headers=auth_header,
    )
    assert resp.status_code != 401
    assert resp.status_code == 200


async def test_reply_route_requires_auth(client_app):
    client, _app, _redis = client_app
    resp = await client.get("/v1/incidents/i1/reply")
    assert resp.status_code == 401
