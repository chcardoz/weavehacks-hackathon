from __future__ import annotations

import hashlib

from fastapi import HTTPException, Request

from keepalive_api.deps import get_pg_pool, get_settings

_APIKEY_LOOKUP = "SELECT id FROM apikey WHERE key = $1 AND (enabled IS NULL OR enabled = true)"


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

    key_hash = hashlib.sha256(token.encode()).hexdigest()
    row = await pool.fetchrow(_APIKEY_LOOKUP, key_hash)
    if row is None:
        raise HTTPException(status_code=401, detail="invalid api key")
    return str(row["id"])
