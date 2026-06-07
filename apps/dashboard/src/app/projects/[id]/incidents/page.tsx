import { headers } from "next/headers"
import { notFound, redirect } from "next/navigation"
import { desc, eq, inArray } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { agent, incident } from "@/db/schema"
import { getOwnedProject } from "@/lib/server/projects"
import {
  type AgentRow,
  type AgentState,
  type Incident,
  type IncidentStatus,
} from "@/lib/observability-types"
import { IncidentsTable } from "./incidents-table"

function isoOrNull(value: Date | string | null): string | null {
  if (!value) return null
  return value instanceof Date ? value.toISOString() : value
}

export default async function IncidentsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) redirect("/sign-in")

  const { id } = await params
  const proj = await getOwnedProject(id, session.user.id)
  if (!proj) notFound()

  const incidentRows = await db
    .select()
    .from(incident)
    .where(eq(incident.projectId, id))
    .orderBy(desc(incident.createdAt))

  const incidentIds = incidentRows.map((i) => i.id)
  const agentRows =
    incidentIds.length > 0
      ? await db
          .select()
          .from(agent)
          .where(inArray(agent.incidentId, incidentIds))
          .orderBy(agent.createdAt)
      : []

  const incidents: Incident[] = incidentRows.map((i) => ({
    id: i.id,
    projectId: i.projectId,
    runId: i.runId,
    kind: i.kind,
    step: i.step,
    status: i.status as IncidentStatus,
    confidence: i.confidence,
    reasoning: i.reasoning,
    diagnosis: i.diagnosis,
    workflowRunId: i.workflowRunId,
    weaveUrl: i.weaveUrl,
    winnerAgentId: i.winnerAgentId,
    resolvedAt: isoOrNull(i.resolvedAt),
    createdAt: isoOrNull(i.createdAt) ?? new Date(0).toISOString(),
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

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Incidents</h1>
      <IncidentsTable incidents={incidents} agents={agents} />
    </div>
  )
}
