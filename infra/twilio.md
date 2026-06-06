# Twilio — SMS send + inbound reply webhook

The relay (`apps/api`) sends escalation SMS and receives `1`/`2`/`3` replies through
Twilio.

## ⚠️ PUT A CARD ON THE ACCOUNT BEFORE THE DEMO

A Twilio **trial** account:

- only sends SMS to **verified** numbers, and
- stamps every message with a "Sent from your Twilio trial account" prefix.

Both ruin the demo. Add a payment method (upgrade the account) before you go on stage. A
small balance is enough.

## 1. Buy / verify a number

1. Twilio Console → Phone Numbers → Buy a number with **SMS** capability (US local is fine).
2. On a trial account, also verify your personal phone (Verified Caller IDs) so it can
   receive the escalation SMS. After upgrading you can text any number.
3. Copy `Account SID`, `Auth Token`, and the purchased number (E.164) into the relay env:
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.

## 2. Point the messaging webhook at the relay

Twilio Console → your number → Messaging → "A message comes in":

- Method: **POST**
- URL: **`{PUBLIC_BASE_URL}/sms`** (e.g. `https://api.keepalive.club/sms`)

## 3. Signature validation — match the URL exactly

The relay validates the `X-Twilio-Signature` header on `POST /sms`. Twilio computes the
signature over the **exact URL it called**. The relay computes its expected signature using
`PUBLIC_BASE_URL`. These must be identical, or validation fails and replies are rejected.

So: whatever URL you put in the Twilio webhook, set `PUBLIC_BASE_URL` to the same origin.

## 4. Local development with ngrok

Twilio can't reach `localhost`, so tunnel:

```bash
ngrok http 8000
```

Then:

- Set the Twilio messaging webhook to `https://<id>.ngrok-free.app/sms`.
- Set `PUBLIC_BASE_URL=https://<id>.ngrok-free.app` on the relay (signature validation
  depends on this matching).
- Restart the relay so it picks up the new `PUBLIC_BASE_URL`.

The free ngrok URL changes each restart — update both the webhook and `PUBLIC_BASE_URL`
together each time.

## 5. Flow recap

1. Library → relay `POST /v1/notify` → Twilio sends SMS, maps `active:{phone}` → incident
   in Redis.
2. You reply `1`/`2`/`3` → Twilio → relay `POST /sms` → relay validates signature, writes
   `reply:{incident_id}` to Redis.
3. Library polls relay `GET /v1/incidents/{id}/reply` → gets your reply (or `null` until
   the deadline expires).
