import { eq } from "drizzle-orm"
import { db } from "@/lib/db"
import { project } from "@/db/schema"

export type ProjectRow = typeof project.$inferSelect

// Fetch a project owned by `userId`, or null if missing / not owned.
export async function getOwnedProject(
  projectId: string,
  userId: string,
): Promise<ProjectRow | null> {
  const [row] = await db
    .select()
    .from(project)
    .where(eq(project.id, projectId))
    .limit(1)
  if (!row || row.userId !== userId) return null
  return row
}
