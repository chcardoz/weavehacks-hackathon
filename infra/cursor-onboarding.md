# Cursor onboarding — probe code writers

Probes are written by Cursor cloud agents (Cursor's VMs, CPU-only, no GPUs). They only
write code: each agent branches from the failing run's exact commit SHA and pushes a
`cursor/probe-*` branch. They never run training. This is what each keepalive user does
once.

## The 4-step user chain

1. **Paid Cursor plan.** Cloud agents are **not** on the free tier.
2. **Install the Cursor GitHub App.** Dashboard → Integrations → Connect GitHub. Grant the
   training repo (read-write; private repos OK).
3. **Issue a user API key** at `cursor.com/dashboard/api`. It must be a **user** key, NOT a
   service-account key — service-account keys can't use `envVars`. Set it as
   `CURSOR_API_KEY`.
4. keepalive passes `repos[].url` + `startingRef=<failing commit SHA>` (captured at watchdog
   start via `git rev-parse HEAD`; W&B records it too).

If the repo isn't connected, the SDK raises `IntegrationNotConnectedError` — the remedy is
to connect it at Dashboard → Integrations.

## Gotchas (from the doc deep-dives)

- **User key, not service-account.** Service-account keys can't set `envVars`, which probes
  need.
- **One active run per agent.** Parallelism comes from spawning **many agents**, not many
  runs per agent.
- **`agentId` vs `envVars` are mutually exclusive.** Idempotent `agentId` UUIDs are nice,
  but incompatible with `envVars` — we pick `envVars`.
- **`/v1/repositories` is rate-limited to 1/min.** Cache the result.
- **No webhooks in v1.** Poll the run object, or use SSE `/stream`. The branch / PR comes
  from `git.branches` on the run object.
- **Cloud VMs are CPU-only**, internet on by default.
- **Commits are signed by the Cursor bot identity** — expect bot-authored commits on the
  `cursor/probe-*` branches.

## SDK fallback ladder

The library tries, in order: official `cursor_sdk` → community `cursor_agent_sdk` → raw
REST (`https://api.cursor.com/v1/agents`).
