# keepalive

WeaveHacks 4 project (June 7–8 2026, submissions due Sun 1pm). A pip-installable Python
watchdog for GPU training runs: it monitors wandb metrics, detects failures (NaN loss,
divergence, stalls, OOM), explains the failure in plain English, escalates to the human
(Telegram message with action buttons + AI voice note), and if the human doesn't respond before a deadline, spawns parallel
Cursor cloud agents ("probes") that each write a different fix hypothesis on its own git
branch — then races those fixes as short checkpoint-resumed training runs on **W&B/CoreWeave
Sandboxes**. The winning probe's run becomes the training; the rest are killed. Every agent
decision is traced in W&B Weave.

One-liner: **agents that hold you accountable — and stop waiting when you don't show up.**

## Architecture (two machines + one relay — keep this straight)

- **The library** (`pip install keepalive`) runs ON the user's GPU machine, inside/alongside
  the training process. It detects, diagnoses, fetches probe branches, launches/judges probe
  runs, promotes the winner. All action is local to the box with the code/checkpoints/GPU.
- **Cursor cloud agents** (Cursor's VMs, no GPUs) only WRITE code: each probe agent branches
  from the failing run's exact commit SHA and pushes `cursor/probe-*` branches to GitHub.
  They never run training.
- **Probe execution** is a pluggable `ProbeExecutor` Protocol:
  - `SandboxExecutor` — W&B/CoreWeave Sandboxes (`pip install wandb[sandbox]`,
    `from wandb.sandbox import Sandbox`, auth = W&B API key). Kata microVMs, CPU-only,
    arbitrary Python/pip/git. **Free tier confirmed in person by W&B staff.** This is the
    demo path: tiny model probes run on the host's own brand-new public-preview product.
  - `LocalExecutor` — git worktree + subprocess on the user's GPU box. Fallback + the
    real-GPU path. Roadmap slide: CoreWeave GPU sandboxes / Modal.
- **Hosted backend** (FastAPI, api.keepalive.club) does what can't or shouldn't be local:
  API key issuance, Telegram relay (sends incident messages with inline action buttons;
  inbound button-tap / typed 1/2/3 webhook → forwarded to the library), the `/v1/llm`
  diagnosis proxy (fronts OpenAI with OUR key, authed by the `ka_live_` key, model
  allow-list + per-key rate limit), and voice-note TTS + hosting (synthesizes the mp3
  from the library's `voice_script` and sends the in-chat voice bubble). It never touches
  GPUs or code. Net effect: end users supply only `KEEPALIVE_API_KEY`, chat id,
  `WANDB_API_KEY`, `CURSOR_API_KEY` — no OpenAI key, no Redis.

The incident flow: detect → pause loop → diagnose (GPT) → Telegram the human + ZSET deadline →
timeout = authority transfers → Cursor agents push fix branches → executor races probes from
last good checkpoint (separate wandb runs, `group=watchdog-{parent}, job_type=probe`) →
promote winner by loss curve (argmin, not vibes) → winner's run continues as the training →
tag parent run, open PR, store incident in memory, Telegram recap + Weave trace link.

## Library entry points (two doors, one engine)

1. `with keepalive.watchdog(run, escalate=["telegram"], timeout=120, checkpoint_dir=...):` —
   wraps a hand-rolled PyTorch loop; in-process metric hook (zero lag); catches soft
   failures (NaN/divergence/stall/exception). The demo path.
2. `keepalive run -- python train.py ...` — CLI supervisor (subprocess + stderr tail);
   survives hard crashes (CUDA OOM, segfault) that kill the process. ~80 lines.
   HF Trainer/Lightning callbacks + distributed (torchrun/DDP) = roadmap, not weekend code.

Checkpoints are a hard requirement (say it proudly — everyone serious already checkpoints).

## Monorepo layout

Two independent workspaces (uv for Python, pnpm for TS). Do NOT try to unify them.

```
keepalive/
├── pyproject.toml          # uv workspace root: members = ["packages/*", "apps/api"]
├── uv.lock                 # one lockfile for all Python
├── package.json            # pnpm root (dashboard only)
├── pnpm-workspace.yaml
├── packages/
│   └── keepalive/          # THE pip-installable library (src/ layout, py.typed)
├── apps/
│   ├── api/                # FastAPI backend: keys, Telegram relay, reply webhook, audio page
│   └── dashboard/          # Next.js: sign in, issue/revoke API keys (ka_live_...)
└── docs/                   # Mintlify (docs.json, NOT mint.json; CLI is `mint`, not `mintlify`)
```

## Stack decisions (researched & locked — don't relitigate)

- **Python tooling:** uv everywhere. `uv init --lib`, `uv_build` backend, src/ layout,
  ruff + pyright, `py.typed` shipped. CLI via Typer (`[project.scripts] keepalive = "keepalive.cli:app"`).
- **Probe code-writers:** official **Cursor Python SDK** (`pip install cursor-sdk`, import
  `cursor_sdk`) — cloud agents only. Fallback ladder: `cursor-agent-sdk` (community PyPI) →
  raw REST `https://api.cursor.com/v1/agents`.
- **Probe runners:** `SandboxExecutor` (W&B Sandboxes, free tier confirmed) with
  `LocalExecutor` fallback. Smoke-test a sandbox (`pip install torch` + 300 steps) hour one.
- **Diagnosis LLM:** OpenAI **GPT-5.4** via plain API tool-loop (`gpt-5.4-mini` for cheap
  probe-side reasoning). Don't hardcode old ids (gpt-4o/o3 are gone). It THINKS and DELEGATES,
  never edits code itself. Tools: `get_run_history`, `get_logs`, `get_config`,
  `search_incident_memory` (Redis), `escalate`, `spawn_probes`, `promote`/`kill_probes`,
  optionally the W&B MCP server (`https://mcp.withwandb.com/mcp`, Bearer = W&B API key).
  Provider ladder in the engine: `OPENAI_API_KEY` set → direct OpenAI (power user);
  `KEEPALIVE_USE_WANDB_INFERENCE` → W&B Inference; **default → relay `/v1/llm` proxy**
  (ka_live_ key, still gpt-5.4, Weave autopatch unaffected since the client is local).
- **Escalation channel: Telegram (Twilio SMS is CUT — A2P 10DLC carrier filtering eats
  link-bearing SMS and registration takes weeks; live calls also CUT — no Pipecat/Daily/
  Deepgram/Cartesia):** one bot via @BotFather, relay holds `TELEGRAM_BOT_TOKEN`. Incident =
  `sendMessage` with inline buttons (⏪ Roll back / 🔧 Apply fix / 🛑 Stop + 🧵 View trace URL
  button) + `sendVoice` voice bubble. TTS is RELAY-SIDE: the library sends `voice_script`
  text in `/v1/notify`; the relay synthesizes (OpenAI `gpt-4o-mini-tts`, ~$0.015/min, our
  key), hosts the mp3, and Telegram fetches it from the public voice-note URL —
  `PUBLIC_BASE_URL` must be public.
  Replies: Telegram webhook → FastAPI `/telegram`, validated via `X-Telegram-Bot-Api-Secret-Token`
  (set with `setWebhook`); button `callback_data` carries `{incident_id}:{choice}`; typing
  1/2/3 still works. Users press Start on the bot to get `KEEPALIVE_TELEGRAM_CHAT_ID` (bots
  can't message first). Free, no trial restrictions, no ngrok — test by curling the webhook
  with the secret header.
- **Tracing:** `weave.init("<team>/keepalive")` autopatches the OpenAI client; every watchdog
  fn is `@weave.op` so one incident = one trace tree (detect → diagnose → escalate → probe
  fan-out → promotion). `weave.attributes({...})` for incident/run ids;
  `call.feedback.add(...)` for verdicts; `result, call = op.call(...)` → `call.ui_url` is the
  shareable demo trace (we send it to the user). Weave link is REQUIRED in the submission.
- **Run monitoring:** in-process `run.log()` hook (primary, zero lag); wandb public API
  `scan_history(min_step=cursor)` for the CLI-supervisor mode. Probe runs = separate wandb
  runs grouped under the parent (the probe race IS the demo visual — don't build our own
  charts). Write-back: `run.tags += [...]`, `run.notes`, `run.update()`.
- **Redis (five load-bearing uses — the upgraded story):**
  1. Streams + consumer groups (NOT pub/sub) for failure events
  2. ZSET deadline polling for escalation timeouts (keyspace `Ex` notifications are
     best-effort — demo flair only)
  3. **Agent Memory Server** (`pip install agent-memory-client` + one Docker container) —
    working memory (per-incident context) + long-term memory (cross-run incident recall
    with semantic search + dedup). The headline Redis integration.
  4. **RedisVL SemanticRouter** — classify failure signals into incident categories
     (divergence/thermal/dataloader) via embedding KNN, no LLM call
  5. **RedisVL SemanticCache** — cache near-identical probe diagnostic LLM calls
  Image: `redis:8` (query engine in core; redis-stack is legacy). SKIP: LangCache (preview,
  managed), Vector Sets (redundant here). Library-side Redis is OPT-IN: `REDIS_URL` and
  `AGENT_MEMORY_URL` default empty (in-process deadline fallback, optional features skip);
  the demo box sets both so all five uses are live. End users never run Redis.
- **W&B Inference** (OpenAI-compatible, `https://api.inference.wandb.ai/v1`) as a second
  model provider for sponsor coverage; also auto-traced by Weave.
- **Backend hosting:** Railway (FastAPI + Postgres + Redis one-click).
- **Dashboard:** Next.js App Router + **Better Auth `api-key` plugin** (create/show-once/
  revoke natively) + shadcn/ui + Neon Postgres, on Vercel. Prefix `ka_live_`. Must run
  `@better-auth/cli generate && migrate` or the apikey table won't exist.
- **API keys:** `ka_live_<token_urlsafe(32)>`, server stores sha256 hash only, raw key shown
  once, Bearer header. SHA-256 is correct (high-entropy keys) — no bcrypt.
- **Docs:** Mintlify via dashboard onboarding (mintlify.com/start, auto-deploys on push).
  Hand-written MDX API reference (no Python docstring auto-gen exists). `mint dev` to preview.

## Cursor onboarding chain (what our users do — surface errors for each step)

1. Paid Cursor plan (cloud agents are not on free tier).
2. Install the Cursor **GitHub App** (Dashboard → Integrations → Connect GitHub), grant the
   training repo (read-write; private OK).
3. Issue a **user API key** at cursor.com/dashboard/api (NOT service-account — those can't
   use `envVars`). → `CURSOR_API_KEY`.
4. Our SDK passes `repos[].url` + `startingRef=<failing run's commit SHA>` (we capture
   `git rev-parse HEAD` at watchdog start; wandb records it too). Not-connected repo →
   `IntegrationNotConnectedError` — catch it and link the user to Dashboard → Integrations.

## Critical gotchas (from doc deep-dives)

- Cursor: one active run per agent (parallelism = many agents); idempotent `agentId` UUIDs
  (but `agentId` is incompatible with `envVars` — pick `envVars`); branch/PR comes from REST
  `git.branches` on the run object; `/v1/repositories` rate-limited 1/min — cache it; no
  webhooks in v1 — poll or SSE `/stream`; cloud VMs = CPU-only, internet on by default;
  commits are signed by the Cursor bot identity.
- W&B Sandboxes: public preview; serverless path is CPU-only; time limits + default
  CPU/RAM undocumented — smoke-test hour one; free tier confirmed verbally by W&B staff
  (get quota bumped at the event if needed).
- wandb history ingestion lags seconds→minutes (public API); re-fetch `api.run(...)` per poll
  (the Run object caches); never co-write `_step` to the trainer's run — separate grouped
  probe runs instead.
- Weave + multiprocessing: each child process must call `weave.init()` itself or traces are
  silently lost.
- Redis vectors must stay bytes (`np.float32(...).tobytes()`); `decode_responses=True`
  corrupts them; KNN needs `.dialect(2)`; dim mismatch fails silently.
- Telegram fetches the voice-note mp3 by URL: it must be public with `Content-Type:
  audio/mpeg` or the voice bubble silently doesn't arrive (the text message still does).
- PyPI: trusted publishing (OIDC) via GitHub Actions; `id-token: write` is the load-bearing
  permission; register the pending publisher before first release.

## Hackathon constraints

- Must use W&B Weave (hard requirement) + include the Weave link in the submission.
- All code written at the hackathon, public GitHub repo, commit early/often.
- 3-minute demo, strictly enforced. Demo = tiny training run (nanoGPT/CIFAR) with a
  **fault injector** (`--inject nan@step400`); escalation timeouts configurable to ~20s for
  demo pacing. Demo beats: live Telegram message (buttons + voice note) arrives on
  stage → ignored → sandbox probe race on the wandb dashboard → recovery message with
  Weave trace link.
- Judged on: utility, technical demo, creativity, presentation, **multi-agent harness
  sophistication**. Sponsor usage: W&B (Weave + Sandboxes + Inference + optionally MCP),
  OpenAI (GPT-5.4 + TTS), Cursor (SDK as probe code-writer), Redis (5 uses). CopilotKit
  deliberately skipped. Pipecat/Daily cut (voice note as a Telegram voice bubble instead —
  no dial-out approval blocker).
- Pitch language for Olding: the escalation ladder = Awareness / Agency / Assurance.
  Pitch language for CoreWeave judges: probe executor is pluggable; GPU sandboxes are
  CoreWeave's own roadmap — keepalive is built on their primitive.

## Build order (cut from the bottom)

1. Library core: detect → diagnose (GPT tool-loop) → Cursor fix branches → SandboxExecutor
   probe race → promote winner. End-to-end on one seeded failure. (LocalExecutor fallback
   if sandboxes misbehave.)
2. Weave instrumentation throughout + wandb probe-run grouping.
3. Telegram escalation (via backend relay) + ZSET timeout state machine + TTS voice-note
   bubble.
4. Redis Agent Memory Server + SemanticRouter (memory recall in the diagnosis = great
   demo moment: "I've seen this NaN pattern before").
5. Dashboard key issuance + `keepalive run` CLI supervisor.
6. Mintlify docs site + SemanticCache.
