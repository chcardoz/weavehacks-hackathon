import { headers } from "next/headers"
import { NextResponse, type NextRequest } from "next/server"
import { eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { searchMemorySemantic } from "@/lib/memory/semantic"
import { incident, memory, project } from "@/db/schema"

export const dynamic = "force-dynamic"

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  const { id } = await ctx.params

  // Load the incident + its project, verifying ownership (404 otherwise).
  const [row] = await db
    .select({
      incidentId: incident.id,
      kind: incident.kind,
      reasoning: incident.reasoning,
      projectId: project.id,
      userId: project.userId,
    })
    .from(incident)
    .innerJoin(project, eq(incident.projectId, project.id))
    .where(eq(incident.id, id))
    .limit(1)

  if (!row || row.userId !== session.user.id) {
    return NextResponse.json({ error: "not_found" }, { status: 404 })
  }

  const query =
    [row.kind, row.reasoning].filter(Boolean).join(" — ") || "training failure"

  const hits = await searchMemorySemantic(row.projectId, query, 3)

  if (hits === null) {
    return NextResponse.json({ available: false, hits: [] })
  }

  // Exclude any hit that is a memory row belonging to THIS incident.
  const ownMemoryRows = await db
    .select({ id: memory.id })
    .from(memory)
    .where(eq(memory.incidentId, id))
  const ownIds = new Set(ownMemoryRows.map((m) => m.id))

  const filtered = hits.filter((h) => !ownIds.has(h.id))

  return NextResponse.json({ available: true, hits: filtered })
}
