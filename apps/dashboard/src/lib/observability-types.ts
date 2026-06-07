// Shared types + pure helpers for the observability UI.
// See infra/observability.md for the contract.

export type ProjectStatus =
  | "training"
  | "incident"
  | "awaiting_human"
  | "racing"
  | "recovered"
  | "stopped"

export type IncidentStatus =
  | "detected"
  | "diagnosing"
  | "awaiting_human"
  | "racing"
  | "resolved"
  | "stopped"

export type AgentState =
  | "spawned"
  | "writing"
  | "branch_pushed"
  | "running"
  | "finished"
  | "winner"
  | "killed"
  | "failed"

export type EventSource =
  | "library"
  | "relay"
  | "cursor"
  | "sandbox"
  | "openai"
  | "wandb"

export type EventLevel = "info" | "warn" | "error"

export type CommandType =
  | "inject_nan"
  | "inject_divergence"
  | "inject_stall"
  | "inject_oom"

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
  name: string
  repo: string | null
  wandbRunId: string | null
  wandbUrl: string | null
  commitSha: string | null
  status: ProjectStatus
  currentStep: number | null
  latestLoss: number | null
  lossHistory: LossPoint[]
  demoMode: boolean
  lastEventAt: string | null
}

// /api/projects list item: project + a little derived context.
export interface ProjectListItem extends Project {
  activeIncident: Incident | null
  racingAgentCount: number
}

export interface Incident {
  id: string
  projectId: string
  kind: string
  step: number | null
  status: IncidentStatus
  diagnosis: string | null
  humanReply: string | null
  deadlineAt: string | null
  weaveUrl: string | null
  winnerAgentId: string | null
  resolvedAt: string | null
  createdAt: string
}

export interface AgentRow {
  id: string
  incidentId: string
  projectId: string
  hypothesis: string | null
  cursorAgentId: string | null
  branch: string | null
  state: AgentState
  wandbRunId: string | null
  finalLoss: number | null
  lossHistory: LossPoint[]
  error: string | null
}

export interface EventRow {
  id: number
  projectId: string
  incidentId: string | null
  agentId: string | null
  source: EventSource
  level: EventLevel
  type: string
  message: string
  data: unknown
  createdAt: string
}

export interface ProjectDetail {
  project: Project
  incidents: Incident[]
  agents: AgentRow[]
  events: EventRow[]
}

// --- pure helpers (unit tested) ---

const RESOLVED_INCIDENT_STATUSES: IncidentStatus[] = ["resolved", "stopped"]

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
    case "training":
      return { dot: "bg-emerald-500", text: "text-emerald-400" }
    case "incident":
      return { dot: "bg-red-500", text: "text-red-400" }
    case "awaiting_human":
      return { dot: "bg-amber-500", text: "text-amber-400" }
    case "racing":
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
export function agentStateTone(state: AgentState | string): {
  variant: BadgeTone
  className: string
} {
  switch (state) {
    case "spawned":
    case "writing":
      return { variant: "muted", className: "" }
    case "branch_pushed":
      return {
        variant: "muted",
        className: "bg-sky-500/15 text-sky-400 border-transparent",
      }
    case "running":
      return {
        variant: "muted",
        className:
          "bg-primary/15 text-primary border-transparent animate-pulse",
      }
    case "finished":
      return {
        variant: "muted",
        className: "bg-emerald-500/15 text-emerald-400 border-transparent",
      }
    case "winner":
      return { variant: "default", className: "" }
    case "killed":
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
    case "relay":
      return "bg-sky-500/10 text-sky-400"
    case "cursor":
      return "bg-primary/10 text-primary"
    case "sandbox":
      return "bg-violet-500/10 text-violet-400"
    case "openai":
      return "bg-teal-500/10 text-teal-400"
    case "wandb":
      return "bg-amber-500/10 text-amber-400"
    default:
      return "bg-muted text-muted-foreground"
  }
}

export function eventLevelClass(level: EventLevel | string): string {
  if (level === "warn") return "text-amber-400"
  if (level === "error") return "text-red-400"
  return "text-foreground"
}

// "mm:ss" until the deadline, or "expired". deadlineAt is ISO; now is ms epoch.
export function formatCountdown(
  deadlineAt: string | null,
  now: number = Date.now(),
): string {
  if (!deadlineAt) return "—"
  const target = new Date(deadlineAt).getTime()
  if (Number.isNaN(target)) return "—"
  const remainingMs = target - now
  if (remainingMs <= 0) return "expired"
  const totalSeconds = Math.floor(remainingMs / 1000)
  const mm = Math.floor(totalSeconds / 60)
  const ss = totalSeconds % 60
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`
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

// Human-readable reply mapping (1/2/3 → action). Reply may also be free text.
export function humanReplyLabel(reply: string | null): string | null {
  if (!reply) return null
  switch (reply.trim()) {
    case "1":
      return "rolled back"
    case "2":
      return "apply fix"
    case "3":
      return "stop"
    default:
      return reply
  }
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
    case "training":
      return "training"
    case "incident":
    case "awaiting_human":
      return item.activeIncident?.kind ?? "incident"
    case "racing":
      return "racing"
    case "recovered":
      return "recovered"
    case "stopped":
      return "stopped"
    default:
      return item.status
  }
}
