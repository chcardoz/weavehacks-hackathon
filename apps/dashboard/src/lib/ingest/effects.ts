// Pure helpers for the /api/v1/events ingest path: history capping and
// heartbeat → run-column derivation. No drizzle, no I/O — unit tested.

export const LOSS_HISTORY_CAP = 120
export const METRICS_WINDOW_CAP = 40

export interface LossPoint {
  step: number
  loss: number
}

export interface MetricsEntry {
  step: number
  metrics: Record<string, unknown>
}

/** Appends `item` to `list` (defensively coerced to an array) and caps to `cap`
 *  most-recent entries. Returns a new array; never mutates the input. */
export function appendCapped<T>(
  existing: unknown,
  item: T,
  cap: number,
): T[] {
  const arr = Array.isArray(existing) ? (existing.slice() as T[]) : []
  arr.push(item)
  if (arr.length > cap) {
    return arr.slice(arr.length - cap)
  }
  return arr
}

/** Pulls a finite numeric loss out of a heartbeat `data` blob.
 *  Looks at `data.loss` then `data.metrics.loss`. Returns null when absent. */
export function extractLoss(data: unknown): number | null {
  if (!data || typeof data !== "object") return null
  const rec = data as Record<string, unknown>
  if (typeof rec.loss === "number" && Number.isFinite(rec.loss)) {
    return rec.loss
  }
  const metrics = rec.metrics
  if (metrics && typeof metrics === "object") {
    const m = (metrics as Record<string, unknown>).loss
    if (typeof m === "number" && Number.isFinite(m)) return m
  }
  return null
}

/** Pulls an integer step out of a `data` blob. Returns null when absent. */
export function extractStep(data: unknown): number | null {
  if (!data || typeof data !== "object") return null
  const step = (data as Record<string, unknown>).step
  if (typeof step === "number" && Number.isFinite(step)) {
    return Math.trunc(step)
  }
  return null
}

/** The full metrics dict from a heartbeat `data` blob (the monitor's input). */
export function extractMetrics(data: unknown): Record<string, unknown> {
  if (!data || typeof data !== "object") return {}
  const metrics = (data as Record<string, unknown>).metrics
  if (metrics && typeof metrics === "object") {
    return metrics as Record<string, unknown>
  }
  return {}
}

export interface HeartbeatUpdate {
  currentStep: number | null
  latestLoss: number | null
  lossHistory: LossPoint[]
  metricsWindow: MetricsEntry[]
}

/** Computes the next run columns for a `run.heartbeat` event given the prior
 *  jsonb history values. Pure — the route does the DB write. */
export function applyHeartbeat(
  data: unknown,
  prevLossHistory: unknown,
  prevMetricsWindow: unknown,
): HeartbeatUpdate {
  const step = extractStep(data)
  const loss = extractLoss(data)
  const metrics = extractMetrics(data)

  let lossHistory: LossPoint[]
  if (step !== null && loss !== null) {
    lossHistory = appendCapped(
      prevLossHistory,
      { step, loss },
      LOSS_HISTORY_CAP,
    )
  } else {
    lossHistory = Array.isArray(prevLossHistory)
      ? (prevLossHistory as LossPoint[])
      : []
  }

  let metricsWindow: MetricsEntry[]
  if (step !== null && Object.keys(metrics).length > 0) {
    metricsWindow = appendCapped(
      prevMetricsWindow,
      { step, metrics },
      METRICS_WINDOW_CAP,
    )
  } else {
    metricsWindow = Array.isArray(prevMetricsWindow)
      ? (prevMetricsWindow as MetricsEntry[])
      : []
  }

  return {
    currentStep: step,
    latestLoss: loss,
    lossHistory,
    metricsWindow,
  }
}

// Incident statuses that mean "still open" — a run may not start a new pipeline
// while one of these is in flight.
const OPEN_INCIDENT_STATUSES = new Set(["detected", "hypothesizing", "fixing"])

export function isIncidentOpen(status: string): boolean {
  return OPEN_INCIDENT_STATUSES.has(status)
}
