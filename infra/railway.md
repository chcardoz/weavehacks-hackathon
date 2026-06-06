# Railway — deploy the relay (`apps/api`)

The relay is FastAPI. Railway gives us FastAPI + Postgres + Redis one-click. It does only
SMS send, inbound reply webhook, key verification, and voice-note hosting.

## 1. Create the project + services

1. New Project → Deploy from GitHub repo → pick this repo.
2. Add **Postgres** (New → Database → PostgreSQL). Railway sets `DATABASE_URL`.
3. Add **Redis** (New → Database → Redis). Railway sets a Redis URL — copy it into
   `REDIS_URL` on the API service.

## 2. Configure the API service

- **Root directory:** `apps/api`
- **Install / build:** uv. Set the build to use uv, e.g.:
  ```bash
  uv sync --frozen
  ```
- **Start command:**
  ```bash
  uvicorn keepalive_api.main:app --host 0.0.0.0 --port $PORT
  ```
  (Railway injects `$PORT`; bind `0.0.0.0`.)

## 3. Environment variables (API service)

| Var | Value |
| --- | ----- |
| `DATABASE_URL` | from Railway Postgres (auto) |
| `REDIS_URL` | from Railway Redis |
| `TWILIO_ACCOUNT_SID` | from Twilio console |
| `TWILIO_AUTH_TOKEN` | from Twilio console |
| `TWILIO_FROM_NUMBER` | your purchased number (E.164) |
| `PUBLIC_BASE_URL` | the relay's public URL, e.g. `https://api.keepalive.club` — **must** match what Twilio calls (signature validation) |
| `KEEPALIVE_DEV_KEYS` | optional comma-separated dev keys fallback when Postgres has no `apikey` row |

The relay verifies `ka_live_` keys by sha256 lookup in the Postgres `apikey` table (the
Better Auth schema the dashboard writes to), with `KEEPALIVE_DEV_KEYS` as a fallback for
local / demo.

## 4. Custom domain

Service → Settings → Networking → Custom Domain → `api.keepalive.club`. Add the CNAME
Railway shows to your DNS. Once it resolves, set `PUBLIC_BASE_URL=https://api.keepalive.club`
and point Twilio's webhook at `https://api.keepalive.club/sms` (see `twilio.md`).

## 5. Smoke test

```bash
curl https://api.keepalive.club/healthz          # or the root route
curl -X POST https://api.keepalive.club/v1/notify \
  -H "Authorization: Bearer ka_live_..." \
  -H "Content-Type: application/json" \
  -d '{"incident_id":"inc_test","kind":"incident","message":"test","to_phone":"+1555..."}'
```

You should receive an SMS. Reply `1`/`2`/`3` and confirm
`GET /v1/incidents/inc_test/reply` returns it.

## Endpoints (reference)

- `POST /v1/notify` — `{incident_id, kind: incident|recap, message, voice_note_url?, trace_url?, to_phone}` → Twilio SMS; maps phone→incident in Redis (`active:{phone}`).
- `POST /sms` — Twilio inbound webhook (form). Validates `X-Twilio-Signature`. Body `1`/`2`/`3` → Redis `reply:{incident_id}`.
- `GET /v1/incidents/{id}/reply` → `{"reply": "1"|"2"|"3"|null}`.
- `POST /v1/voice-notes` — bytes + incident_id → Redis (TTL) → `{"url": "/a/{id}"}`.
- `GET /a/{id}` — HTML audio page. `GET /a/{id}.mp3` — `Content-Type: audio/mpeg`.
