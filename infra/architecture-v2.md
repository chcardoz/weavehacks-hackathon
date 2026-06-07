# keepalive v2 — Vercel-native architecture (the pivot)

Single source of truth for the June 2026 pivot. Supersedes the Railway/Telegram/Cursor
design and the parts of `observability.md` that conflict with it. Every workspace codes
against THIS document.

## System overview

```
Python lib (pip install keepalive) — THIN client
  keepalive.watchdog(run, prompt="...", threshold=0.6, max_agents=3)
  → hooks run.log(), batches metrics/events → POST {api_url}/api/v1/events
  → hard-failure detectors (nan/oom/exception/stall) → incident.detected event
  → demo: polls GET /api/v1/projects/{id}/commands for fault injection

Next.js dashboard on Vercel — the ENTIRE backend
  /api/v1/events           ingest (Bearer ka_live_) + monitoring agent scores batches
  /api/github/webhook      push to default branch → trainingLaunch workflow
  fixingPipeline workflow  hypothesis agent → N coding agents (Vercel Sandboxes) → PRs
  trainingLaunch workflow  Vercel Sandbox (python) → launches W&B Sandbox training run
  /docs                    Fumadocs
  Weave: OTel exporter → trace.wandb.ai (all AI SDK calls traced as one tree per incident)
```

Telegram, Twilio, Cursor SDK, Railway, FastAPI, Mintlify: all GONE.

## User journey (drives everything)

1. Landing page → **Sign in with GitHub** (Better Auth social provider, `scope: ["repo"]`).
2. Issue an API key (`ka_live_…`, existing Better Auth api-key plugin).
3. **New Project**: pick a GitHub repo → we store repo + create a push webhook on it.
4. Locally: `pip install keepalive`, `keepalive login` (stores key), paste the
   **agent blurb** (a copy-pastable prompt telling their coding agent how to wire
   keepalive + wandb into the training script).
5. Merge to main → webhook → `trainingLaunch` workflow → training runs in a
   **W&B Sandbox**, visible in wandb, reporting metrics to us.
6. **Monitoring agent** (cheap model, W&B Inference) scores each metrics window
   against the project's plain-English monitoring prompt → `{confidence, reasoning}`.
7. `confidence < threshold` (or hard client-side failure) → incident → `fixingPipeline`:
   **hypothesis agent** (no code tools, searches incident memory) → fans out ≤ maxAgents
   **coding agents**, each in its own Vercel Sandbox on its own branch → each opens a
   **PR with a full report**. Optional Resend email recap. Branch pushes do NOT trigger
   training (webhook only fires the pipeline for the default branch).

## Database schema v2 (drizzle, Neon Postgres — `apps/dashboard/src/db/schema.ts`)

No migrations; `drizzle-kit push` and nuking prod data is fine. Better Auth tables
(user, session, account, verification, apikey) stay Better Auth-managed, EXCEPT:

- `user` gains: `wandbApiKey` text (nullable — user-level setting for sandbox training).

App tables (replace the old project/incident/agent shape):

```
project            — repo-level entity (Vercel-like), created from the dashboard
  id               text pk (nanoid)
  userId           text → user.id, not null
  name             text not null
  repoOwner        text not null
  repoName         text not null
  defaultBranch    text not null default 'main'
  webhookId        integer            -- GitHub hook id we created
  trainCommand     text not null default 'python train.py'
  monitoringPrompt text               -- plain-English watch criteria (null = lib value or default)
  fixingPrompt     text               -- hypothesis-agent prompt override
  confidenceThreshold real not null default 0.6
  maxAgents        integer not null default 3
  monitorModel     text not null default 'wandb/microsoft/Phi-4-mini-instruct'
  trainingApiKey   text               -- raw ka_live_ key minted for sandbox runs (hackathon-ok)
  status           text not null default 'idle'   -- idle|training|incident|fixing|recovered|stopped
  createdAt/updatedAt timestamps

run                — one training run (local or sandbox)
  id               text pk (library-chosen: wandb run id, else nanoid)
  projectId        → project.id, not null
  wandbRunId, wandbUrl, commitSha, branch text
  source           text not null default 'local'  -- local|sandbox
  sandboxId        text                            -- W&B sandbox id when source=sandbox
  status           text not null default 'training' -- training|incident|fixing|recovered|stopped|finished
  currentStep      integer
  latestLoss       real
  lossHistory      jsonb [{step,loss}] capped ~120
  metricsWindow    jsonb [{step, metrics:{...}}] capped ~40  -- monitor agent input
  demoMode         boolean default false
  lastEventAt, lastScoredAt timestamps
  createdAt        timestamp

incident
  id               text pk (nanoid or library id)
  projectId, runId not null refs
  kind             text   -- nan_loss|divergence|stall|oom|exception|monitor_flag
  step             integer
  status           text not null default 'detected' -- detected|hypothesizing|fixing|resolved|failed
  confidence       real             -- monitor score that tripped it
  reasoning        text             -- monitor's one-liner
  diagnosis        text             -- hypothesis agent's summary
  workflowRunId    text             -- Workflow DevKit run id
  weaveUrl         text
  winnerAgentId    text
  resolvedAt, createdAt timestamps

agent              — one coding agent (ours, in a Vercel Sandbox)
  id               text pk (nanoid)
  incidentId, projectId not null refs
  hypothesis       text not null
  branch           text             -- keepalive/fix-{incidentShort}-{n}
  prUrl            text
  prNumber         integer
  state            text not null default 'spawned' -- spawned|coding|pushed|pr_opened|failed
  report           text             -- markdown report (also the PR body)
  sandboxId        text
  error            text
  createdAt/updatedAt timestamps

event              — append-only feed (same spirit as v1)
  id bigserial pk; projectId not null; runId, incidentId, agentId nullable
  source           text -- library|server|monitor|hypothesis|coder|sandbox|github
  level            text -- info|warn|error
  type             text
  message          text
  data             jsonb
  createdAt        timestamp default now

memory             — incident memory, per project (sidebar item; hypothesis agent searches it)
  id               text pk (nanoid)
  projectId        not null ref
  incidentId       text
  kind             text       -- failure kind
  summary          text not null   -- what happened + winning fix, written by the pipeline
  resolution       text            -- what fixed it (PR link, hypothesis)
  data             jsonb
  createdAt        timestamp

command            — demo fault injection (unchanged contract)
  id text pk (uuid), projectId not null, type text, status pending|consumed,
  consumedAt, createdAt
```

## Library-facing API (Next.js route handlers, Bearer `ka_live_` key)

Auth: validate via Better Auth api-key plugin (`auth.api.verifyApiKey`). The key's
user owns the projects.

### POST /api/v1/events

Same batch shape as v1 (`infra/observability.md`) with these changes:

- `project` block now: `{name, repo_owner, repo_name, branch, commit_sha, wandb_run_id,
  wandb_url, demo_mode, monitoring_prompt?, threshold?, max_agents?}`.
- Server resolves the **project** by `(userId, repo_owner, repo_name)` — creates it if
  missing (library-first flow). Server resolves the **run** by event `project_id` field
  (which the library still fills with its run-scoped id — treated as `run.id`).
- Library prompt/threshold/max_agents apply ONLY when the project columns are null
  (dashboard edits win).
- Response: `{"accepted": N, "project_id": "...", "run_id": "..."}`.

Library-emitted types (the only ones now): `run.started`, `run.heartbeat`
(`data: {step, loss?, metrics: {...}}` — full metrics dict, sampled ≤ every 5s),
`run.stopped`, `incident.detected` (`data: {kind, step, message?, metrics_tail?}`),
`log`. Everything else (diagnosis, agents, promotion) is server-emitted into `event`
by the workflows (source=`server|monitor|hypothesis|coder`).

Ingest side effects:
1. Always insert `event` rows; upsert project/run metadata; update run step/loss/
   metricsWindow on heartbeats.
2. `incident.detected` → create incident + `start(fixingPipeline)` (if no open incident
   for the run).
3. After heartbeats: if `now - run.lastScoredAt > 20s` and run.status=training →
   monitoring agent scores `metricsWindow` against the effective monitoring prompt →
   emit `monitor.scored` event `{confidence, reasoning, signals}` → if
   `confidence < threshold` → create incident (kind=monitor_flag) +
   `start(fixingPipeline)`.

### GET /api/v1/projects/{projectId}/commands

Unchanged: atomically consume pending commands, `{"commands":[{id,type,created_at}]}`.

## Python library surface (packages/keepalive)

The library gets THIN. Keep: detectors, metric hook, reporter, fault injector,
command poller, CLI. Delete: probes/* (cursor, sandbox, local, executor, judge),
diagnose/*, escalate/*, memory/*, events.py (Redis streams). Keep `tracing.py`
(optional weave on the user side).

```python
import keepalive

with keepalive.watchdog(
    run,                                   # wandb run
    prompt="Flag if val/loss diverges from train/loss or grad_norm spikes.",
    threshold=0.6,
    max_agents=3,
    checkpoint_dir="ckpts/",               # kept in signature; informational
    demo_mode=False,
):
    train()
```

- Config: `KEEPALIVE_API_KEY`, `KEEPALIVE_API_URL` (default `https://keepalive.club`),
  or `~/.config/keepalive/config.json` written by `keepalive login`.
- CLI: `keepalive login` (prompt for key, store), `keepalive run -- python train.py`
  (subprocess supervisor, stderr OOM/exception scan, emits events).
- `run.started` carries repo info: parse `git remote get-url origin` → owner/name,
  `git rev-parse HEAD` → commit_sha, current branch.
- On hard failure: emit `incident.detected`, keep the process alive (training paused or
  crashed is fine — the server fixes via PRs; no local racing anymore).

## Monitoring agent (server-side, in the ingest path)

- AI SDK v6: `generateText` + `Output.object({schema})` →
  `{confidence: 0..1, reasoning: string, signals: string[]}`.
- Model: project.monitorModel. Prefix routing: `wandb/<id>` → W&B Inference via
  `createOpenAICompatible({baseURL: 'https://api.inference.wandb.ai/v1', apiKey: WANDB_API_KEY})`;
  anything else (`openai/gpt-5.4-mini` etc.) → Vercel AI Gateway plain string.
- System prompt = built-in guardrails + the project's plain-English monitoring prompt.
- Runs inline in the ingest route (1–3s); NOT a workflow.

## Fixing pipeline (Workflow DevKit, `'use workflow'`)

`fixingPipeline(incidentId)`:
1. step `loadContext`: project, run, incident, last N memory rows, recent events.
2. step `generateHypotheses`: hypothesis agent — strong model via gateway
   (`openai/gpt-5.4`), `ToolLoopAgent`, ONLY tool = `searchIncidentMemory`
   (semantic-first: Redis vector KNN via `src/lib/memory/semantic.ts`, falling
   back to SQL ILIKE on the `memory` table when Redis/embeddings are
   unavailable). Produces ≤ maxAgents distinct hypotheses + a diagnosis
   summary. NO code tools.
3. `Promise.all(hypotheses.map(runCodingAgent))` — each step:
   - create Vercel Sandbox (`@vercel/sandbox`), clone repo at `incident` run's
     commitSha using the user's GitHub token (Better Auth account table),
     `git checkout -b keepalive/fix-{short}-{n}`.
   - `ToolLoopAgent` with opencode-style tools (read/write/edit/bash/grep/glob)
     implemented over sandbox.runCommand/readFileToBuffer/writeFiles.
   - commit + push branch; open PR via Octokit with the agent's full markdown report;
     update `agent` row + emit events at each transition.
4. step `finalize`: write `memory` row (dual-write: Postgres = source of truth
   for the UI, Redis = semantic search index via `storeMemorySemantic`), mark
   incident resolved/failed, set project/run status, optional Resend email report.

GitHub PR bodies are the human-facing report. The webhook ignores non-default
branches, so agent branches never trigger training.

## Training launch (Workflow + W&B Sandbox)

`/api/github/webhook` (raw-body HMAC `x-hub-signature-256`, `GITHUB_WEBHOOK_SECRET`):
`push` to `refs/heads/{defaultBranch}` → find project by repo → `start(trainingLaunch)`.

`trainingLaunch(projectId, commitSha)`: W&B Sandboxes have NO REST API (Python gRPC
SDK only), so: create a **Vercel Sandbox** (runtime python3.13), `pip install
"wandb[sandbox]"`, write + run `launcher.py` (a template string owned by the
dashboard's training workflow code) which creates a W&B Sandbox (`NetworkOptions(egress_mode="internet")`, secrets/env:
`WANDB_API_KEY` = user's, `KEEPALIVE_API_KEY` = project.trainingApiKey,
`KEEPALIVE_API_URL`), git-clones the repo at the SHA, `pip install -r
requirements.txt`, runs `project.trainCommand`, prints the W&B sandbox id, exits.
Store sandboxId on a new `run` row (source=sandbox); training metrics then flow in
via the normal library reporter from inside the W&B sandbox.

CPU-only on the serverless tier (GPU = roadmap/CKS); demo trains a tiny model.

## Dashboard UI map (Vercel-style)

- `/` landing: hero, GitHub sign-in, pip install snippet.
- Signed-in user-level shell, left sidebar: **Projects, API Keys, Settings, Docs**.
  - `/projects` grid + New Project (repo picker via Octokit list repos → creates
    project + webhook).
  - `/keys` existing key management.
  - `/settings` user settings: wandb API key, report email.
- Project-level shell (`/projects/[id]/…`), left sidebar: **← All Projects, Overview,
  Incidents, Agents, Memory, Settings**.
  - Overview: status, live loss chart, latest run, event feed, demo fault-injection.
  - Incidents: list + detail (confidence, reasoning, diagnosis, agents, PRs).
  - Agents: editable monitoring prompt, fixing prompt, threshold slider, max agents,
    monitor model picker.
  - Memory: memory rows for the project.
  - Settings: repo, default branch, train command, danger zone.
- `/docs` Fumadocs: quickstart, agent-blurb, concepts, reference.

## Models & env

| Use | Model | Route |
|---|---|---|
| Monitoring | `wandb/microsoft/Phi-4-mini-instruct` (default) | W&B Inference direct |
| Monitoring alt | `openai/gpt-5.4-mini` | AI Gateway |
| Hypothesis | `openai/gpt-5.4` | AI Gateway |
| Coding agents | `openai/gpt-5.4` | AI Gateway |

Env (dashboard): `DATABASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL`,
`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_WEBHOOK_SECRET`,
`AI_GATEWAY_API_KEY` (or Vercel OIDC), `WANDB_API_KEY` (ours: Weave traces + default
Inference), `WANDB_PROJECT` (e.g. `team/keepalive`), `RESEND_API_KEY` (optional),
`REDIS_URL` (optional — Redis Cloud via the Vercel Marketplace "Redis for Vercel"
integration; enables semantic incident memory), `LANGCACHE_SERVER_URL` +
`LANGCACHE_CACHE_ID` + `LANGCACHE_API_KEY` (optional — Redis LangCache semantic
cache for monitor verdicts).

## Redis (sponsor: semantic memory + LangCache)

Two Redis AI capabilities, both strictly optional (every path degrades
gracefully when env is unset — the demo can never break on missing Redis):

- **Semantic incident memory** — `src/lib/redis.ts` (globalThis singleton; Redis
  Cloud free tier caps at 30 connections) + `src/lib/memory/semantic.ts`.
  Index `idx:memory` (HASH prefix `mem:`, HNSW/COSINE/FLOAT32/DIM 1536).
  Embeddings: `embed({ model: "openai/text-embedding-3-small" })` via AI Gateway
  (W&B Inference has NO embeddings endpoint). `storeMemorySemantic` never
  throws; `searchMemorySemantic` returns `null` when unavailable → callers fall
  back to ILIKE. Consumers: hypothesis agent tool, `finalize` dual-write, and
  `GET /api/incidents/{id}/similar` (powers the "Similar past incidents" card
  in the incidents UI; renders nothing when unavailable).
- **LangCache** — `src/lib/ai/semantic-cache.ts` wraps `scoreMetrics`: semantic
  cache keyed on `monitoringPrompt + "\n" + JSON.stringify(promptBody)`; only
  real model verdicts are cached (never the confidence-1 fallback); 2s
  `timeoutMs` so a slow cache can't stall ingest. SDK: `@redis-ai/langcache`
  (note: `SearchStrategy` enum imports from `@redis-ai/langcache/models`, not
  the package root). node-redis is v6: schema enums are `SCHEMA_FIELD_TYPE` /
  `SCHEMA_VECTOR_FIELD_ALGORITHM`, `DIALECT` is a number.

## Weave tracing (TS side)

OTel exporter → `https://trace.wandb.ai/otel/v1/traces`, headers
`Authorization: Basic base64("api:" + WANDB_API_KEY)` + `project_id: WANDB_PROJECT`.
AI SDK calls set `experimental_telemetry: {isEnabled: true, functionId, metadata}`
(incidentId/projectId in metadata so one incident reads as one tree). Serverless
gotcha: force-flush the tracer provider before route handlers / steps return.
Python side keeps `weave.init` + `@weave.op` (optional, user-side).
