import { db } from "@/lib/db"
import { event } from "@/db/schema"

// Append-only event feed writer. Imported by the ingest route, the fixing
// pipeline, and the GitHub webhook. Keep `EmitEventArgs` stable — it is a
// cross-workspace contract.

export type EventLevel = "info" | "warn" | "error"

export interface EmitEventArgs {
  projectId: string
  runId?: string | null
  incidentId?: string | null
  agentId?: string | null
  source: string // library|server|monitor|hypothesis|coder|sandbox|github
  level?: EventLevel
  type: string
  message: string
  data?: unknown
}

function toRow(args: EmitEventArgs) {
  return {
    projectId: args.projectId,
    runId: args.runId ?? null,
    incidentId: args.incidentId ?? null,
    agentId: args.agentId ?? null,
    source: args.source,
    level: args.level ?? "info",
    type: args.type,
    message: args.message,
    data: (args.data ?? null) as unknown,
  }
}

/** Inserts one `event` row. Never throws — a logging failure must not break the
 *  caller's hot path. */
export async function emitEvent(args: EmitEventArgs): Promise<void> {
  try {
    await db.insert(event).values(toRow(args))
  } catch (err) {
    console.error("[server-events] emitEvent failed:", err)
  }
}

/** Inserts a batch of `event` rows in a single statement. No-op on empty input;
 *  never throws. */
export async function emitEvents(batch: EmitEventArgs[]): Promise<void> {
  if (batch.length === 0) return
  try {
    await db.insert(event).values(batch.map(toRow))
  } catch (err) {
    console.error("[server-events] emitEvents failed:", err)
  }
}
