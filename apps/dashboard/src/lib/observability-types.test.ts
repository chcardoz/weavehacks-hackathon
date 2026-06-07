import { describe, expect, it } from "vitest"
import {
  agentStateTone,
  eventLevelClass,
  eventSourceClass,
  formatCountdown,
  formatRelative,
  humanReplyLabel,
  isIncidentResolved,
  parseLossHistory,
  projectStatusTone,
  sparklinePoints,
} from "./observability-types"

describe("isIncidentResolved", () => {
  it("treats resolved and stopped as resolved", () => {
    expect(isIncidentResolved("resolved")).toBe(true)
    expect(isIncidentResolved("stopped")).toBe(true)
  })
  it("treats live statuses as unresolved", () => {
    for (const s of ["detected", "diagnosing", "awaiting_human", "racing"]) {
      expect(isIncidentResolved(s)).toBe(false)
    }
  })
})

describe("projectStatusTone", () => {
  it("maps statuses to colors", () => {
    expect(projectStatusTone("training").dot).toBe("bg-emerald-500")
    expect(projectStatusTone("incident").dot).toBe("bg-red-500")
    expect(projectStatusTone("awaiting_human").dot).toBe("bg-amber-500")
    expect(projectStatusTone("racing").dot).toBe("bg-primary")
    expect(projectStatusTone("recovered").dot).toBe("bg-sky-500")
    expect(projectStatusTone("stopped").dot).toBe("bg-muted-foreground")
  })
  it("falls back for unknown status", () => {
    expect(projectStatusTone("???").dot).toBe("bg-muted-foreground")
  })
})

describe("agentStateTone", () => {
  it("running pulses, winner is default, failed is destructive", () => {
    expect(agentStateTone("running").className).toContain("animate-pulse")
    expect(agentStateTone("winner").variant).toBe("default")
    expect(agentStateTone("failed").variant).toBe("destructive")
    expect(agentStateTone("killed").variant).toBe("destructive")
    expect(agentStateTone("spawned").variant).toBe("muted")
  })
})

describe("event class helpers", () => {
  it("maps sources to hues", () => {
    expect(eventSourceClass("library")).toContain("emerald")
    expect(eventSourceClass("cursor")).toContain("primary")
    expect(eventSourceClass("unknown")).toContain("muted")
  })
  it("maps levels", () => {
    expect(eventLevelClass("warn")).toContain("amber")
    expect(eventLevelClass("error")).toContain("red")
    expect(eventLevelClass("info")).toBe("text-foreground")
  })
})

describe("formatCountdown", () => {
  const now = Date.parse("2026-06-07T00:00:00Z")
  it("returns mm:ss for a future deadline", () => {
    const dl = new Date(now + 65_000).toISOString()
    expect(formatCountdown(dl, now)).toBe("01:05")
  })
  it("pads single digits", () => {
    const dl = new Date(now + 5_000).toISOString()
    expect(formatCountdown(dl, now)).toBe("00:05")
  })
  it("returns expired when past", () => {
    const dl = new Date(now - 1000).toISOString()
    expect(formatCountdown(dl, now)).toBe("expired")
  })
  it("handles null and garbage", () => {
    expect(formatCountdown(null, now)).toBe("—")
    expect(formatCountdown("not-a-date", now)).toBe("—")
  })
})

describe("formatRelative", () => {
  const now = Date.parse("2026-06-07T01:00:00Z")
  it("seconds, minutes, hours, days", () => {
    expect(formatRelative(new Date(now - 5_000).toISOString(), now)).toBe(
      "5s ago",
    )
    expect(formatRelative(new Date(now - 120_000).toISOString(), now)).toBe(
      "2m ago",
    )
    expect(formatRelative(new Date(now - 7_200_000).toISOString(), now)).toBe(
      "2h ago",
    )
    expect(
      formatRelative(new Date(now - 2 * 86_400_000).toISOString(), now),
    ).toBe("2d ago")
  })
  it("handles null", () => {
    expect(formatRelative(null, now)).toBe("—")
  })
})

describe("parseLossHistory", () => {
  it("keeps valid numeric points", () => {
    const out = parseLossHistory([
      { step: 1, loss: 2.5 },
      { step: 2, loss: 1.1 },
    ])
    expect(out).toEqual([
      { step: 1, loss: 2.5 },
      { step: 2, loss: 1.1 },
    ])
  })
  it("drops malformed / non-finite entries and non-arrays", () => {
    expect(parseLossHistory(null)).toEqual([])
    expect(parseLossHistory("nope")).toEqual([])
    expect(
      parseLossHistory([
        { step: 1 },
        { loss: 2 },
        { step: "x", loss: 1 },
        { step: 3, loss: Number.NaN },
        42,
        { step: 4, loss: 0.5 },
      ]),
    ).toEqual([{ step: 4, loss: 0.5 }])
  })
})

describe("humanReplyLabel", () => {
  it("maps 1/2/3 to actions and passes through free text", () => {
    expect(humanReplyLabel("1")).toBe("rolled back")
    expect(humanReplyLabel("2")).toBe("apply fix")
    expect(humanReplyLabel("3")).toBe("stop")
    expect(humanReplyLabel("custom")).toBe("custom")
    expect(humanReplyLabel(null)).toBe(null)
  })
})

describe("sparklinePoints", () => {
  it("returns empty for no points", () => {
    expect(sparklinePoints([], 120, 32)).toBe("")
  })
  it("draws a flat line for a single point", () => {
    expect(sparklinePoints([{ step: 1, loss: 3 }], 120, 32)).toBe(
      "2.00,16.00 118.00,16.00",
    )
  })
  it("low loss sits lower (higher y) than high loss", () => {
    const pts = sparklinePoints(
      [
        { step: 1, loss: 10 },
        { step: 2, loss: 0 },
      ],
      120,
      32,
      2,
    )
    const [first, second] = pts.split(" ")
    const yHigh = Number(first.split(",")[1]) // loss=10 -> top -> small y
    const yLow = Number(second.split(",")[1]) // loss=0 -> bottom -> large y
    expect(yLow).toBeGreaterThan(yHigh)
  })
  it("spans the full width", () => {
    const pts = sparklinePoints(
      [
        { step: 1, loss: 1 },
        { step: 2, loss: 2 },
        { step: 3, loss: 1 },
      ],
      120,
      32,
      2,
    )
    const coords = pts.split(" ")
    expect(coords[0].split(",")[0]).toBe("2.00")
    expect(coords[coords.length - 1].split(",")[0]).toBe("118.00")
  })
})
