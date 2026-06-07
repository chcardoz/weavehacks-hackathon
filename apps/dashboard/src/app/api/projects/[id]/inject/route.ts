import { headers } from "next/headers"
import { NextResponse, type NextRequest } from "next/server"
import { desc, eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { command, incident, project } from "@/db/schema"
import {
  COMMAND_TYPES,
  type CommandType,
  isIncidentResolved,
} from "@/lib/observability-types"

export const dynamic = "force-dynamic"

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  const { id } = await ctx.params

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 })
  }

  const type = (body as { type?: unknown } | null)?.type
  if (
    typeof type !== "string" ||
    !(COMMAND_TYPES as string[]).includes(type)
  ) {
    return NextResponse.json(
      { error: "invalid_type", allowed: COMMAND_TYPES },
      { status: 400 },
    )
  }

  const [projectRow] = await db
    .select({ id: project.id })
    .from(project)
    .where(eq(project.id, id))
    .limit(1)
  if (!projectRow) {
    return NextResponse.json({ error: "not_found" }, { status: 404 })
  }

  // Reject if the newest incident is unresolved. Allowed if there is no incident.
  const [newest] = await db
    .select({ status: incident.status })
    .from(incident)
    .where(eq(incident.projectId, id))
    .orderBy(desc(incident.createdAt))
    .limit(1)

  if (newest && !isIncidentResolved(newest.status)) {
    return NextResponse.json(
      { error: "incident_in_progress" },
      { status: 409 },
    )
  }

  await db.insert(command).values({
    id: crypto.randomUUID(),
    projectId: id,
    type: type as CommandType,
    status: "pending",
  })

  return NextResponse.json({ ok: true })
}
