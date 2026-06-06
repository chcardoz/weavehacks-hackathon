# keepalive build tasks

Recovery protocol after context loss: read CLAUDE.md (= AGENTS.md), then `git log --oneline`,
then this file. Checkboxes below are updated by the top-level agent after each commit.
Only the top-level agent commits (conventional commits). Subagents never commit, never run
servers; unit tests only get run by the top-level agent in Phase 3.

## Phases

- [x] Phase 0 — scaffold: uv/pnpm workspaces, ruff/pyright config, types.py + config.py contracts
- [x] Phase 1 — parallel code writing (8 subagents, disjoint dirs, NO tests, NO commits):
  - [x] 1a detect/ + events.py + tracing.py
  - [x] 1b diagnose/
  - [x] 1c escalate/ + memory/
  - [x] 1d probes/
  - [x] 1e watchdog.py + cli.py + __init__.py
  - [x] 1f apps/api
  - [x] 1g apps/dashboard
  - [x] 1h docs/ + infra/ + .github/workflows
- [x] Phase 2 — reconciliation (fixed race() on_update callback shape), committed per area
- [x] Phase 3 — test writing: 164 python tests (library + api) + dashboard vitest
- [x] Phase 4 — pytest 164 passed; ruff check + format clean; pyright 0 errors
- [x] Phase 5 — pnpm install; oxlint 0/0; oxfmt clean; vitest 4 passed; tsc clean
- [x] Phase 6 — final TASKS.md update + report

## State at handoff (2026-06-06)

All code written and unit-verified. NOT yet done (deliberately left for humans):
integration testing against real wandb/OpenAI/Cursor/Twilio/Redis, running the api/dashboard
servers, Neon `pnpm db:generate && db:migrate`, deployments (see infra/), demo training
script + fault injector, W&B Sandbox hour-one smoke test (infra/wandb-sandboxes.md).

Known soft spots to verify live:
- SandboxExecutor resolves wandb Sandbox exec method defensively (public preview API undocumented)
- Cursor REST response shapes parsed defensively (branch under target.branchName / branchName / git.branches)
- better-auth show-once field assumed `data.key` on apiKey.create; delete param assumed `keyId` (tsc-checked)
- agent-memory-server docker image name flagged "verify at event" in infra/redis.md
- Watchdog stall detection in-process is heartbeat()-driven (no background thread); CLI mode polls idle_check

Deliberately deferred to humans: integration testing, running servers, demo script, deployments.

## Interface contract (source of truth: packages/keepalive/src/keepalive/types.py + config.py)

All cross-module types live in `keepalive.types` (FailureKind, IncidentStatus, HumanReply,
ProbeState, MetricSnapshot, FailureEvent, RunContext, FixHypothesis, Diagnosis, ProbeSpec,
ProbeResult, Incident, Detector, ProbeExecutor, KeepaliveStop/Rollback/HandedOff, new_id).
Settings = `keepalive.config.Settings` (frozen dataclass, `Settings.from_env()`).

### keepalive.detect
- `rules.NaNLossDetector(loss_key="loss")`, `rules.DivergenceDetector(loss_key="loss", window=20, factor=2.5, min_history=20)` — implement Detector protocol
- `rules.StallDetector(timeout_s=300.0)` — `.check_idle(now: float, last: MetricSnapshot | None) -> FailureEvent | None`
- `rules.scan_logline(line: str, step: int = -1) -> FailureEvent | None` — OOM/exception regexes for stderr tails
- `rules.DetectorSuite(detectors=None, stall=None, max_history=2000)` — `.observe(snapshot) -> FailureEvent | None`, `.idle_check(now=None) -> FailureEvent | None`, `.history: list[MetricSnapshot]`
- `monitor.MetricHook(suite, on_failure)` — `.install(run)` (patches run.log), `.uninstall()`
- `monitor.HistoryPoller(run_path, api=None, loss_key="loss")` — `.poll() -> list[MetricSnapshot]` (wandb public API scan_history(min_step=cursor), re-fetch api.run per poll)

### keepalive.events
- `EventBus(redis_client, stream="keepalive:events", group="keepalive")` — `.publish(event_type: str, payload: dict) -> str`, `.ensure_group()`, `.consume(consumer="watchdog", count=10, block_ms=1000) -> list[tuple[str, dict]]`, `.ack(*ids)` (Streams + consumer groups, NOT pub/sub)

### keepalive.tracing
- `init_tracing(project: str) -> bool` (weave.init, never raises), `traced(fn=None, *, name=None)` (weave.op if available else identity), `incident_attributes(incident)` ctx manager, `current_trace_url() -> str | None`

### keepalive.diagnose
- `tools.RunDataFetcher(ctx: RunContext, api=None)` — `.get_run_history(keys=None, last_n=50)`, `.get_logs(tail=100)`, `.get_config()`
- `engine.DiagnosisEngine(settings, client=None, recall=None, cache=None)` — `.diagnose(incident, fetcher) -> Diagnosis`; OpenAI chat tool-loop, final tool `submit_diagnosis`; ≤ settings.max_probes hypotheses; recall: callable(FailureEvent) -> list[str]; cache: get(str)->str|None / set(str,str)

### keepalive.escalate
- `client.EscalationClient(settings, http=None)` — `.notify_incident(incident, voice_note_url=None) -> None` (POST {api_url}/v1/notify, Bearer api_key), `.fetch_reply(incident_id) -> HumanReply | None` (GET /v1/incidents/{id}/reply), `.send_recap(incident, message) -> None`, `.upload_voice_note(incident_id, mp3: bytes) -> str` (POST /v1/voice-notes → absolute url)
- `voice.VoiceNoteBuilder(settings, client=None)` — `.script_for(incident) -> str`, `.synthesize(text) -> bytes` (openai audio.speech → mp3)
- `deadline.DeadlineClock(redis_client, key="keepalive:deadlines")` — `.arm(incident_id, timeout_s) -> float`, `.due(now=None) -> list[str]`, `.disarm(incident_id)`, `.await_human(incident_id, fetch_reply, poll_interval=2.0, now_fn=time.time, sleep_fn=time.sleep) -> HumanReply | None` (None = deadline expired → authority transfers)

### keepalive.memory
- `incidents.IncidentMemory(settings, client=None)` — `.remember(incident, resolution: str)`, `.recall(failure: FailureEvent) -> list[str]`, `.available: bool` (agent-memory-client; graceful no-op without it)
- `router.SignalRouter(redis_url, router=None)` — `.classify(text) -> str | None` (RedisVL SemanticRouter; routes: divergence/thermal/dataloader/oom; graceful None)
- `cache.DiagnosisCache(redis_url, cache=None)` — `.get(prompt) -> str | None`, `.set(prompt, response)` (RedisVL SemanticCache; graceful no-op)

### keepalive.probes
- `cursor.CursorClient(settings, http=None)` — `.spawn_probe(hypothesis, ctx, incident_id) -> ProbeSpec` (POST {cursor_api_url}/v1/agents, startingRef=ctx.commit_sha, branch cursor/probe-{spec.id}), `.wait_for_branch(spec, timeout_s=None, poll_s=5.0, sleep_fn=time.sleep) -> ProbeSpec`, `.cancel(spec)`; `cursor.IntegrationNotConnectedError`; ladder cursor_sdk → cursor_agent_sdk → REST(httpx)
- `sandbox.SandboxExecutor(settings, session_factory=None)` — ProbeExecutor on wandb.sandbox.Sandbox
- `local.LocalExecutor(settings, repo_root=None)` — ProbeExecutor via git worktree + subprocess
- `executor.race(specs, executor, ctx, *, steps, on_update=None) -> tuple[ProbeResult | None, list[ProbeResult]]` (ThreadPoolExecutor; winner via judge; kill losers)
- `judge.pick_winner(results, loss_key="loss") -> ProbeResult | None` (argmin finite final_loss among FINISHED), `judge.summarize(results) -> str`
- Probe wandb runs: separate runs, `group=f"watchdog-{ctx.run_id}"`, `job_type="probe"`, name=spec.id; helper `judge.fetch_probe_metrics(run_path, api=None, loss_key="loss") -> tuple[float | None, list[MetricSnapshot]]`

### keepalive.watchdog / cli / __init__
- `Watchdog(run=None, settings=None, *, executor=None, suite=None, engine=None, escalation=None, deadline=None, memory_=None, router=None, bus=None, cursor=None, checkpoint_dir="checkpoints", timeout=None, escalate=("sms",), loss_key=None, entrypoint=None)`
- `Watchdog.handle_failure(event: FailureEvent) -> None` — full incident flow; raises KeepaliveStop/KeepaliveRollback/KeepaliveHandedOff
- `keepalive.watchdog(...)` contextmanager wrapping Watchdog (door 1); `cli.app` Typer with `keepalive run -- python train.py` (door 2, stderr tail + HistoryPoller)
- `__init__` exports: watchdog, Watchdog, Settings, all public types, __version__

### apps/api (keepalive_api)
- FastAPI; Bearer ka_live_ keys, sha256 lookup in Postgres `apikey` table (Better Auth schema) with `KEEPALIVE_DEV_KEYS` env fallback
- POST /v1/notify {incident_id, kind: incident|recap, message, voice_note_url?, trace_url?, to_phone} → Twilio SMS; maps phone→incident in Redis (`active:{phone}`)
- POST /sms — Twilio inbound webhook (form), validate X-Twilio-Signature, Body 1/2/3 → Redis `reply:{incident_id}`
- GET /v1/incidents/{id}/reply → {"reply": "1"|"2"|"3"|null}
- POST /v1/voice-notes (bytes + incident_id) → Redis (TTL) → {"url": "/a/{id}"}; GET /a/{id} HTML audio page; GET /a/{id}.mp3 Content-Type audio/mpeg

### apps/dashboard
- Next.js App Router + Better Auth api-key plugin (prefix ka_live_) + drizzle/Neon + shadcn/ui; create/show-once/revoke keys; oxlint + oxfmt + vitest; pnpm

## Conventions
- No comments/docstrings unless genuinely non-obvious; full type hints; ruff line-length 120 (double quotes); lazy imports for heavy/optional deps (wandb, weave, redisvl, agent_memory_client, cursor_sdk); every external client injectable for tests; redis vectors stay bytes (no decode_responses on vector clients)
