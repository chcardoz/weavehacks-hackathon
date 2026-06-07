import { headers } from "next/headers"
import { notFound, redirect } from "next/navigation"
import { desc, eq } from "drizzle-orm"
import { Brain } from "lucide-react"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { memory } from "@/db/schema"
import { getOwnedProject } from "@/lib/server/projects"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/components/ui/card"

function fmtDateTime(value: Date | string | null): string {
  if (!value) return "—"
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export default async function MemoryPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) redirect("/sign-in")

  const { id } = await params
  const proj = await getOwnedProject(id, session.user.id)
  if (!proj) notFound()

  const rows = await db
    .select()
    .from(memory)
    .where(eq(memory.projectId, id))
    .orderBy(desc(memory.createdAt))

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Memory</h1>
        <p className="text-sm text-muted-foreground">
          What keepalive learned from past incidents. The hypothesis agent
          searches these before proposing fixes.
        </p>
      </div>

      {rows.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-muted/20 p-10 text-center">
          <Brain className="size-7 text-muted-foreground" />
          <p className="max-w-md text-sm text-muted-foreground">
            No memories yet. After the first incident is resolved, keepalive
            records what happened and what fixed it — and the hypothesis agent
            recalls it next time.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((m) => (
            <Card key={m.id}>
              <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
                <div className="flex items-center gap-2">
                  {m.kind && <Badge variant="muted">{m.kind}</Badge>}
                </div>
                <span className="text-xs text-muted-foreground">
                  {fmtDateTime(m.createdAt)}
                </span>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <p className="whitespace-pre-wrap">{m.summary}</p>
                {m.resolution && (
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground">
                      Resolution:{" "}
                    </span>
                    {m.resolution}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
