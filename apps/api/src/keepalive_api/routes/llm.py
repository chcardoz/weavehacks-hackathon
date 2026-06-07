from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_openai, get_redis, get_settings

logger = logging.getLogger("keepalive_api.llm")

router = APIRouter()

_MAX_BODY_BYTES = 2_000_000


async def _enforce_rate_limit(request: Request, key_id: str) -> None:
    settings = get_settings(request)
    redis = get_redis(request)
    window = int(time.time() // 60)
    bucket = f"llmrl:{key_id}:{window}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, 120)
    if count > settings.llm_rate_limit_per_min:
        raise HTTPException(status_code=429, detail="rate limit exceeded")


@router.post("/v1/llm/chat/completions")
async def chat_completions(request: Request, key_id: str = Depends(require_api_key)) -> Response:
    openai = get_openai(request)
    if openai is None:
        raise HTTPException(status_code=503, detail="llm proxy not configured")

    body = await request.body()
    if not body or len(body) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail=f"body must be 1..{_MAX_BODY_BYTES} bytes")

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="body must be valid JSON") from exc

    settings = get_settings(request)
    model = payload.get("model")
    if model not in settings.llm_allowed_models:
        raise HTTPException(status_code=400, detail=f"model not allowed: {model}")
    if payload.get("stream"):
        raise HTTPException(status_code=400, detail="streaming is not supported")

    await _enforce_rate_limit(request, key_id)

    resp = await openai.post("/chat/completions", json=payload)
    if resp.is_error:
        logger.warning("openai upstream error (%s): %s", resp.status_code, resp.text[:500])
    # NOTE: relay self-logging is intentionally SKIPPED here. The LLM proxy has no
    # project_id in context (no incident/project hint in the chat-completions body),
    # and the contract allows relay self-logs to be best-effort, so we omit the event.
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
