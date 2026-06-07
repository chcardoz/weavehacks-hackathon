import { headers } from "next/headers"
import { NextResponse } from "next/server"
import { desc, inArray, sql } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { agent, incident, project } from "@/db/schema"
import {
  type Incident,
  type IncidentStatus,
  type LossPoint,
  parseLossHistory,
  type ProjectListItem,
  type ProjectStatus,
} from "@/lib/observability-types"

export const dynamic = "force-dynamic"

const UNRESOLVED: IncidentStatus[] = [
  "detected",
  "diagnosing",
  "awaiting_human",
  "racing",
]

function isoOrNull(value: Date | string | null): string | null {
  if (!value) return null
  return value instanceof Date ? value.toISOString() : value
}

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  const projects = await db
    .select()
    .from(project)
    .orderBy(desc(project.lastEventAt), desc(project.createdAt))

  // Newest unresolved incident per project + count of agents racing for it.
  const incidents = await db
    .select()
    .from(incident)
    .where(inArray(incident.status, UNRESOLVED))
    .orderBy(desc(incident.createdAt))

  const activeByProject = new Map<string, typeof incidents[number]>()
  for (const inc of incidents) {
    if (!activeByProject.has(inc.projectId)) {
      activeByProject.set(inc.projectId, inc)
    }
  }

  const activeIds = [...activeByProject.values()].map((i) => i.id)
  const racingCounts = new Map<string, number>()
  if (activeIds.length > 0) {
    const rows = await db
      .select({
        incidentId: agent.incidentId,
        count: sql<number>`count(*)::int`,
      })
      .from(agent)
      .where(inArray(agent.incidentId, activeIds))
      .groupBy(agent.incidentId)
    for (const r of rows) racingCounts.set(r.incidentId, r.count)
  }

  const items: ProjectListItem[] = projects.map((p) => {
    const inc = activeByProject.get(p.id)
    const activeIncident: Incident | null = inc
      ? {
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
          createdAt: isoOrNull(inc.createdAt) ?? new Date(0).toISOString(),
        }
      : null
    const lossHistory: LossPoint[] = parseLossHistory(p.lossHistory)
    return {
      id: p.id,
      name: p.name,
      repo: p.repo,
      wandbRunId: p.wandbRunId,
      wandbUrl: p.wandbUrl,
      commitSha: p.commitSha,
      status: p.status as ProjectStatus,
      currentStep: p.currentStep,
      latestLoss: p.latestLoss,
      lossHistory,
      demoMode: p.demoMode ?? false,
      lastEventAt: isoOrNull(p.lastEventAt),
      activeIncident,
      racingAgentCount: inc ? racingCounts.get(inc.id) ?? 0 : 0,
    }
  })

  return NextResponse.json({ projects: items })
}
