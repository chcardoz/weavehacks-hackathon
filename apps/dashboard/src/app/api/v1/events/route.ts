import { NextResponse } from "next/server"
import { and, desc, eq } from "drizzle-orm"
import { start } from "workflow/api"

import { authenticateApiKey } from "@/lib/api-auth"
import { db } from "@/lib/db"
import { incident, project, run } from "@/db/schema"
import { emitEvent } from "@/lib/server-events"
import {
  DEFAULT_MONITORING_PROMPT,
  flushTraces,
  initWeave,
  scoreMetrics,
  type MetricsWindowEntry,
} from "@/lib/ai"
import {
  applyHeartbeat,
  isIncidentOpen,
  type MetricsEntry,
} from "@/lib/ingest/effects"
// Authored in parallel by the workflows agent. Signature: fixingPipeline(incidentId).
import { fixingPipeline } from "@/workflows/fixing-pipeline"

export const dynamic = "force-dynamic"

const MAX_BATCH = 100
const SCORE_INTERVAL_MS = 20_000

interface ProjectBlock {
  name?: string
  repo_owner?: string
  repo_name?: string
  branch?: string
  commit_sha?: string
  wandb_run_id?: string
  wandb_url?: string
  demo_mode?: boolean
  monitoring_prompt?: string
  threshold?: number
  max_agents?: number
}

interface EventItem {
  project_id?: string // library run-scoped id → run.id
  project?: ProjectBlock
  incident_id?: string
  agent_id?: string
  source?: string
  level?: "info" | "warn" | "error"
  type?: string
  message?: string
  data?: unknown
}

function asString(v: unknown): string | undefined {
  return typeof v === "string" && v.length > 0 ? v : undefined
}

function genId(): string {
  return crypto.randomUUID()
}

type ProjectRow = typeof project.$inferSelect
type RunRow = typeof run.$inferSelect

// --- project / run resolution ---------------------------------------------

async function resolveProject(
  userId: string,
  block: ProjectBlock | undefined,
): Promise<ProjectRow> {
  const repoOwner = asString(block?.repo_owner)
  const repoName = asString(block?.repo_name)

  if (repoOwner && repoName) {
    const [existing] = await db
      .select()
      .from(project)
      .where(
        and(
          eq(project.userId, userId),
          eq(project.repoOwner, repoOwner),
          eq(project.repoName, repoName),
        ),
      )
      .limit(1)
    if (existing) {
      await backfillProject(existing, block)
      return existing
    }

    const [created] = await db
      .insert(project)
      .values({
        id: genId(),
        userId,
        name: asString(block?.name) ?? `${repoOwner}/${repoName}`,
        repoOwner,
        repoName,
        monitoringPrompt: asString(block?.monitoring_prompt) ?? null,
        confidenceThreshold:
          typeof block?.threshold === "number" ? block.threshold : undefined,
        maxAgents:
          typeof block?.max_agents === "number" ? block.max_agents : undefined,
      })
      .returning()
    return created
  }

  // No repo info → fall back to a per-user "default" project so ingest never drops.
  const [existingDefault] = await db
    .select()
    .from(project)
    .where(
      and(
        eq(project.userId, userId),
        eq(project.repoOwner, ""),
        eq(project.repoName, ""),
      ),
    )
    .limit(1)
  if (existingDefault) return existingDefault

  const [createdDefault] = await db
    .insert(project)
    .values({
      id: genId(),
      userId,
      name: "default",
      repoOwner: "",
      repoName: "",
    })
    .returning()
  return createdDefault
}

// Library values fill columns ONLY when the project columns are null (dashboard wins).
async function backfillProject(
  row: ProjectRow,
  block: ProjectBlock | undefined,
): Promise<void> {
  const patch: Partial<typeof project.$inferInsert> = {}
  if (row.monitoringPrompt == null && asString(block?.monitoring_prompt)) {
    patch.monitoringPrompt = block?.monitoring_prompt
  }
  // threshold/maxAgents are NOT NULL with DB defaults; only override if still default.
  if (typeof block?.threshold === "number" && row.confidenceThreshold === 0.6) {
    patch.confidenceThreshold = block.threshold
  }
  if (typeof block?.max_agents === "number" && row.maxAgents === 3) {
    patch.maxAgents = block.max_agents
  }
  if (Object.keys(patch).length > 0) {
    await db.update(project).set(patch).where(eq(project.id, row.id))
  }
}

async function resolveRun(
  runId: string,
  projectId: string,
  block: ProjectBlock | undefined,
): Promise<RunRow> {
  const [existing] = await db
    .select()
    .from(run)
    .where(eq(run.id, runId))
    .limit(1)
  if (existing) return existing

  const source =
    asString(process.env.KEEPALIVE_RUN_SOURCE) === "sandbox"
      ? "sandbox"
      : "local"

  const [created] = await db
    .insert(run)
    .values({
      id: runId,
      projectId,
      wandbRunId: asString(block?.wandb_run_id) ?? null,
      wandbUrl: asString(block?.wandb_url) ?? null,
      commitSha: asString(block?.commit_sha) ?? null,
      branch: asString(block?.branch) ?? null,
      source,
      demoMode: block?.demo_mode === true,
    })
    .returning()
  return created
}

// --- open-incident lookup --------------------------------------------------

async function findOpenIncident(runId: string): Promise<string | null> {
  const [row] = await db
    .select({ id: incident.id, status: incident.status })
    .from(incident)
    .where(eq(incident.runId, runId))
    .orderBy(desc(incident.createdAt))
    .limit(1)
  if (row && isIncidentOpen(row.status)) return row.id
  return null
}

// --- pipeline trigger ------------------------------------------------------

async function triggerPipeline(
  incidentId: string,
  projectId: string,
  runId: string,
): Promise<void> {
  try {
    const wfRun = await start(fixingPipeline, [incidentId])
    await db
      .update(incident)
      .set({ workflowRunId: wfRun.runId })
      .where(eq(incident.id, incidentId))
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    await emitEvent({
      projectId,
      runId,
      incidentId,
      source: "server",
      level: "warn",
      type: "pipeline.start_failed",
      message: `failed to start fixing pipeline: ${msg}`,
    })
  }
}

async function createIncident(args: {
  projectId: string
  runId: string
  kind: string
  step: number | null
  confidence?: number | null
  reasoning?: string | null
  id?: string
}): Promise<string> {
  const id = args.id ?? genId()
  await db.insert(incident).values({
    id,
    projectId: args.projectId,
    runId: args.runId,
    kind: args.kind,
    step: args.step,
    status: "detected",
    confidence: args.confidence ?? null,
    reasoning: args.reasoning ?? null,
  })
  await db
    .update(run)
    .set({ status: "incident" })
    .where(eq(run.id, args.runId))
  await db
    .update(project)
    .set({ status: "incident" })
    .where(eq(project.id, args.projectId))
  return id
}

// --- monitoring agent hook -------------------------------------------------

async function runMonitor(
  projectRow: ProjectRow,
  runRow: RunRow,
): Promise<void> {
  const metricsWindow = (
    Array.isArray(runRow.metricsWindow) ? runRow.metricsWindow : []
  ) as MetricsEntry[]
  if (metricsWindow.length === 0) return

  await db
    .update(run)
    .set({ lastScoredAt: new Date() })
    .where(eq(run.id, runRow.id))

  const monitoringPrompt =
    projectRow.monitoringPrompt ?? DEFAULT_MONITORING_PROMPT

  const verdict = await scoreMetrics({
    monitorModel: projectRow.monitorModel,
    monitoringPrompt,
    metricsWindow: metricsWindow as MetricsWindowEntry[],
    projectId: projectRow.id,
    runId: runRow.id,
  })

  await emitEvent({
    projectId: projectRow.id,
    runId: runRow.id,
    source: "monitor",
    type: "monitor.scored",
    message: verdict.reasoning,
    data: {
      confidence: verdict.confidence,
      reasoning: verdict.reasoning,
      signals: verdict.signals,
    },
  })

  if (verdict.confidence < projectRow.confidenceThreshold) {
    const incidentId = await createIncident({
      projectId: projectRow.id,
      runId: runRow.id,
      kind: "monitor_flag",
      step: runRow.currentStep ?? null,
      confidence: verdict.confidence,
      reasoning: verdict.reasoning,
    })
    await emitEvent({
      projectId: projectRow.id,
      runId: runRow.id,
      incidentId,
      source: "monitor",
      level: "warn",
      type: "incident.created",
      message: `monitor flagged run (confidence ${verdict.confidence.toFixed(2)})`,
      data: { kind: "monitor_flag", confidence: verdict.confidence },
    })
    await triggerPipeline(incidentId, projectRow.id, runRow.id)
  }
}

// --- route -----------------------------------------------------------------

export async function POST(request: Request) {
  const identity = await authenticateApiKey(request)
  if (!identity) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  // Ensure the Weave client exists for this invocation (idempotent; the
  // instrumentation hook normally covers cold starts, this is belt-and-braces
  // for the demo-critical monitoring path).
  await initWeave()

  let body: unknown
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 })
  }

  const events = (body as { events?: unknown } | null)?.events
  if (!Array.isArray(events)) {
    return NextResponse.json({ error: "missing_events" }, { status: 400 })
  }
  if (events.length > MAX_BATCH) {
    return NextResponse.json(
      { error: "too_many_events", max: MAX_BATCH },
      { status: 400 },
    )
  }

  // The batch shares one library run-scoped id + project block. Resolve once
  // from the first item; fall back to the per-user default project otherwise.
  const items = events as EventItem[]
  const first = items[0] ?? {}
  const projectRow = await resolveProject(identity.userId, first.project)

  const runId = asString(first.project_id)
  let runRow: RunRow | null = runId
    ? await resolveRun(runId, projectRow.id, first.project)
    : null

  let sawHeartbeat = false
  let heartbeatRunId: string | null = null

  for (const item of items) {
    const type = asString(item.type) ?? "log"
    const data = item.data
    const targetRunId = runRow?.id ?? null

    // Always insert the event row.
    await emitEvent({
      projectId: projectRow.id,
      runId: targetRunId,
      incidentId: asString(item.incident_id) ?? null,
      agentId: asString(item.agent_id) ?? null,
      source: asString(item.source) ?? "library",
      level: item.level ?? "info",
      type,
      message: asString(item.message) ?? type,
      data,
    })

    if (!runRow) continue

    switch (type) {
      case "run.started": {
        await db
          .update(run)
          .set({ status: "training", lastEventAt: new Date() })
          .where(eq(run.id, runRow.id))
        await db
          .update(project)
          .set({ status: "training" })
          .where(eq(project.id, projectRow.id))
        runRow = { ...runRow, status: "training" }
        break
      }
      case "run.heartbeat": {
        const upd = applyHeartbeat(
          data,
          runRow.lossHistory,
          runRow.metricsWindow,
        )
        await db
          .update(run)
          .set({
            currentStep: upd.currentStep ?? runRow.currentStep,
            latestLoss: upd.latestLoss ?? runRow.latestLoss,
            lossHistory: upd.lossHistory,
            metricsWindow: upd.metricsWindow,
            lastEventAt: new Date(),
          })
          .where(eq(run.id, runRow.id))
        runRow = {
          ...runRow,
          currentStep: upd.currentStep ?? runRow.currentStep,
          latestLoss: upd.latestLoss ?? runRow.latestLoss,
          lossHistory: upd.lossHistory,
          metricsWindow: upd.metricsWindow,
        }
        sawHeartbeat = true
        heartbeatRunId = runRow.id
        break
      }
      case "run.stopped": {
        await db
          .update(run)
          .set({ status: "stopped", lastEventAt: new Date() })
          .where(eq(run.id, runRow.id))
        const open = await findOpenIncident(runRow.id)
        if (!open) {
          await db
            .update(project)
            .set({ status: "stopped" })
            .where(eq(project.id, projectRow.id))
        }
        runRow = { ...runRow, status: "stopped" }
        break
      }
      case "incident.detected": {
        const open = await findOpenIncident(runRow.id)
        if (!open) {
          const d = (data ?? {}) as Record<string, unknown>
          const incidentId = await createIncident({
            projectId: projectRow.id,
            runId: runRow.id,
            kind: asString(d.kind) ?? "exception",
            step: typeof d.step === "number" ? d.step : null,
            id: asString(item.incident_id),
          })
          runRow = { ...runRow, status: "incident" }
          await triggerPipeline(incidentId, projectRow.id, runRow.id)
        }
        break
      }
      default:
        // unknown types → event row only (already inserted).
        break
    }
  }

  // Monitoring agent hook: only when we got heartbeats, the run is training,
  // it's been > SCORE_INTERVAL_MS since the last score, and no open incident.
  if (sawHeartbeat && runRow && heartbeatRunId === runRow.id) {
    try {
      const lastScored = runRow.lastScoredAt
        ? new Date(runRow.lastScoredAt).getTime()
        : 0
      const due = Date.now() - lastScored > SCORE_INTERVAL_MS
      if (runRow.status === "training" && due) {
        const open = await findOpenIncident(runRow.id)
        if (!open) {
          await runMonitor(projectRow, runRow)
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      await emitEvent({
        projectId: projectRow.id,
        runId: runRow.id,
        source: "monitor",
        level: "warn",
        type: "monitor.failed",
        message: `monitor hook failed: ${msg}`,
      })
    }
  }

  await flushTraces()

  return NextResponse.json({
    accepted: items.length,
    project_id: projectRow.id,
    run_id: runRow?.id ?? null,
  })
}
