from __future__ import annotations

from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, Response
from twilio.request_validator import RequestValidator

from keepalive_api.deps import get_redis, get_settings

router = APIRouter()

_ACTION_REPLIES = {
    "1": "rolling back to the last good checkpoint.",
    "2": "applying the fix.",
    "3": "stopping the run.",
}
_HELP_TEXT = "Reply 1 to roll back, 2 to apply the fix, or 3 to stop the run."


def _twiml(message: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(message)}</Message></Response>'


@router.post("/sms")
async def inbound_sms(request: Request) -> Response:
    settings = get_settings(request)
    redis = get_redis(request)

    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    from_number = params.get("From", "")
    raw_body = params.get("Body", "")

    if settings.twilio_auth_token:
        validator = RequestValidator(settings.twilio_auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = f"{settings.public_base_url}/sms"
        if not validator.validate(url, params, signature):
            raise HTTPException(status_code=403, detail="invalid twilio signature")

    body = raw_body.strip()

    if body in _ACTION_REPLIES:
        incident_id_raw = await redis.get(f"active:{from_number}")
        if incident_id_raw is None:
            return Response(content=_twiml("No active incident."), media_type="application/xml")
        incident_id = incident_id_raw.decode() if isinstance(incident_id_raw, bytes) else str(incident_id_raw)
        await redis.set(f"reply:{incident_id}", body, ex=86400)
        return Response(content=_twiml(f"Got it — {_ACTION_REPLIES[body]}"), media_type="application/xml")

    return Response(content=_twiml(_HELP_TEXT), media_type="application/xml")
