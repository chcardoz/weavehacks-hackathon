# keepalive dashboard

Sign in, then issue / show-once / revoke `ka_live_` API keys. Next.js 15 (App
Router) + Better Auth (api-key plugin) + drizzle-orm on Neon Postgres + Tailwind
v4.

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

## Database migration (REQUIRED)

You MUST run the Better Auth migration before the app works. Without it the
`apikey` table (and the core auth tables) will not exist and every request fails:

```bash
pnpm db:generate   # @better-auth/cli generate — writes the schema
pnpm db:migrate    # @better-auth/cli migrate — applies it to Neon
```

The drizzle schema in `src/db/schema.ts` mirrors the Better Auth core tables plus
the api-key plugin's `apikey` table; keep them in sync if you change plugins.

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
