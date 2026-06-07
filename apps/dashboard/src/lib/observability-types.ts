// Shared types + pure helpers for the observability UI.
// See infra/architecture-v2.md for the v2 contract (status vocabularies, sources).

export type ProjectStatus = "idle" | "training" | "incident" | "fixing" | "recovered" | "stopped"

export type RunStatus = "training" | "incident" | "fixing" | "recovered" | "stopped" | "finished"

export type IncidentStatus = "detected" | "hypothesizing" | "fixing" | "resolved" | "failed"

export type AgentState = "spawned" | "coding" | "pushed" | "pr_opened" | "failed"

export type EventSource = "library" | "server" | "monitor" | "hypothesis" | "coder" | "sandbox" | "github"

export type EventLevel = "info" | "warn" | "error"

// Library-emitted event types (the only ones the client sends).
export type LibraryEventType = "run.started" | "run.heartbeat" | "run.stopped" | "incident.detected" | "log"

// Server-emitted event types (workflows + monitor).
export type ServerEventType = "monitor.scored" | "incident.created" | "hypothesis.generated" | "agent.spawned" | "agent.coding" | "agent.pushed" | "agent.pr_opened" | "agent.failed" | "incident.resolved" | "incident.failed" | "training.launched"

export type CommandType = "inject_nan" | "inject_divergence" | "inject_stall" | "inject_oom"

export const COMMAND_TYPES: CommandType[] = [
  "inject_nan",
  "inject_divergence",
  "inject_stall",
  "inject_oom",
]

export interface LossPoint {
  step: number
  loss: number
}

export interface Project {
  id: string
  userId: string
  name: string
  repoOwner: string
  repoName: string
  defaultBranch: string
  webhookId: number | null
  trainCommand: string
  monitoringPrompt: string | null
  fixingPrompt: string | null
  confidenceThreshold: number
  maxAgents: number
  monitorModel: string
  status: ProjectStatus
  createdAt: string | null
  updatedAt: string | null
}

export interface Run {
  id: string
  projectId: string
  wandbRunId: string | null
  wandbUrl: string | null
  commitSha: string | null
  branch: string | null
  source: "local" | "sandbox"
  sandboxId: string | null
  status: RunStatus
  currentStep: number | null
  latestLoss: number | null
  lossHistory: LossPoint[]
  demoMode: boolean
  lastEventAt: string | null
  lastScoredAt: string | null
  createdAt: string | null
}

// /api/projects list item: project + a little derived context.
export interface ProjectListItem extends Project {
  latestRun: Run | null
  activeIncident: Incident | null
  fixingAgentCount: number
}

export interface Incident {
  id: string
  projectId: string
  runId: string
  kind: string | null
  step: number | null
  status: IncidentStatus
  confidence: number | null
  reasoning: string | null
  diagnosis: string | null
  workflowRunId: string | null
  weaveUrl: string | null
  winnerAgentId: string | null
  resolvedAt: string | null
  createdAt: string
}

export interface AgentRow {
  id: string
  incidentId: string
  projectId: string
  hypothesis: string
  branch: string | null
  prUrl: string | null
  prNumber: number | null
  state: AgentState
  report: string | null
  sandboxId: string | null
  error: string | null
}

export interface EventRow {
  id: number
  projectId: string
  runId: string | null
  incidentId: string | null
  agentId: string | null
  source: EventSource
  level: EventLevel
  type: string
  message: string
  data: unknown
  createdAt: string
}

export interface MemoryRow {
  id: string
  projectId: string
  incidentId: string | null
  kind: string | null
  summary: string
  resolution: string | null
  data: unknown
  createdAt: string
}

export interface ProjectDetail {
  project: Project
  latestRun: Run | null
  incidents: Incident[]
  agents: AgentRow[]
  events: EventRow[]
}

// --- pure helpers (unit tested) ---

const RESOLVED_INCIDENT_STATUSES: IncidentStatus[] = ["resolved", "failed"]

export function isIncidentResolved(status: IncidentStatus | string): boolean {
  return (RESOLVED_INCIDENT_STATUSES as string[]).includes(status)
}

// Tailwind text/color tokens for each project status.
export type StatusTone = {
  dot: string // bg-* class for the status dot
  text: string // text-* class
}

export function projectStatusTone(status: ProjectStatus | string): StatusTone {
  switch (status) {
    case "idle":
      return { dot: "bg-muted-foreground", text: "text-muted-foreground" }
    case "training":
      return { dot: "bg-emerald-500", text: "text-emerald-400" }
    case "incident":
      return { dot: "bg-red-500", text: "text-red-400" }
    case "fixing":
      return { dot: "bg-primary", text: "text-primary" }
    case "recovered":
      return { dot: "bg-sky-500", text: "text-sky-400" }
    case "stopped":
      return { dot: "bg-muted-foreground", text: "text-muted-foreground" }
    default:
      return { dot: "bg-muted-foreground", text: "text-muted-foreground" }
  }
}

export type BadgeTone = "default" | "muted" | "destructive"

// Maps an agent state to a shadcn Badge variant + extra classes.
export function agentStateTone(
  state: AgentState | string,
): {
  variant: BadgeTone
  className: string
} {
  switch (state) {
    case "spawned":
      return { variant: "muted", className: "" }
    case "coding":
      return {
        variant: "muted",
        className:
          "bg-primary/15 text-primary border-transparent animate-pulse",
      }
    case "pushed":
      return {
        variant: "muted",
        className: "bg-sky-500/15 text-sky-400 border-transparent",
      }
    case "pr_opened":
      return {
        variant: "muted",
        className: "bg-emerald-500/15 text-emerald-400 border-transparent",
      }
    case "failed":
      return { variant: "destructive", className: "" }
    default:
      return { variant: "muted", className: "" }
  }
}

// Maps an incident status to a shadcn Badge variant + extra classes.
export function incidentStatusTone(status: IncidentStatus | string): {
  variant: BadgeTone
  className: string
} {
  switch (status) {
    case "detected":
      return {
        variant: "muted",
        className: "bg-red-500/15 text-red-400 border-transparent",
      }
    case "hypothesizing":
      return {
        variant: "muted",
        className:
          "bg-primary/15 text-primary border-transparent animate-pulse",
      }
    case "fixing":
      return {
        variant: "muted",
        className: "bg-amber-500/15 text-amber-400 border-transparent",
      }
    case "resolved":
      return {
        variant: "muted",
        className: "bg-emerald-500/15 text-emerald-400 border-transparent",
      }
    case "failed":
      return { variant: "destructive", className: "" }
    default:
      return { variant: "muted", className: "" }
  }
}

// Maps an event source to a muted hued badge class.
export function eventSourceClass(source: EventSource | string): string {
  switch (source) {
    case "library":
      return "bg-emerald-500/10 text-emerald-400"
    case "server":
      return "bg-sky-500/10 text-sky-400"
    case "monitor":
      return "bg-teal-500/10 text-teal-400"
    case "hypothesis":
      return "bg-primary/10 text-primary"
    case "coder":
      return "bg-violet-500/10 text-violet-400"
    case "sandbox":
      return "bg-amber-500/10 text-amber-400"
    case "github":
      return "bg-foreground/10 text-foreground"
    default:
      return "bg-muted text-muted-foreground"
  }
}

export function eventLevelClass(level: EventLevel | string): string {
  if (level === "warn") return "text-amber-400"
  if (level === "error") return "text-red-400"
  return "text-foreground"
}

// "Xs ago" / "Xm ago" / "Xh ago" from an ISO timestamp.
export function formatRelative(
  iso: string | null,
  now: number = Date.now(),
): string {
  if (!iso) return "—"
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return "—"
  const deltaSec = Math.max(0, Math.floor((now - then) / 1000))
  if (deltaSec < 60) return `${deltaSec}s ago`
  const min = Math.floor(deltaSec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const days = Math.floor(hr / 24)
  return `${days}d ago`
}

// Parse a jsonb loss_history (unknown) into validated points, defensively.
export function parseLossHistory(value: unknown): LossPoint[] {
  if (!Array.isArray(value)) return []
  const out: LossPoint[] = []
  for (const item of value) {
    if (item && typeof item === "object") {
      const rec = item as Record<string, unknown>
      const step = rec.step
      const loss = rec.loss
      if (typeof step === "number" && typeof loss === "number") {
        if (Number.isFinite(step) && Number.isFinite(loss)) {
          out.push({ step, loss })
        }
      }
    }
  }
  return out
}

// Build an SVG polyline points string from loss points, fit to a box.
// Pure + testable. Returns "" when there is nothing to draw.
export function sparklinePoints(
  points: LossPoint[],
  width: number,
  height: number,
  pad = 2,
): string {
  if (points.length === 0) return ""
  if (points.length === 1) {
    const y = (height / 2).toFixed(2)
    const x0 = pad.toFixed(2)
    const x1 = (width - pad).toFixed(2)
    return `${x0},${y} ${x1},${y}`
  }
  const losses = points.map((p) => p.loss)
  const min = Math.min(...losses)
  const max = Math.max(...losses)
  const span = max - min || 1
  const innerW = width - pad * 2
  const innerH = height - pad * 2
  const n = points.length - 1
  return points
    .map((p, i) => {
      const x = pad + (innerW * i) / n
      // higher loss → higher up the chart looks wrong; invert so low loss = bottom
      const y = pad + innerH * (1 - (p.loss - min) / span)
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(" ")
}

// One-line label describing what a project is doing right now.
export function projectActivityKind(item: ProjectListItem): string {
  switch (item.status) {
    case "idle":
      return "idle"
    case "training":
      return "training"
    case "incident":
      return item.activeIncident?.kind ?? "incident"
    case "fixing":
      return "fixing"
    case "recovered":
      return "recovered"
    case "stopped":
      return "stopped"
    default:
      return item.status
  }
}
