import { headers } from "next/headers"
import { NextResponse, type NextRequest } from "next/server"
import { and, asc, desc, eq, gt } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { agent, event, incident, project } from "@/db/schema"
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

  if (!projectRow) {
    return NextResponse.json({ error: "not_found" }, { status: 404 })
  }

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
    name: projectRow.name,
    repo: projectRow.repo,
    wandbRunId: projectRow.wandbRunId,
    wandbUrl: projectRow.wandbUrl,
    commitSha: projectRow.commitSha,
    status: projectRow.status as ProjectStatus,
    currentStep: projectRow.currentStep,
    latestLoss: projectRow.latestLoss,
    lossHistory: parseLossHistory(projectRow.lossHistory),
    demoMode: projectRow.demoMode ?? false,
    lastEventAt: isoOrNull(projectRow.lastEventAt),
  }

  const incidents: Incident[] = incidentRows.map((inc) => ({
    id: inc.id,
    projectId: inc.projectId,
    kind: inc.kind,
    step: inc.step,
    status: inc.status as IncidentStatus,
    diagnosis: inc.diagnosis,
    humanReply: inc.humanReply,
    deadlineAt: isoOrNull(inc.deadlineAt),
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
    cursorAgentId: a.cursorAgentId,
    branch: a.branch,
    state: a.state as AgentState,
    wandbRunId: a.wandbRunId,
    finalLoss: a.finalLoss,
    lossHistory: parseLossHistory(a.lossHistory),
    error: a.error,
  }))

  const events: EventRow[] = eventRows.map((e) => ({
    id: e.id,
    projectId: e.projectId,
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
    incidents,
    agents,
    events,
  })
}
