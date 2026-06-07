import { describe, expect, it } from "vitest"

import {
  appendCapped,
  applyHeartbeat,
  extractLoss,
  extractMetrics,
  extractStep,
  isIncidentOpen,
  LOSS_HISTORY_CAP,
  METRICS_WINDOW_CAP,
} from "./effects"

describe("appendCapped", () => {
  it("appends to a missing/non-array base", () => {
    expect(appendCapped(undefined, 1, 5)).toEqual([1])
    expect(appendCapped(null, 1, 5)).toEqual([1])
    expect(appendCapped("nope", 1, 5)).toEqual([1])
  })

  it("keeps only the last `cap` entries", () => {
    const base = [1, 2, 3]
    expect(appendCapped(base, 4, 3)).toEqual([2, 3, 4])
  })

  it("does not mutate the input array", () => {
    const base = [1, 2]
    appendCapped(base, 3, 10)
    expect(base).toEqual([1, 2])
  })
})

describe("extractLoss", () => {
  it("reads data.loss first", () => {
    expect(extractLoss({ loss: 0.5 })).toBe(0.5)
  })
  it("falls back to data.metrics.loss", () => {
    expect(extractLoss({ metrics: { loss: 1.25 } })).toBe(1.25)
  })
  it("ignores non-finite / missing", () => {
    expect(extractLoss({ loss: NaN })).toBeNull()
    expect(extractLoss({ loss: Infinity })).toBeNull()
    expect(extractLoss({})).toBeNull()
    expect(extractLoss(null)).toBeNull()
    expect(extractLoss("x")).toBeNull()
  })
})

describe("extractStep", () => {
  it("truncates finite steps", () => {
    expect(extractStep({ step: 400 })).toBe(400)
    expect(extractStep({ step: 12.9 })).toBe(12)
  })
  it("returns null when absent or non-finite", () => {
    expect(extractStep({})).toBeNull()
    expect(extractStep({ step: NaN })).toBeNull()
    expect(extractStep(undefined)).toBeNull()
  })
})

describe("extractMetrics", () => {
  it("returns the metrics dict", () => {
    expect(extractMetrics({ metrics: { loss: 1, lr: 0.01 } })).toEqual({
      loss: 1,
      lr: 0.01,
    })
  })
  it("returns {} when absent", () => {
    expect(extractMetrics({})).toEqual({})
    expect(extractMetrics(null)).toEqual({})
  })
})

describe("applyHeartbeat", () => {
  it("appends a loss point + metrics entry", () => {
    const out = applyHeartbeat(
      { step: 10, loss: 0.4, metrics: { loss: 0.4, grad_norm: 2 } },
      [{ step: 9, loss: 0.5 }],
      [{ step: 9, metrics: { loss: 0.5 } }],
    )
    expect(out.currentStep).toBe(10)
    expect(out.latestLoss).toBe(0.4)
    expect(out.lossHistory).toEqual([
      { step: 9, loss: 0.5 },
      { step: 10, loss: 0.4 },
    ])
    expect(out.metricsWindow).toHaveLength(2)
    expect(out.metricsWindow[1]).toEqual({
      step: 10,
      metrics: { loss: 0.4, grad_norm: 2 },
    })
  })

  it("derives loss from metrics.loss when top-level loss is missing", () => {
    const out = applyHeartbeat({ step: 5, metrics: { loss: 1.1 } }, [], [])
    expect(out.latestLoss).toBe(1.1)
    expect(out.lossHistory).toEqual([{ step: 5, loss: 1.1 }])
  })

  it("does not append loss history when loss is absent", () => {
    const out = applyHeartbeat(
      { step: 5, metrics: { lr: 0.01 } },
      [{ step: 4, loss: 0.9 }],
      [],
    )
    expect(out.lossHistory).toEqual([{ step: 4, loss: 0.9 }])
    // metrics present → window still grows
    expect(out.metricsWindow).toEqual([{ step: 5, metrics: { lr: 0.01 } }])
  })

  it("caps history at the documented limits", () => {
    const longLoss = Array.from({ length: LOSS_HISTORY_CAP + 5 }, (_, i) => ({
      step: i,
      loss: i,
    }))
    const longWin = Array.from(
      { length: METRICS_WINDOW_CAP + 5 },
      (_, i) => ({ step: i, metrics: { loss: i } }),
    )
    const out = applyHeartbeat(
      { step: 999, loss: 0.1, metrics: { loss: 0.1 } },
      longLoss,
      longWin,
    )
    expect(out.lossHistory).toHaveLength(LOSS_HISTORY_CAP)
    expect(out.metricsWindow).toHaveLength(METRICS_WINDOW_CAP)
    expect(out.lossHistory[out.lossHistory.length - 1]).toEqual({
      step: 999,
      loss: 0.1,
    })
  })
})

describe("isIncidentOpen", () => {
  it("treats in-flight statuses as open", () => {
    expect(isIncidentOpen("detected")).toBe(true)
    expect(isIncidentOpen("hypothesizing")).toBe(true)
    expect(isIncidentOpen("fixing")).toBe(true)
  })
  it("treats terminal statuses as closed", () => {
    expect(isIncidentOpen("resolved")).toBe(false)
    expect(isIncidentOpen("failed")).toBe(false)
    expect(isIncidentOpen("whatever")).toBe(false)
  })
})
