# Observability contract — events, commands, and the dashboard data plane

> **⚠️ Superseded (June 7 pivot):** `infra/architecture-v2.md` is now the binding
> contract. The FastAPI relay (`apps/api`) is deleted — ingest lives at
> `apps/dashboard` `POST /api/v1/events`, and the schema moved to v2 (repo-level
> `project`, `incident`, `agent`, `memory`). This doc is kept for the event-shape
> history only.

How the dashboard's `/projects` pages get live data, and how demo fault-injection
commands flow back to the library. Three parties code against this spec:

- **Library** (`packages/keepalive`): emits events, polls commands (demo mode only).
- **Relay** (`apps/api`): ingests events into Postgres, serves commands, self-logs.
- **Dashboard** (`apps/dashboard`): reads the tables via drizzle, inserts commands.

All five tables live in the shared Neon Postgres (same DB as `apikey`). Schema is
owned by `apps/dashboard/src/db/schema.ts` and pushed with `drizzle-kit push`; the
relay reads/writes them with asyncpg.

## Tables

| Table | Purpose | Key columns |
| ----- | ------- | ----------- |
| `project` | one watched training run | `id` (text pk, library-chosen, e.g. wandb run id), `name`, `repo`, `wandb_run_id`, `wandb_url`, `commit_sha`, `status`, `current_step`, `latest_loss`, `loss_history` (jsonb `[{step,loss}]`, capped last ~60), `demo_mode`, `apikey_id`, `last_event_at` |
| `incident` | one failure lifecycle | `id` (text pk = library incident id), `project_id`, `kind`, `step`, `status`, `diagnosis`, `human_reply`, `deadline_at`, `weave_url`, `winner_agent_id`, `resolved_at` |
| `agent` | one probe (Cursor agent + sandbox run) | `id` (text pk = probe spec id), `incident_id`, `project_id`, `hypothesis`, `cursor_agent_id`, `branch`, `state`, `wandb_run_id`, `final_loss`, `loss_history` (jsonb), `error` |
| `event` | append-only log line | `id` (bigserial), `project_id`, `incident_id?`, `agent_id?`, `source`, `level`, `type`, `message`, `data` (jsonb), `created_at` |
| `command` | dashboard → library demo command | `id` (text pk, uuid), `project_id`, `type`, `status` (`pending`/`consumed`), `consumed_at` |

Status vocabularies:

- `project.status`: `training | incident | awaiting_human | racing | recovered | stopped`
- `incident.status`: `detected | diagnosing | awaiting_human | racing | resolved | stopped`
- `agent.state`: `spawned | writing | branch_pushed | running | finished | winner | killed | failed`
- `event.source`: `library | relay | cursor | sandbox | openai | wandb`
- `event.level`: `info | warn | error`
- `command.type`: `inject_nan | inject_divergence | inject_stall | inject_oom`

## POST /v1/events (relay, Bearer = `ka_live_` key)

Batch ingest. The relay ALWAYS appends each item to `event`, and additionally
applies the state effect listed below for recognized `type`s. Unknown types are
stored as plain log lines (forward compatible). Returns `{"accepted": N}`.

```json
{
  "events": [
    {
      "project_id": "run-a1b2c3",            // required on every item
      "project": {                            // optional; upserts project metadata
        "name": "nanogpt-shakespeare",
        "repo": "chcardoz/nanogpt",
        "wandb_run_id": "a1b2c3",
        "wandb_url": "https://wandb.ai/...",
        "commit_sha": "98ab5df",
        "demo_mode": true
      },
      "incident_id": "inc_0f3a",              // optional
      "agent_id": "probe-1",                  // optional
      "source": "library",
      "level": "info",
      "type": "incident.detected",
      "message": "NaN loss at step 400",
      "data": { "kind": "nan_loss", "step": 400 },
      "ts": "2026-06-07T01:54:02Z"            // optional; relay defaults to now()
    }
  ]
}
```

### Event types and their state effects

| `type` | emitted by | `data` | state effect |
| ------ | ---------- | ------ | ------------ |
| `run.started` | library | `{step?}` | upsert project, `status=training` |
| `run.heartbeat` | library | `{step, loss}` | project `current_step`, `latest_loss`, append `loss_history`, `last_event_at` |
| `run.stopped` | library | `{reason?}` | project `status=stopped` |
| `incident.detected` | library | `{kind, step}` | insert incident (`status=detected`), project `status=incident` |
| `incident.diagnosed` | library | `{diagnosis, hypotheses: [str]}` | incident `diagnosis`, `status=diagnosing` |
| `incident.escalated` | library | `{deadline_ts, weave_url?}` | incident `status=awaiting_human`, `deadline_at`, `weave_url`; project `status=awaiting_human` |
| `incident.human_reply` | library | `{reply: "1"\|"2"\|"3"}` | incident `human_reply` |
| `incident.deadline_expired` | library | `{}` | incident `status=racing`, project `status=racing` |
| `agent.spawned` | library | `{hypothesis, cursor_agent_id?}` | insert agent (`state=spawned`) |
| `agent.status` | library | `{state, branch?, cursor_agent_id?, wandb_run_id?, error?}` | update agent row from data |
| `agent.metrics` | library | `{step, loss}` or `{final_loss}` | append agent `loss_history`; set `final_loss` if present |
| `incident.promoted` | library | `{winner_agent_id, final_loss}` | incident `winner_agent_id`, `status=resolved`, `resolved_at`; project `status=recovered`; winner agent `state=winner` |
| `incident.stopped` | library | `{reason}` | incident `status=stopped`, project `status=stopped` |
| `log` | anyone | anything | none (log line only) |

Relay self-logged events (source=`relay`, type=`log` unless noted): telegram message
sent (`data.voice_sent`), webhook reply received (`incident.human_reply` with the
reply — the relay knows it first), LLM proxy call (`data.model`, `data.ms`). The
relay resolves `project_id` for webhook replies via the incident row.

## GET /v1/projects/{project_id}/commands (relay, Bearer = `ka_live_` key)

Returns pending commands for the project and atomically marks them consumed
(`UPDATE ... WHERE status='pending' RETURNING`):

```json
{ "commands": [ { "id": "uuid", "type": "inject_nan", "created_at": "..." } ] }
```

The library polls this every ~2s ONLY when demo mode is armed
(`KEEPALIVE_DEMO=1` env or `watchdog(..., demo_mode=True)`).

## Dashboard writes

`POST /api/projects/[id]/inject` (Next.js route, session-gated): body
`{"type": "inject_nan"}` → inserts a `command` row. Buttons disabled while the
project has an unresolved incident.

## Library emission rules

- Events are fire-and-forget: queued to a background thread, batched (flush every
  ~2s or 20 events), `try/except` everything — a dead relay must NEVER affect the
  training run or the incident pipeline.
- Reporter is on whenever `api_key` + `api_url` are configured; project identity
  comes from the wandb run (id/name/url) + `git rev-parse HEAD`.
- `run.heartbeat` at most every 5s (sampled from the metric hook).

## Fault injection (demo mode only)

`keepalive/demo.py` — `FaultInjector`, applied at the next step boundary inside
the metric hook:

- `inject_nan`: replace the loss value with NaN before detectors see it
- `inject_divergence`: multiply optimizer LRs by 100 (real divergence follows)
- `inject_stall`: sleep inside the hook past the stall detector window
- `inject_oom`: raise `RuntimeError("CUDA out of memory. (keepalive demo)")`

Never active unless explicitly armed. The injected fault produces a REAL failure
signal — everything downstream (detect → diagnose → escalate → probes) runs
unmodified.
