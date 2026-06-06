import { describe, expect, it } from "vitest"

import { cn } from "./utils"

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("a", "b")).toBe("a b")
  })

  it("drops falsy values", () => {
    expect(cn("a", false, undefined, null, "b")).toBe("a b")
  })

  it("resolves tailwind conflicts with last-wins", () => {
    expect(cn("p-2", "p-4")).toBe("p-4")
    expect(cn("text-red-500", "text-zinc-50")).toBe("text-zinc-50")
  })

  it("handles conditional objects and arrays", () => {
    expect(cn({ a: true, b: false }, ["c", { d: true }])).toBe("a c d")
  })
})
