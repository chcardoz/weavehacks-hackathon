from __future__ import annotations

import base64
import hashlib

from fastapi import HTTPException, Request

from keepalive_api.deps import get_pg_pool, get_settings

_APIKEY_LOOKUP = "SELECT id FROM apikey WHERE key = $1 AND (enabled IS NULL OR enabled = true)"


def hash_api_key(token: str) -> str:
    """sha256 → unpadded base64url, matching Better Auth's defaultKeyHasher."""
    digest = hashlib.sha256(token.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def require_api_key(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    settings = get_settings(request)
    if token in settings.dev_keys:
        return "dev"

    pool = get_pg_pool(request)
    if pool is None:
        raise HTTPException(status_code=401, detail="invalid api key")

    row = await pool.fetchrow(_APIKEY_LOOKUP, hash_api_key(token))
    if row is None:
        raise HTTPException(status_code=401, detail="invalid api key")
    return str(row["id"])
