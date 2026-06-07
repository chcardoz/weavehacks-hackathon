import { headers } from "next/headers"
import { NextResponse } from "next/server"
import { desc, eq, inArray, sql } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { agent, incident, project, run } from "@/db/schema"
import {
  type Incident,
  type IncidentStatus,
  parseLossHistory,
  type ProjectListItem,
  type ProjectStatus,
  type Run,
  type RunStatus,
} from "@/lib/observability-types"

export const dynamic = "force-dynamic"

const UNRESOLVED: IncidentStatus[] = ["detected", "hypothesizing", "fixing"]

function isoOrNull(value: Date | string | null): string | null {
  if (!value) return null
  return value instanceof Date ? value.toISOString() : value
}

type RunRow = typeof run.$inferSelect

function toRun(r: RunRow): Run {
  return {
    id: r.id,
    projectId: r.projectId,
    wandbRunId: r.wandbRunId,
    wandbUrl: r.wandbUrl,
    commitSha: r.commitSha,
    branch: r.branch,
    source: r.source as Run["source"] ?? "local",
    sandboxId: r.sandboxId,
    status: r.status as RunStatus,
    currentStep: r.currentStep,
    latestLoss: r.latestLoss,
    lossHistory: parseLossHistory(r.lossHistory),
    demoMode: r.demoMode ?? false,
    lastEventAt: isoOrNull(r.lastEventAt),
    lastScoredAt: isoOrNull(r.lastScoredAt),
    createdAt: isoOrNull(r.createdAt),
  }
}

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  const projects = await db
    .select()
    .from(project)
    .where(eq(project.userId, session.user.id))
    .orderBy(desc(project.updatedAt), desc(project.createdAt))

  const projectIds = projects.map((p) => p.id)

  // Latest run per project.
  const latestRunByProject = new Map<string, RunRow>()
  if (projectIds.length > 0) {
    const runs = await db
      .select()
      .from(run)
      .where(inArray(run.projectId, projectIds))
      .orderBy(desc(run.createdAt))
    for (const r of runs) {
      if (!latestRunByProject.has(r.projectId)) {
        latestRunByProject.set(r.projectId, r)
      }
    }
  }

  // Newest unresolved incident per project + count of agents fixing it.
  const incidents =
    projectIds.length > 0
      ? await db
          .select()
          .from(incident)
          .where(inArray(incident.status, UNRESOLVED))
          .orderBy(desc(incident.createdAt))
      : []

  const activeByProject = new Map<string, typeof incidents[number]>()
  for (const inc of incidents) {
    if (
      projectIds.includes(inc.projectId) &&
      !activeByProject.has(inc.projectId)
    ) {
      activeByProject.set(inc.projectId, inc)
    }
  }

  const activeIds = [...activeByProject.values()].map((i) => i.id)
  const fixingCounts = new Map<string, number>()
  if (activeIds.length > 0) {
    const rows = await db
      .select({
        incidentId: agent.incidentId,
        count: sql<number>`count(*)::int`,
      })
      .from(agent)
      .where(inArray(agent.incidentId, activeIds))
      .groupBy(agent.incidentId)
    for (const r of rows) fixingCounts.set(r.incidentId, r.count)
  }

  const items: ProjectListItem[] = projects.map((p) => {
    const inc = activeByProject.get(p.id)
    const activeIncident: Incident | null = inc
      ? {
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
          createdAt: isoOrNull(inc.createdAt) ?? new Date(0).toISOString(),
        }
      : null
    const latestRunRow = latestRunByProject.get(p.id)
    return {
      id: p.id,
      userId: p.userId,
      name: p.name,
      repoOwner: p.repoOwner,
      repoName: p.repoName,
      defaultBranch: p.defaultBranch,
      webhookId: p.webhookId,
      trainCommand: p.trainCommand,
      monitoringPrompt: p.monitoringPrompt,
      fixingPrompt: p.fixingPrompt,
      confidenceThreshold: p.confidenceThreshold,
      maxAgents: p.maxAgents,
      monitorModel: p.monitorModel,
      status: p.status as ProjectStatus,
      createdAt: isoOrNull(p.createdAt),
      updatedAt: isoOrNull(p.updatedAt),
      latestRun: latestRunRow ? toRun(latestRunRow) : null,
      activeIncident,
      fixingAgentCount: inc ? (fixingCounts.get(inc.id) ?? 0) : 0,
    }
  })

  return NextResponse.json({ projects: items })
}
