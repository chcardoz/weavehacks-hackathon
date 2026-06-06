# Railway — deploy the relay (`apps/api`)

The relay is FastAPI. Railway gives us FastAPI + Postgres + Redis one-click. It does
Telegram send, inbound reply webhook, key verification, the `/v1/llm` diagnosis proxy
(fronts OpenAI with our key), and voice-note TTS + hosting.

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
| `TELEGRAM_BOT_TOKEN` | from @BotFather (see `telegram.md`) |
| `TELEGRAM_WEBHOOK_SECRET` | `openssl rand -hex 16`; same value passed to `setWebhook` |
| `PUBLIC_BASE_URL` | the relay's public URL, e.g. `https://api.keepalive.club` — used for voice-note URLs (Telegram fetches the mp3 from here) |
| `OPENAI_API_KEY` | **our** OpenAI key — powers the `/v1/llm` diagnosis proxy and voice-note TTS; users never supply one |
| `KEEPALIVE_LLM_MODELS` | optional allow-list for the proxy, default `gpt-5.4,gpt-5.4-mini` |
| `KEEPALIVE_LLM_RATE_LIMIT_PER_MIN` | optional per-key proxy rate limit, default `30` |
| `KEEPALIVE_TTS_MODEL` / `KEEPALIVE_TTS_VOICE` | optional, default `gpt-4o-mini-tts` / `alloy` |
| `KEEPALIVE_DEV_KEYS` | optional comma-separated dev keys fallback when Postgres has no `apikey` row |

The relay verifies `ka_live_` keys by sha256 lookup in the Postgres `apikey` table (the
Better Auth schema the dashboard writes to), with `KEEPALIVE_DEV_KEYS` as a fallback for
local / demo.

## 4. Custom domain

Service → Settings → Networking → Custom Domain → `api.keepalive.club`. Add the CNAME
Railway shows to your DNS. Once it resolves, set `PUBLIC_BASE_URL=https://api.keepalive.club`
and point the Telegram webhook at `https://api.keepalive.club/telegram` (see `telegram.md`).

## 5. Smoke test

```bash
curl https://api.keepalive.club/healthz          # or the root route
curl -X POST https://api.keepalive.club/v1/notify \
  -H "Authorization: Bearer ka_live_..." \
  -H "Content-Type: application/json" \
  -d '{"incident_id":"inc_test","kind":"incident","message":"test","chat_id":"<your chat id>"}'
```

You should receive a Telegram message with buttons. Tap one (or type `1`/`2`/`3`) and
confirm `GET /v1/incidents/inc_test/reply` returns it.

## Endpoints (reference)

- `POST /v1/notify` — `{incident_id, kind: incident|recap, message, voice_script?, trace_url?, chat_id}` → Telegram message with inline buttons; if `voice_script` present, the relay runs OpenAI TTS, stores the mp3 (`audio:{id}`, TTL), and sends the voice bubble — best-effort. Maps chat→incident in Redis (`active:{chat_id}`).
- `POST /v1/llm/chat/completions` — OpenAI-compatible diagnosis proxy. Bearer = `ka_live_` key. Model allow-list, no streaming, 2MB cap, per-key rate limit (429), 503 if `OPENAI_API_KEY` unset.
- `POST /telegram` — Telegram webhook (JSON update). Validates `X-Telegram-Bot-Api-Secret-Token`. Button tap (`{incident_id}:{choice}`) or typed `1`/`2`/`3` → Redis `reply:{incident_id}`.
- `GET /v1/incidents/{id}/reply` → `{"reply": "1"|"2"|"3"|null}`.
- `GET /a/{id}` — HTML audio page. `GET /a/{id}.mp3` — `Content-Type: audio/mpeg`.
