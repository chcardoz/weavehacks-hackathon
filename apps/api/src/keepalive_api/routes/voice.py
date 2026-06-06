from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from keepalive_api.deps import get_redis

router = APIRouter()


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


@router.get("/a/{note_id}.mp3")
async def voice_note_audio(note_id: str, request: Request) -> Response:
    redis = get_redis(request)
    audio = await redis.get(f"audio:{note_id}")
    if audio is None:
        raise HTTPException(status_code=404, detail="voice note not found")
    return Response(content=audio, media_type="audio/mpeg")


@router.get("/a/{note_id}")
async def voice_note_page(note_id: str, request: Request) -> HTMLResponse:
    redis = get_redis(request)
    exists = await redis.exists(f"audio:{note_id}")
    if not exists:
        raise HTTPException(status_code=404, detail="voice note not found")
    return HTMLResponse(content=_player_html(note_id))
