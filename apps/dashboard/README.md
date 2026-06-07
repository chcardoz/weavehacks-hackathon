# keepalive dashboard

Sign in, then issue / show-once / revoke `ka_live_` API keys, and watch your
training runs live on `/projects` (incident lifecycle, probe agents, unified
logs, demo fault injection — contract in `../../infra/observability.md`).
Next.js 15 (App Router) + Better Auth (api-key plugin) + drizzle-orm on Neon
Postgres + Tailwind v4.

## Setup

```bash
pnpm install
cp .env.example .env.local   # then fill in the values
```

Required env vars (see `.env.example`):

- `DATABASE_URL` — Neon Postgres pooled connection string
- `BETTER_AUTH_SECRET` — 32+ char secret (`openssl rand -base64 32`)
- `BETTER_AUTH_URL` — e.g. `http://localhost:3000`
- `NEXT_PUBLIC_APP_URL` — e.g. `http://localhost:3000`

## Database schema push (REQUIRED)

You MUST push the schema before the app works. Without it the `apikey` table
(and the core auth tables) will not exist and every request fails:

```bash
DATABASE_URL="<neon connection string>" pnpm db:push   # drizzle-kit push
```

Prefer Neon's **unpooled** connection string for DDL. Heads-up:
`@better-auth/cli migrate` does NOT work here — it only supports the built-in
Kysely adapter and this app uses the drizzle adapter; `db:push` is the working
path. `pnpm db:generate` only regenerates the Better Auth portion of
`src/db/schema.ts` after plugin changes. The schema also holds the
observability tables (`project`/`incident`/`agent`/`event`/`command`) shared
with the relay — contract in `../../infra/observability.md`.

## Develop

```bash
pnpm dev      # http://localhost:3000
pnpm lint     # oxlint
pnpm fmt      # oxfmt
pnpm test     # vitest (tests added separately)
```

## Deploy

Vercel. See `../../infra/vercel.md` for project setup, env vars, and the Neon
integration.
