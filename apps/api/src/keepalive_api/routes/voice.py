from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from keepalive_api.auth import require_api_key
from keepalive_api.deps import get_redis, get_settings
from keepalive_api.models import VoiceNoteResponse

router = APIRouter()

_MAX_AUDIO_BYTES = 5_000_000


@router.post("/v1/voice-notes")
async def upload_voice_note(
    incident_id: str,
    request: Request,
    _: str = Depends(require_api_key),
) -> VoiceNoteResponse:
    body = await request.body()
    if not body or len(body) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="audio must be 1..5_000_000 bytes")

    settings = get_settings(request)
    redis = get_redis(request)
    note_id = secrets.token_urlsafe(8)
    await redis.set(f"audio:{note_id}", body, ex=settings.voice_note_ttl_s)
    return VoiceNoteResponse(url=f"{settings.public_base_url}/a/{note_id}")


def _player_html(note_id: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>keepalive</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 1.5rem;
    background: #0a0a0b; color: #e7e7ea;
    font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
  }}
  .wordmark {{ font-size: 0.9rem; letter-spacing: 0.3em; text-transform: uppercase; color: #6ee7b7; }}
  h1 {{ font-size: 1.6rem; font-weight: 600; margin: 0; text-align: center; max-width: 30rem; }}
  audio {{ width: min(90vw, 28rem); }}
</style>
</head>
<body>
  <div class="wordmark">keepalive</div>
  <h1>Your training run needs you.</h1>
  <audio controls autoplay src="/a/{note_id}.mp3"></audio>
</body>
</html>"""


@router.get("/a/{note_id}")
async def voice_note_page(note_id: str, request: Request) -> HTMLResponse:
    redis = get_redis(request)
    exists = await redis.exists(f"audio:{note_id}")
    if not exists:
        raise HTTPException(status_code=404, detail="voice note not found")
    return HTMLResponse(content=_player_html(note_id))


@router.get("/a/{note_id}.mp3")
async def voice_note_audio(note_id: str, request: Request) -> Response:
    redis = get_redis(request)
    audio = await redis.get(f"audio:{note_id}")
    if audio is None:
        raise HTTPException(status_code=404, detail="voice note not found")
    return Response(content=audio, media_type="audio/mpeg")
