# keepalive

WeaveHacks 4 project (June 7–8 2026, submissions due Sun 1pm). An AI watchdog platform for
ML training runs: users sign in with GitHub, connect a training repo, and `pip install
keepalive`. Merging to main launches training in a **W&B Sandbox**. A **monitoring agent**
(cheap model on W&B Inference) scores live wandb metrics against a plain-English,
user-editable prompt → `{confidence, reasoning}`. When confidence drops below the project
threshold (or a hard failure hits), a **fixing pipeline** fires: a hypothesis agent (no code
tools, consults per-project incident memory) fans out N coding agents — each in its own
Vercel Sandbox on its own git branch — and each opens a **PR with a full report**. Every
agent decision is traced in W&B Weave.

One-liner: **agents that hold your training run accountable — and act when you don't.**

**`infra/architecture-v2.md` is the binding contract** — schema, API shapes, library
surface, UI map, model choices. Read it before changing anything cross-cutting.
(Telegram, Twilio, Cursor SDK, Railway, FastAPI relay, Mintlify, local probe racing,
Redis on the client: all CUT in the June 7 pivot. Don't resurrect them.)

## Architecture (one Next.js app + one thin Python client)

- **apps/dashboard** (Next.js 15 App Router, Vercel) — the ENTIRE backend + UI:
  - Better Auth: email/password + **GitHub social provider** (`scope: ["repo"]`, config
    field is `scope` SINGULAR) + api-key plugin (`ka_live_` keys, sha256-hashed).
  - `POST /api/v1/events` — library ingest (Bearer key) + inline monitoring agent
    (20s debounce per run). `GET /api/v1/projects/{id}/commands` — demo fault injection.
  - `POST /api/github/webhook` — HMAC-verified; push to the project's default branch only
    → `start(trainingLaunch)`. Agent fix branches NEVER trigger training.
  - **Workflows** (Workflow DevKit, `'use workflow'`/`'use step'`, started via
    `start(fn, args)` from `workflow/api`):
    - `src/workflows/fixing-pipeline.ts` — loadContext → hypothesis agent → fan-out
      coding agents (Vercel Sandboxes, opencode-style read/write/edit/bash/grep/glob
      tools from `src/lib/agents/sandbox-tools.ts`) → PRs via Octokit → memory row +
      optional Resend email.
    - `src/workflows/training-launch.ts` — Vercel Sandbox (python3.13) runs a launcher
      that creates a **W&B Sandbox** (no REST API exists — Python gRPC SDK only, hence
      the sandbox-in-sandbox driver) which clones the repo and runs
      `project.trainCommand`.
  - **AI core** (`src/lib/ai/`): AI SDK v6 (`generateText` + `Output.object`, NOT
    generateObject; `ToolLoopAgent` + `stopWhen: stepCountIs(n)`; `inputSchema` not
    parameters). Model routing: `wandb/<id>` → W&B Inference via createOpenAICompatible
    (`https://api.inference.wandb.ai/v1`, our `WANDB_API_KEY`); anything else (e.g.
    `openai/gpt-5.4`) → Vercel AI Gateway plain string. Monitoring default:
    `wandb/microsoft/Phi-4-mini-instruct`.
  - **Weave tracing**: OTel exporter → `https://trace.wandb.ai/otel/v1/traces`
    (Basic `api:<WANDB_API_KEY>`, `project_id: WANDB_PROJECT`). AI SDK calls pass
    `experimental_telemetry`. **Serverless gotcha: `await flushTraces()` before any
    handler/step returns or spans are silently dropped.**
  - `/docs` — Fumadocs (content in `apps/dashboard/content/docs/`, incl. the
    copy-pastable **agent-blurb** users give their coding agent). Pinned to
    fumadocs-ui/core 15.x + fumadocs-mdx 11.x (Next 15 compat); `src/lib/source.ts`
    has a files-thunk/array shim for that version pairing — keep it.
  - DB: Neon Postgres via drizzle, schema in `src/db/schema.ts`, pushed with
    `pnpm db:push` (no migrations; hackathon). Repo-level `project` → `run` →
    `incident` → `agent`, plus `event` feed, `memory`, `command`.
- **packages/keepalive** (pip, uv workspace) — THIN client: hooks `run.log()`, detectors
  (nan/divergence/stall + stderr OOM/exception scan), fire-and-forget event reporter
  (`/api/v1/events`), demo FaultInjector + command poller, CLI (`keepalive login`,
  `keepalive run -- python train.py`). Surface:
  `with keepalive.watchdog(run, prompt="...", threshold=0.6, max_agents=3): train()`.
  On failure it reports and KEEPS GOING — fixing happens server-side via PRs.
  Config precedence: kwargs > env (`KEEPALIVE_API_KEY/URL`) > `~/.config/keepalive/config.json`.

## Monorepo

Two independent workspaces (uv for Python, pnpm for TS). Do NOT unify.

```
keepalive/
├── pyproject.toml          # uv workspace: members = ["packages/*"]
├── packages/keepalive/     # the pip library (src/ layout, py.typed)
├── apps/dashboard/         # Next.js: everything else (UI, API, workflows, docs)
└── infra/                  # architecture-v2.md (CONTRACT), vercel.md, observability.md (v1, partly superseded)
```

Quality bar: `uv run ruff check && uv run pyright && uv run pytest` (92 tests) and
`pnpm -C apps/dashboard exec tsc --noEmit && pnpm -C apps/dashboard test && pnpm -C
apps/dashboard exec oxlint src` (74 tests) must stay green. `next build` works with
dummy `DATABASE_URL`/`BETTER_AUTH_SECRET`. Known: oxfmt 0.1.0 corrupts some inline
type annotations — don't run it blind.

## Env (Vercel)

`DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` (public — also the webhook +
library URL), `GITHUB_CLIENT_ID/SECRET` (OAuth App, callback
`/api/auth/callback/github`), `GITHUB_WEBHOOK_SECRET`, `AI_GATEWAY_API_KEY` (or Vercel
OIDC), `WANDB_API_KEY` + `WANDB_PROJECT` (Weave traces + W&B Inference), `RESEND_API_KEY`
(optional). Users set their own wandb key in /settings (used to launch their sandbox
training); each project mints a raw `trainingApiKey` at creation.

## Critical gotchas

- W&B Sandboxes: public preview, Python SDK only (no REST), CPU on serverless tier (GPU
  = CKS/roadmap — pitch it, don't promise it). Free tier confirmed verbally by W&B staff.
  `Sandbox.run("bash","-c", script, network=NetworkOptions(egress_mode="internet"), ...)`
  — main command = training, driver exits without waiting. Smoke-test early; quota bumps
  at the event.
- Vercel Sandbox: `Sandbox.create({source:{type:'git',...}, runtime, resources, timeout})`,
  `runCommand({cmd,args,env,cwd})`; repo root is `/vercel/sandbox`; always `stop()` in
  finally; Hobby = 45min/10 concurrent.
- Better Auth: verifyApiKey returns the owner as `key.referenceId` (NOT userId).
  GitHub OAuth-app tokens never expire — no refresh logic. Token lives in `account`.
- GitHub webhook: validate raw-body HMAC (`x-hub-signature-256`, timingSafeEqual);
  squash-merge fires both `pull_request` and `push` — we key off `push` only.
- wandb model IDs and W&B Inference slugs drift — verify via
  `GET https://api.inference.wandb.ai/v1/models` before the demo.
- Weave + separate processes (sandboxes, workflow steps): each must init its own
  tracing or traces are silently lost.

## Hackathon constraints

- W&B Weave is a HARD requirement + Weave link in the submission.
- 3-minute demo: connect repo on stage → merge → W&B Sandbox training appears in wandb →
  inject fault from the dashboard → monitor confidence drops → fixing pipeline fans out
  coding agents → PRs with reports land on the GitHub repo → Weave trace tree.
- Judged on: utility, technical demo, creativity, presentation, **multi-agent harness
  sophistication**. Sponsors used: W&B (Weave + Sandboxes + Inference), OpenAI (GPT-5.4
  via AI Gateway), Vercel (AI SDK, Workflows, Sandbox, AI Gateway).
- Demo pacing: monitoring debounce is 20s; `command` table fault injection works on any
  live run with `demo_mode=True`.
