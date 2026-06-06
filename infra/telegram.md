# Telegram — escalation messages + inline-button replies

The relay (`apps/api`) sends escalation messages and receives replies through one Telegram
bot. This replaced Twilio SMS: no carrier filtering, no number verification, voice notes
play inline as voice bubbles, and replies are buttons instead of typed codes.

## 1. Create the bot (~2 min)

1. Message **@BotFather** → `/newbot` → pick a name + username (e.g. `keepalive_bot`).
2. Copy the token (`<bot_id>:<secret>`) into the relay env: `TELEGRAM_BOT_TOKEN`.
3. Generate a webhook secret: `openssl rand -hex 16` → `TELEGRAM_WEBHOOK_SECRET`.

## 2. Point the webhook at the relay

Telegram requires HTTPS on port 443/80/88/8443 — Railway's public domain qualifies.

```bash
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=https://api.keepalive.club/telegram" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET" \
  --data-urlencode 'allowed_updates=["message","callback_query"]'

# verify
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
```

Telegram echoes the secret in the `X-Telegram-Bot-Api-Secret-Token` header on every
delivery; the relay rejects requests where it doesn't match. (No HMAC signature dance —
this replaced Twilio's `X-Twilio-Signature` validation.)

Note: webhook and `getUpdates` long-polling are mutually exclusive. If you poll with
`getUpdates` while debugging, delete the webhook first (`/deleteWebhook`) and re-set it
after.

## 3. User onboarding — getting a chat id

A bot **cannot** message someone who never started it. Each user must:

1. Open `https://t.me/<bot_username>` and press **Start**.
2. The bot replies with their chat id and the exact line to export:
   `KEEPALIVE_TELEGRAM_CHAT_ID=<id>`.

That's the entire onboarding — it replaced phone-number purchase + verification.

## 4. Incident flow recap

1. Library → relay `POST /v1/notify` `{..., chat_id}` → relay sends the Telegram message
   with inline buttons (⏪ Roll back / 🔧 Apply fix / 🛑 Stop + 🧵 View trace) and the AI
   voice note as a voice bubble (`sendVoice` fetches the relay's public mp3 URL). Maps
   `active:{chat_id}` → incident in Redis.
2. User taps a button → Telegram → relay `POST /telegram` → callback_data
   (`{incident_id}:{choice}`) → Redis `reply:{incident_id}`. Typing `1`/`2`/`3` also works
   (uses the `active:{chat_id}` mapping).
3. Library polls relay `GET /v1/incidents/{id}/reply` → gets the reply (or `null` until
   the deadline expires).

## 5. Testing the webhook WITHOUT a phone

Replay what Telegram would POST, with the secret header — that's it:

```bash
# a button tap ("apply fix" on incident inc_test)
curl -s -X POST https://api.keepalive.club/telegram \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: $TELEGRAM_WEBHOOK_SECRET" \
  -d '{"update_id":1,"callback_query":{"id":"cb1","from":{"id":111,"is_bot":false,"first_name":"T"},
       "message":{"message_id":1,"chat":{"id":111,"type":"private"},"text":"x"},
       "chat_instance":"-1","data":"inc_test:2"}}'

# confirm the relay recorded it
curl https://api.keepalive.club/v1/incidents/inc_test/reply   # -> {"reply":"2"}
```

(The replayed `answerCallbackQuery` will 400 on Telegram's side for a fake callback id —
the relay logs and ignores that; the reply still lands in Redis.)

## 6. Gotchas

- **Always answer callback queries** — the relay does (`answerCallbackQuery`), otherwise
  the user's client spins. Don't remove that call.
- Rate limits: ~1 message/sec per chat, bursts → 429 with `retry_after`. One incident =
  two sends (message + voice); a non-issue.
- Message text cap 4096 chars; `callback_data` cap 64 bytes (`{incident_id}:{choice}` fits).
- We send plain text (no `parse_mode`) — nothing to escape, diagnosis text can't break it.
- The voice note is sent **by URL** — `PUBLIC_BASE_URL` must be publicly reachable or the
  voice bubble silently doesn't arrive (the text message still does).
