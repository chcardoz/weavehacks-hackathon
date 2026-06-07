import { headers } from "next/headers"
import { NextResponse, type NextRequest } from "next/server"
import { and, asc, desc, eq, gt } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { agent, event, incident, project, run } from "@/db/schema"
import {
  type AgentRow,
  type AgentState,
  type EventLevel,
  type EventRow,
  type EventSource,
  type Incident,
  type IncidentStatus,
  parseLossHistory,
  type Project,
  type ProjectStatus,
  type Run,
  type RunStatus,
} from "@/lib/observability-types"

export const dynamic = "force-dynamic"

const EVENT_PAGE_CAP = 500
const RECENT_EVENT_COUNT = 200

function isoOrNull(value: Date | string | null): string | null {
  if (!value) return null
  return value instanceof Date ? value.toISOString() : value
}

function iso(value: Date | string | null): string {
  return isoOrNull(value) ?? new Date(0).toISOString()
}

export async function GET(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  const { id } = await ctx.params

  const [projectRow] = await db
    .select()
    .from(project)
    .where(eq(project.id, id))
    .limit(1)

  if (!projectRow || projectRow.userId !== session.user.id) {
    return NextResponse.json({ error: "not_found" }, { status: 404 })
  }

  const [latestRunRow] = await db
    .select()
    .from(run)
    .where(eq(run.projectId, id))
    .orderBy(desc(run.createdAt))
    .limit(1)

  const incidentRows = await db
    .select()
    .from(incident)
    .where(eq(incident.projectId, id))
    .orderBy(desc(incident.createdAt))

  const newestIncident = incidentRows[0]
  const agentRows = newestIncident
    ? await db
        .select()
        .from(agent)
        .where(eq(agent.incidentId, newestIncident.id))
        .orderBy(asc(agent.createdAt))
    : []

  // Events: incremental (?after=) or the most recent page, always ascending.
  const afterParam = req.nextUrl.searchParams.get("after")
  const afterId =
    afterParam !== null && afterParam !== "" ? Number(afterParam) : null

  let eventRows
  if (afterId !== null && Number.isFinite(afterId)) {
    eventRows = await db
      .select()
      .from(event)
      .where(and(eq(event.projectId, id), gt(event.id, afterId)))
      .orderBy(asc(event.id))
      .limit(EVENT_PAGE_CAP)
  } else {
    const recent = await db
      .select()
      .from(event)
      .where(eq(event.projectId, id))
      .orderBy(desc(event.id))
      .limit(RECENT_EVENT_COUNT)
    eventRows = recent.reverse()
  }

  const projectOut: Project = {
    id: projectRow.id,
    userId: projectRow.userId,
    name: projectRow.name,
    repoOwner: projectRow.repoOwner,
    repoName: projectRow.repoName,
    defaultBranch: projectRow.defaultBranch,
    webhookId: projectRow.webhookId,
    trainCommand: projectRow.trainCommand,
    monitoringPrompt: projectRow.monitoringPrompt,
    fixingPrompt: projectRow.fixingPrompt,
    confidenceThreshold: projectRow.confidenceThreshold,
    maxAgents: projectRow.maxAgents,
    monitorModel: projectRow.monitorModel,
    status: projectRow.status as ProjectStatus,
    createdAt: isoOrNull(projectRow.createdAt),
    updatedAt: isoOrNull(projectRow.updatedAt),
  }

  const latestRun: Run | null = latestRunRow
    ? {
        id: latestRunRow.id,
        projectId: latestRunRow.projectId,
        wandbRunId: latestRunRow.wandbRunId,
        wandbUrl: latestRunRow.wandbUrl,
        commitSha: latestRunRow.commitSha,
        branch: latestRunRow.branch,
        source: latestRunRow.source as Run["source"] ?? "local",
        sandboxId: latestRunRow.sandboxId,
        status: latestRunRow.status as RunStatus,
        currentStep: latestRunRow.currentStep,
        latestLoss: latestRunRow.latestLoss,
        lossHistory: parseLossHistory(latestRunRow.lossHistory),
        demoMode: latestRunRow.demoMode ?? false,
        lastEventAt: isoOrNull(latestRunRow.lastEventAt),
        lastScoredAt: isoOrNull(latestRunRow.lastScoredAt),
        createdAt: isoOrNull(latestRunRow.createdAt),
      }
    : null

  const incidents: Incident[] = incidentRows.map((inc) => ({
    id: inc.id,
    projectId: inc.projectId,
    runId: inc.runId,
    kind: inc.kind,
    step: inc.step,
    status: inc.status as IncidentStatus,
    confidence: inc.confidence,
    reasoning: inc.reasoning,
    diagnosis: inc.diagnosis,
    workflowRunId: inc.workflowRunId,
    weaveUrl: inc.weaveUrl,
    winnerAgentId: inc.winnerAgentId,
    resolvedAt: isoOrNull(inc.resolvedAt),
    createdAt: iso(inc.createdAt),
  }))

  const agents: AgentRow[] = agentRows.map((a) => ({
    id: a.id,
    incidentId: a.incidentId,
    projectId: a.projectId,
    hypothesis: a.hypothesis,
    branch: a.branch,
    prUrl: a.prUrl,
    prNumber: a.prNumber,
    state: a.state as AgentState,
    report: a.report,
    sandboxId: a.sandboxId,
    error: a.error,
  }))

  const events: EventRow[] = eventRows.map((e) => ({
    id: e.id,
    projectId: e.projectId,
    runId: e.runId,
    incidentId: e.incidentId,
    agentId: e.agentId,
    source: e.source as EventSource,
    level: e.level as EventLevel,
    type: e.type,
    message: e.message,
    data: e.data,
    createdAt: iso(e.createdAt),
  }))

  return NextResponse.json({
    project: projectOut,
    latestRun,
    incidents,
    agents,
    events,
  })
}
