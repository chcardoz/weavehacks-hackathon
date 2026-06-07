# Vercel — deploy the dashboard (`apps/dashboard`)

Next.js App Router app for issuing / revoking `ka_live_` keys. Better Auth `api-key`
plugin + drizzle + Neon Postgres + shadcn/ui. pnpm.

## 1. Provision Neon

1. Create a Neon project → copy the pooled connection string.
2. It becomes `DATABASE_URL` for both the dashboard and the relay (they share the
   `apikey` table).

## 2. Import the repo into Vercel

- New Project → import this repo.
- **Root directory:** `apps/dashboard`
- **Package manager:** pnpm (Vercel auto-detects from `pnpm-lock.yaml`).
- Framework preset: Next.js (auto).

## 3. Environment variables

| Var | Value |
| --- | ----- |
| `DATABASE_URL` | Neon pooled connection string |
| `BETTER_AUTH_SECRET` | random 32+ byte secret (`openssl rand -base64 32`) |
| `BETTER_AUTH_URL` | the dashboard's public URL, e.g. `https://keepalive.club` |
| `GITHUB_CLIENT_ID` | GitHub OAuth App client id (see §7) |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App client secret (see §7) |

## 4. Push the schema BEFORE first use

The Better Auth `api-key` plugin needs an `apikey` table (and the observability
tables need to exist for `/projects`). None exist until you push the schema.
From `apps/dashboard`, against Neon (prefer the **unpooled** connection string
for DDL):

```bash
DATABASE_URL="<neon connection string>" pnpm db:push
```

Heads-up: `@better-auth/cli migrate` does NOT work with this app (drizzle
adapter; the CLI's migrate only supports Kysely) — `db:push` (drizzle-kit) is
the working path. If you change Better Auth plugins, regenerate that part of
the schema with `pnpm db:generate` first.

<!-- If you skip this, key issuance fails because the apikey table is missing. -->

## 5. Custom domain

Vercel → Project → Settings → Domains → add `keepalive.club`. Update DNS as Vercel
instructs. Set `BETTER_AUTH_URL=https://keepalive.club`.

## 6. Smoke test

1. Open `https://keepalive.club`, sign in.
2. Issue a key → confirm it shows once and is prefixed `ka_live_`.
3. Confirm a row landed in the Neon `apikey` table (sha256 hash stored, never the raw key).
4. Use that key against the relay's `/v1/notify` (see `railway.md`).

## 7. GitHub OAuth app setup

Sign-in is **Continue with GitHub** (Better Auth social provider, `scope: ["repo"]`
so we can read repos, create push webhooks, push branches, and open PRs on the repos
the user admins). Set this up before first sign-in.

1. GitHub → your account/org → **Settings → Developer settings → OAuth Apps → New
   OAuth App**.
2. Fields:
   - **Application name:** `keepalive` (or `keepalive (dev)` for the localhost app).
   - **Homepage URL:** `https://keepalive.club` (or `http://localhost:3000`).
   - **Authorization callback URL:** `{BETTER_AUTH_URL}/api/auth/callback/github`,
     i.e. `https://keepalive.club/api/auth/callback/github`.
3. A GitHub OAuth App allows **one callback URL** only, so create a **second OAuth
   App** for local dev with callback
   `http://localhost:3000/api/auth/callback/github`.
4. On each app: **Generate a new client secret**, then copy the **Client ID** and
   **Client secret**.
5. Set the env vars:
   - Production (Vercel project env): `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` from
     the production OAuth App. Ensure `BETTER_AUTH_URL` matches the app's callback host.
   - Local (`.env.local`): the dev OAuth App's id/secret, plus
     `BETTER_AUTH_URL=http://localhost:3000`.

The GitHub access token is stored by Better Auth in the `account` table
(`provider_id = 'github'`); server code reads it via `getOctokit(userId)` in
`src/lib/github.ts`. OAuth-App tokens don't expire, so there's no refresh flow.

## Training launch

Merging to a project's default branch triggers a training run, end to end:

```
GitHub push → POST /api/github/webhook (raw-body HMAC) → start(trainingLaunch)
  → Vercel Sandbox (python3.13): pip install "wandb[sandbox]", run launcher.py
  → launcher.py starts a W&B Sandbox running the project's trainCommand
  → project.status = 'training'; training metrics flow back via the library reporter
```

Required env / setup:

- `GITHUB_WEBHOOK_SECRET` — shared secret for the push webhook. The webhook is
  created **automatically at project creation** (Octokit, on the user's repo),
  so the secret must be set before any project is created. The route validates
  `x-hub-signature-256` over the exact raw bytes and 401s on mismatch.
- `BETTER_AUTH_URL` — must be the **public** dashboard URL. It is passed into the
  W&B sandbox as `KEEPALIVE_API_URL` so the keepalive library inside the training
  run can POST events back to `/api/v1/events`.
- Each user must set their **W&B API key in Settings** (`user.wandbApiKey`). It
  authenticates both the W&B Sandbox client and the training run's `wandb` login.
  A missing key (or missing GitHub token / project training key) surfaces as a
  readable `training.failed` event in the project feed — the launch never crashes
  the workflow.

Only pushes to `project.defaultBranch` launch training. Agent fix branches
(`keepalive/fix-*`) and branch deletions are ignored, so coding-agent PRs never
kick off a training run.

CPU-only on the serverless sandbox tier (GPU is roadmap); the demo trains a tiny
model. No `run` row is pre-created — the keepalive library inside the W&B sandbox
reports its own run id and the ingest path creates the run.
