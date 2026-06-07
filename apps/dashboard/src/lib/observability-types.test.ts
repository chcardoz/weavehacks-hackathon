import { describe, expect, it } from "vitest"
import {
  agentStateTone,
  eventLevelClass,
  eventSourceClass,
  formatRelative,
  isIncidentResolved,
  parseLossHistory,
  projectStatusTone,
  sparklinePoints,
} from "./observability-types"

describe("isIncidentResolved", () => {
  it("treats resolved and failed as resolved", () => {
    expect(isIncidentResolved("resolved")).toBe(true)
    expect(isIncidentResolved("failed")).toBe(true)
  })
  it("treats live statuses as unresolved", () => {
    for (const s of ["detected", "hypothesizing", "fixing"]) {
      expect(isIncidentResolved(s)).toBe(false)
    }
  })
})

describe("projectStatusTone", () => {
  it("maps statuses to colors", () => {
    expect(projectStatusTone("idle").dot).toBe("bg-muted-foreground")
    expect(projectStatusTone("training").dot).toBe("bg-emerald-500")
    expect(projectStatusTone("incident").dot).toBe("bg-red-500")
    expect(projectStatusTone("fixing").dot).toBe("bg-primary")
    expect(projectStatusTone("recovered").dot).toBe("bg-sky-500")
    expect(projectStatusTone("stopped").dot).toBe("bg-muted-foreground")
  })
  it("falls back for unknown status", () => {
    expect(projectStatusTone("???").dot).toBe("bg-muted-foreground")
  })
})

describe("agentStateTone", () => {
  it("coding pulses, pr_opened is emerald, failed is destructive", () => {
    expect(agentStateTone("coding").className).toContain("animate-pulse")
    expect(agentStateTone("pushed").className).toContain("sky")
    expect(agentStateTone("pr_opened").className).toContain("emerald")
    expect(agentStateTone("failed").variant).toBe("destructive")
    expect(agentStateTone("spawned").variant).toBe("muted")
  })
})

describe("event class helpers", () => {
  it("maps sources to hues", () => {
    expect(eventSourceClass("library")).toContain("emerald")
    expect(eventSourceClass("hypothesis")).toContain("primary")
    expect(eventSourceClass("coder")).toContain("violet")
    expect(eventSourceClass("unknown")).toContain("muted")
  })
  it("maps levels", () => {
    expect(eventLevelClass("warn")).toContain("amber")
    expect(eventLevelClass("error")).toContain("red")
    expect(eventLevelClass("info")).toBe("text-foreground")
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
