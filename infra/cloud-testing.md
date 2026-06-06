# Cloud test plan — every provider, live, top to bottom

No mocks, no localhost, no docker-compose. Each phase ends in a pass/fail check. Phases
1–2 are independent of each other; 3–4 need everything before them.

Unit tests (`uv run pytest`, fakeredis + respx) still run anywhere — this file is about
proving the **real** providers work.

## Phase 0 — accounts + keys (15 min, do first)

| Provider | What you need | Where |
| -------- | ------------- | ----- |
| W&B | `WANDB_API_KEY` | wandb.ai/settings |
| OpenAI | `OPENAI_API_KEY` with billing — **goes on the relay**, not the library (end users never supply one) | platform.openai.com |
| Cursor | **paid plan**, user key (`CURSOR_API_KEY`), GitHub App installed on the training repo | cursor.com/dashboard → API Keys + Integrations |
| Telegram | bot token from @BotFather, webhook secret, your chat id (press Start on the bot) | [telegram.md](./telegram.md) |
| Railway | project with relay + Redis 8 + memory server | [railway.md](./railway.md), [redis.md](./redis.md) |
| Vercel/Neon | dashboard deployed, migrations run | [vercel.md](./vercel.md) |
| GitHub | a **scratch repo** connected to the Cursor GitHub App (cheap smoke tests) | — |

Put a card on Cursor now — cloud agents don't exist on the free plan. Telegram is free.

## Phase 1 — per-provider smoke tests (independent, run in parallel)

### 1a. W&B Sandbox (the probe executor — highest risk, do FIRST)

Run the hour-one smoke test in [wandb-sandboxes.md](./wandb-sandboxes.md):
`pip install "wandb[sandbox]"`, boot `Sandbox.run()`, pip-install torch, 300 steps.
**Pass:** `SMOKE_OK` + noted wall-clock. **Fail:** flip `SandboxExecutor` → `LocalExecutor`
and move on; it's pluggable for exactly this reason.

### 1b. Weave tracing

```python
import weave
weave.init("<team>/keepalive")

@weave.op
def ping(x: str) -> str: return x.upper()

result, call = ping.call("hello")
print(call.ui_url)        # open it — this is the link we send to users
```

**Pass:** trace visible at the printed URL. Remember: every child **process** must call
`weave.init()` itself or its traces silently vanish.

### 1c. W&B Inference (second provider)

```bash
curl -H "Authorization: Bearer $WANDB_API_KEY" https://api.inference.wandb.ai/v1/models
```

**Pass:** model list includes `openai/gpt-oss-120b`. Note: model ids are namespaced
open-weights models; pass `default_headers={"OpenAI-Project": "<team>/keepalive"}` for
usage attribution.

### 1d. Cursor cloud agents (≈ a few cents)

```bash
# auth
curl -sS https://api.cursor.com/v1/me -H "Authorization: Bearer $CURSOR_API_KEY"
# repo connected? RATE LIMITED 1/min — don't hammer
curl -sS https://api.cursor.com/v1/repositories -H "Authorization: Bearer $CURSOR_API_KEY"
# launch the cheapest possible agent against the SCRATCH repo
curl -sS -X POST https://api.cursor.com/v1/agents \
  -H "Authorization: Bearer $CURSOR_API_KEY" -H "Content-Type: application/json" \
  -d '{"prompt":{"text":"Add a one-line comment to the top of README.md"},
       "repos":[{"url":"https://github.com/<you>/<scratch-repo>","startingRef":"main"}],
       "autoCreatePR":false}'
# poll until FINISHED, read git.branches[].branch (cursor/...)
curl -sS https://api.cursor.com/v1/agents/<id> -H "Authorization: Bearer $CURSOR_API_KEY"
```

**Pass:** status reaches `FINISHED` and a `cursor/...` branch exists on the scratch repo.
Then repeat with `"startingRef": "<a specific commit SHA>"` — that's our actual probe
contract. One active run per agent; parallelism = many agents.

### 1e. Redis 8 + Agent Memory Server (Railway)

Run the checks in [redis.md](./redis.md): `PING`, `FT._LIST`, Streams/XGROUP, ZSET,
`FT.CREATE` vector index, then `curl https://<memory-service>.up.railway.app/v1/health`.

### 1f. OpenAI

```bash
curl -s https://api.openai.com/v1/responses -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" -d '{"model":"gpt-5.4-mini","input":"ping"}'
```

Also generate one `gpt-4o-mini-tts` mp3 and play it — that's the voice note.

## Phase 2 — relay integration (Railway + Telegram + dashboard)

1. **Key issuance:** sign in at the dashboard, issue a `ka_live_` key, confirm the sha256
   row lands in Neon `apikey`.
2. **Webhook wiring:** `setWebhook` + `getWebhookInfo` per [telegram.md](./telegram.md) §2.
3. **Outbound message:** `POST /v1/notify` per [railway.md](./railway.md) §5 with that key.
   **Pass:** Telegram message with ⏪/🔧/🛑 buttons arrives on your phone.
4. **Inbound reply, no phone needed:** curl the webhook with the secret header per
   [telegram.md](./telegram.md) §5. **Pass:** `GET /v1/incidents/<id>/reply` returns `"2"`.
5. **Inbound reply, real phone:** tap a button on the message from step 3 (also try typing
   `2`). Same check.
6. **Voice note:** `POST /v1/notify` with a `voice_script` field — the relay runs TTS,
   hosts the mp3, and sends the voice bubble. **Pass:** a playable voice bubble arrives
   in the chat (requires the relay's `OPENAI_API_KEY` set and `PUBLIC_BASE_URL` publicly
   reachable — Telegram fetches the mp3 from it).
7. **LLM proxy:**
   ```bash
   curl -sS https://api.keepalive.club/v1/llm/chat/completions \
     -H "Authorization: Bearer ka_live_..." -H "Content-Type: application/json" \
     -d '{"model":"gpt-5.4-mini","messages":[{"role":"user","content":"ping"}]}'
   ```
   **Pass:** a chat completion comes back. Also check a disallowed model returns 400 and
   a missing key returns 401.

## Phase 3 — library against live providers (no relay-side fakes left)

On the GPU box (or any laptop — probes are CPU-only anyway), export the library env
(see [README.md](./README.md) master table). The end-user set is just `KEEPALIVE_API_KEY`,
`KEEPALIVE_API_URL=https://api.keepalive.club`, `KEEPALIVE_TELEGRAM_CHAT_ID`,
`WANDB_API_KEY`, `CURSOR_API_KEY` — diagnosis and TTS ride the relay. For the demo box,
also set `REDIS_URL=<railway redis>` and `AGENT_MEMORY_URL=<railway memory service>` so
all five Redis uses are live. Then drive a tiny fault-injected run:

```python
# smoke_e2e.py — must be a git repo connected to the Cursor GitHub App, with a commit pushed
import math, wandb, keepalive, torch

run = wandb.init(project="keepalive-e2e")
x = torch.randn(64, 64); w = torch.randn(64, 64, requires_grad=True)
opt = torch.optim.SGD([w], lr=1e-3)

with keepalive.watchdog(run, escalate=["telegram"], timeout=30, checkpoint_dir="ckpts"):
    for step in range(1000):
        loss = (x @ w).pow(2).mean()
        if step == 400:
            loss = loss * float("nan")        # fault injection
        opt.zero_grad(); loss.backward(); opt.step()
        run.log({"loss": loss.item()})
```

Set `KEEPALIVE_TIMEOUT=30` so you're not waiting 2 minutes. Two passes:

- **Human-responds path:** tap ⏪ Roll back (or type `1`) within 30s. **Pass:** loop resumes from
  checkpoint, no probes spawned.
- **Timeout path:** ignore the Telegram message. **Pass, checked in order:** Cursor pushes
  `cursor/probe-*` branches from the failing SHA → sandbox probe runs appear on the W&B
  dashboard under `group=watchdog-<run_id>`, `job_type=probe` → winner promoted by argmin
  loss → parent run tagged + recap message with a working Weave trace link → incident stored
  in memory (rerun the script: diagnosis should recall "seen this NaN pattern before").

## Phase 4 — demo dress rehearsal

Full Phase 3 timeout path, untouched, with the W&B dashboard and your phone on screen,
inside 3 minutes. Run it twice. Note wall-clock of each beat (sandbox torch install is the
slow one — consider pre-warming or a lighter probe requirement).

## Known cost of a full pass

~3–5 Cursor agent runs (cents each + tokens), one TTS mp3 (~$0.015), OpenAI diagnosis
calls, $0 Telegram, $0 W&B (free tier). A full e2e pass is well under $5.
