# keepalive

WeaveHacks 4 project (June 7–8 2026, submissions due Sun 1pm). A pip-installable Python
watchdog for GPU training runs: it monitors wandb metrics, detects failures (NaN loss,
divergence, stalls, OOM), explains the failure in plain English, escalates to the human
(SMS + AI voice note), and if the human doesn't respond before a deadline, spawns parallel
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
- **Hosted backend** (FastAPI, api.keepalive.club) does ONLY what can't be local: API key
  issuance, Twilio SMS relay (send + inbound 1/2/3 reply webhook → forwarded to the library),
  hosting the voice-note audio page. It never touches GPUs or code.

The incident flow: detect → pause loop → diagnose (GPT) → SMS the human + ZSET deadline →
timeout = authority transfers → Cursor agents push fix branches → executor races probes from
last good checkpoint (separate wandb runs, `group=watchdog-{parent}, job_type=probe`) →
promote winner by loss curve (argmin, not vibes) → winner's run continues as the training →
tag parent run, open PR, store incident in memory, SMS recap + Weave trace link.

## Library entry points (two doors, one engine)

1. `with keepalive.watchdog(run, escalate=["sms"], timeout=120, checkpoint_dir=...):` —
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
│   ├── api/                # FastAPI backend: keys, SMS relay, reply webhook, audio page
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
- **Voice note (NOT live calls — Pipecat/Daily/Deepgram/Cartesia are CUT):** OpenAI
  `gpt-4o-mini-tts` → mp3 (~$0.015/min). Do NOT send as MMS attachment (carriers mangle
  audio; Twilio recommends ≤600KB and often converts to a link anyway). Send **SMS with a
  short link** to a hosted `<audio>` page (serve with `Content-Type: audio/mpeg`) + the
  Weave trace link. Replies: Twilio inbound webhook → FastAPI `/sms` ("1"=rollback,
  "2"=apply fix, "3"=stop), validate `X-Twilio-Signature`, ngrok for local dev. Twilio trial
  only texts verified numbers + stamps a prefix — put a card on the account before demo.
- **Tracing:** `weave.init("<team>/keepalive")` autopatches the OpenAI client; every watchdog
  fn is `@weave.op` so one incident = one trace tree (detect → diagnose → escalate → probe
  fan-out → promotion). `weave.attributes({...})` for incident/run ids;
  `call.feedback.add(...)` for verdicts; `result, call = op.call(...)` → `call.ui_url` is the
  shareable demo trace (we SMS it to the user). Weave link is REQUIRED in the submission.
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
  managed), Vector Sets (redundant here).
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
- Twilio media_url must be public with correct Content-Type or the send is rejected.
- PyPI: trusted publishing (OIDC) via GitHub Actions; `id-token: write` is the load-bearing
  permission; register the pending publisher before first release.

## Hackathon constraints

- Must use W&B Weave (hard requirement) + include the Weave link in the submission.
- All code written at the hackathon, public GitHub repo, commit early/often.
- 3-minute demo, strictly enforced. Demo = tiny training run (nanoGPT/CIFAR) with a
  **fault injector** (`--inject nan@step400`); escalation timeouts configurable to ~20s for
  demo pacing. Demo beats: live SMS arrives on stage → ignored → sandbox probe race on the
  wandb dashboard → recovery SMS with Weave trace link.
- Judged on: utility, technical demo, creativity, presentation, **multi-agent harness
  sophistication**. Sponsor usage: W&B (Weave + Sandboxes + Inference + optionally MCP),
  OpenAI (GPT-5.4 + TTS), Cursor (SDK as probe code-writer), Redis (5 uses). CopilotKit
  deliberately skipped. Pipecat/Daily cut (voice note via SMS link instead — no dial-out
  approval blocker).
- Pitch language for Olding: the escalation ladder = Awareness / Agency / Assurance.
  Pitch language for CoreWeave judges: probe executor is pluggable; GPU sandboxes are
  CoreWeave's own roadmap — keepalive is built on their primitive.

## Build order (cut from the bottom)

1. Library core: detect → diagnose (GPT tool-loop) → Cursor fix branches → SandboxExecutor
   probe race → promote winner. End-to-end on one seeded failure. (LocalExecutor fallback
   if sandboxes misbehave.)
2. Weave instrumentation throughout + wandb probe-run grouping.
3. SMS escalation (Twilio via backend relay) + ZSET timeout state machine + TTS voice-note
   page.
4. Redis Agent Memory Server + SemanticRouter (memory recall in the diagnosis = great
   demo moment: "I've seen this NaN pattern before").
5. Dashboard key issuance + `keepalive run` CLI supervisor.
6. Mintlify docs site + SemanticCache.
