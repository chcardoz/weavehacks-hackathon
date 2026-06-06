# keepalive infra runbooks

Concrete deploy steps for the weekend. No fluff. Pick the runbook for the service you're
standing up.

| Runbook | Service |
| ------- | ------- |
| [railway.md](./railway.md) | Relay (`apps/api`): FastAPI + Postgres + Redis |
| [vercel.md](./vercel.md) | Dashboard (`apps/dashboard`): Next.js + Neon |
| [mintlify.md](./mintlify.md) | Docs site (`docs/`) |
| [twilio.md](./twilio.md) | SMS send + inbound reply webhook |
| [cursor-onboarding.md](./cursor-onboarding.md) | Cursor cloud agents (probe code) |
| [redis.md](./redis.md) + [docker-compose.yml](./docker-compose.yml) | Local Redis + Agent Memory Server |
| [wandb-sandboxes.md](./wandb-sandboxes.md) | W&B Sandboxes (probe executor) |
| [pypi.md](./pypi.md) | Publish the `keepalive` library |

## Architecture recap (so you put secrets in the right place)

- **The library** runs on the user's GPU box. It needs almost every secret because it does
  the real work (detect, diagnose, probe, promote).
- **The relay** (`apps/api`, Railway) does SMS + key verification + voice-note hosting only.
- **The dashboard** (`apps/dashboard`, Vercel) issues keys.
- **Cursor cloud agents** only write code; they run on Cursor's VMs.

## Env var master table — which service needs which secret

| Secret | Library (GPU box) | Relay (Railway) | Dashboard (Vercel) | Agent Memory Server |
| ------ | :---: | :---: | :---: | :---: |
| `KEEPALIVE_API_KEY` (`ka_live_...`) | ✅ | — | issued here | — |
| `KEEPALIVE_API_URL` | ✅ (points at relay) | — | — | — |
| `KEEPALIVE_PHONE` | ✅ | — | — | — |
| `OPENAI_API_KEY` | ✅ (diagnosis + TTS) | — | — | ✅ (embeddings) |
| `CURSOR_API_KEY` (user key) | ✅ | — | — | — |
| `WANDB_API_KEY` | ✅ (metrics + sandboxes) | — | — | — |
| `REDIS_URL` | ✅ | ✅ (reply / phone map) | — | ✅ |
| `TWILIO_ACCOUNT_SID` | — | ✅ | — | — |
| `TWILIO_AUTH_TOKEN` | — | ✅ | — | — |
| `TWILIO_FROM_NUMBER` | — | ✅ | — | — |
| `PUBLIC_BASE_URL` | — | ✅ (signature validation) | — | — |
| `KEEPALIVE_DEV_KEYS` (fallback) | — | ✅ (optional) | — | — |
| `DATABASE_URL` (Neon) | — | ✅ (key lookup) | ✅ | — |
| `BETTER_AUTH_SECRET` | — | — | ✅ | — |
| `BETTER_AUTH_URL` | — | — | ✅ | — |

Optional W&B Inference (second model provider, library side):
`KEEPALIVE_USE_WANDB_INFERENCE`, `KEEPALIVE_WANDB_INFERENCE_URL`,
`KEEPALIVE_WANDB_INFERENCE_MODEL`. See the
[configuration reference](../docs/reference/configuration.mdx) for the full list and
defaults.
