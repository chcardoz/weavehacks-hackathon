# keepalive infra runbooks

Concrete deploy steps for the weekend. No fluff. Pick the runbook for the service you're
standing up.

| Runbook | Service |
| ------- | ------- |
| [railway.md](./railway.md) | Relay (`apps/api`): FastAPI + Postgres + Redis |
| [vercel.md](./vercel.md) | Dashboard (`apps/dashboard`): Next.js + Neon |
| [mintlify.md](./mintlify.md) | Docs site (`docs/`) |
| [telegram.md](./telegram.md) | Escalation messages + inline-button replies |
| [cursor-onboarding.md](./cursor-onboarding.md) | Cursor cloud agents (probe code) |
| [redis.md](./redis.md) | Redis 8 + Agent Memory Server on Railway |
| [wandb-sandboxes.md](./wandb-sandboxes.md) | W&B Sandboxes (probe executor) |
| [pypi.md](./pypi.md) | Publish the `keepalive` library |
| [cloud-testing.md](./cloud-testing.md) | **End-to-end cloud test plan** — run this top to bottom |

## Architecture recap (so you put secrets in the right place)

- **The library** runs on the user's GPU box. End users supply only their `ka_live_` key,
  Telegram chat id, `WANDB_API_KEY`, and `CURSOR_API_KEY` — the relay fronts OpenAI for
  them (diagnosis proxy + TTS), and Redis is opt-in.
- **The relay** (`apps/api`, Railway) does Telegram, key verification, the `/v1/llm`
  diagnosis proxy, voice-note TTS + hosting.
- **The dashboard** (`apps/dashboard`, Vercel) issues keys.
- **Cursor cloud agents** only write code; they run on Cursor's VMs.

## Env var master table — which service needs which secret

| Secret | Library (GPU box) | Relay (Railway) | Dashboard (Vercel) | Agent Memory Server |
| ------ | :---: | :---: | :---: | :---: |
| `KEEPALIVE_API_KEY` (`ka_live_...`) | ✅ | — | issued here | — |
| `KEEPALIVE_API_URL` | ✅ (points at relay) | — | — | — |
| `KEEPALIVE_TELEGRAM_CHAT_ID` | ✅ | — | — | — |
| `WANDB_API_KEY` | ✅ (metrics + sandboxes) | — | — | — |
| `CURSOR_API_KEY` (user key) | ✅ | — | — | — |
| `OPENAI_API_KEY` | optional (direct GPT-5.4 override) | ✅ (LLM proxy + TTS) | — | ✅ (embeddings) |
| `REDIS_URL` | optional (full Redis stack: streams, deadlines, router, cache) | ✅ (replies, rate limits, audio) | — | ✅ |
| `AGENT_MEMORY_URL` | optional (incident memory) | — | — | — |
| `TELEGRAM_BOT_TOKEN` | — | ✅ | — | — |
| `TELEGRAM_WEBHOOK_SECRET` | — | ✅ | — | — |
| `PUBLIC_BASE_URL` | — | ✅ (public voice-note URLs) | — | — |
| `KEEPALIVE_LLM_MODELS` / `KEEPALIVE_LLM_RATE_LIMIT_PER_MIN` | — | optional (proxy guardrails) | — | — |
| `KEEPALIVE_TTS_MODEL` / `KEEPALIVE_TTS_VOICE` | — | optional | — | — |
| `KEEPALIVE_DEV_KEYS` (fallback) | — | ✅ (optional) | — | — |
| `DATABASE_URL` (Neon) | — | ✅ (key lookup) | ✅ | — |
| `BETTER_AUTH_SECRET` | — | — | ✅ | — |
| `BETTER_AUTH_URL` | — | — | ✅ | — |

Diagnosis provider ladder (library): `OPENAI_API_KEY` → direct OpenAI;
`KEEPALIVE_USE_WANDB_INFERENCE` (+ `KEEPALIVE_WANDB_INFERENCE_URL`,
`KEEPALIVE_WANDB_INFERENCE_MODEL`) → W&B Inference; default → relay proxy at
`{KEEPALIVE_API_URL}/v1/llm` authed by the `ka_live_` key. See the
[configuration reference](../docs/reference/configuration.mdx) for the full list and
defaults.

For the demo, set `REDIS_URL` + `AGENT_MEMORY_URL` on the GPU box (Railway Redis +
memory service) so all five Redis uses are live; end users don't need either.
