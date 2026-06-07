import { NextResponse } from "next/server"
import { and, eq } from "drizzle-orm"

import { authenticateApiKey } from "@/lib/api-auth"
import { db } from "@/lib/db"
import { command, project } from "@/db/schema"

export const dynamic = "force-dynamic"

// GET /api/v1/projects/{projectId}/commands
// Bearer ka_live_ auth; the project must belong to the key's user. Atomically
// consumes all pending commands (UPDATE ... WHERE status='pending' RETURNING).
export async function GET(
  request: Request,
  ctx: { params: Promise<{ projectId: string }> },
) {
  const identity = await authenticateApiKey(request)
  if (!identity) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  const { projectId } = await ctx.params

  const [owned] = await db
    .select({ id: project.id })
    .from(project)
    .where(and(eq(project.id, projectId), eq(project.userId, identity.userId)))
    .limit(1)
  if (!owned) {
    return NextResponse.json({ error: "not_found" }, { status: 404 })
  }

  const consumed = await db
    .update(command)
    .set({ status: "consumed", consumedAt: new Date() })
    .where(
      and(eq(command.projectId, projectId), eq(command.status, "pending")),
    )
    .returning({
      id: command.id,
      type: command.type,
      createdAt: command.createdAt,
    })

  return NextResponse.json({
    commands: consumed.map((c) => ({
      id: c.id,
      type: c.type,
      created_at: c.createdAt,
    })),
  })
}
