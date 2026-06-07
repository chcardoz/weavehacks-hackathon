import { describe, expect, it } from "vitest"

import {
  applyEdit,
  countOccurrences,
  numberLines,
  truncateOutput,
} from "./text-utils"

describe("countOccurrences", () => {
  it("counts non-overlapping matches", () => {
    expect(countOccurrences("aaa", "a")).toBe(3)
    expect(countOccurrences("ababab", "ab")).toBe(3)
    expect(countOccurrences("aaaa", "aa")).toBe(2) // non-overlapping
    expect(countOccurrences("hello", "z")).toBe(0)
  })

  it("returns 0 for empty needle", () => {
    expect(countOccurrences("hello", "")).toBe(0)
  })
})

describe("applyEdit", () => {
  it("replaces a unique occurrence", () => {
    const r = applyEdit("lr = 0.1\nbatch = 32", "lr = 0.1", "lr = 0.01")
    expect(r.ok).toBe(true)
    expect(r.content).toBe("lr = 0.01\nbatch = 32")
  })

  it("rejects when oldString is missing", () => {
    const r = applyEdit("foo", "bar", "baz")
    expect(r.ok).toBe(false)
    expect(r.error).toContain("not found")
  })

  it("rejects ambiguous (non-unique) edits and reports the count", () => {
    const r = applyEdit("x\nx\nx", "x", "y")
    expect(r.ok).toBe(false)
    expect(r.error).toContain("not unique")
    expect(r.error).toContain("3")
  })

  it("replaceAll replaces every occurrence", () => {
    const r = applyEdit("x\nx\nx", "x", "y", true)
    expect(r.ok).toBe(true)
    expect(r.content).toBe("y\ny\ny")
  })

  it("only replaces the first when unique-but-replaceAll-false would be ambiguous, so replaceAll is required", () => {
    const ambiguous = applyEdit("a a", "a", "b")
    expect(ambiguous.ok).toBe(false)
    const all = applyEdit("a a", "a", "b", true)
    expect(all.content).toBe("b b")
  })

  it("rejects identical strings", () => {
    const r = applyEdit("foo", "foo", "foo")
    expect(r.ok).toBe(false)
    expect(r.error).toContain("identical")
  })

  it("rejects empty oldString", () => {
    const r = applyEdit("foo", "", "bar")
    expect(r.ok).toBe(false)
    expect(r.error).toContain("empty")
  })
})

describe("truncateOutput", () => {
  it("returns short output unchanged", () => {
    expect(truncateOutput("hello\nworld")).toBe("hello\nworld")
  })

  it("keeps the tail and prepends a header when over the line cap", () => {
    const input = Array.from({ length: 10 }, (_, i) => `line${i}`).join("\n")
    const out = truncateOutput(input, { maxLines: 3 })
    expect(out).toContain("...truncated")
    expect(out).toContain("7 earlier lines")
    expect(out).toContain("line9")
    expect(out).toContain("line7")
    expect(out).not.toContain("line6")
  })

  it("enforces the byte cap on the tail", () => {
    const input = "x".repeat(100)
    const out = truncateOutput(input, { maxLines: 1000, maxBytes: 10 })
    expect(out).toContain("...truncated")
    expect(out).toContain("earlier bytes")
    // header + newline + 10 trailing x's
    expect(out.endsWith("x".repeat(10))).toBe(true)
  })

  it("handles empty output", () => {
    expect(truncateOutput("")).toBe("")
  })
})

describe("numberLines", () => {
  it("prefixes 1-based line numbers", () => {
    expect(numberLines("a\nb\nc")).toBe("1: a\n2: b\n3: c")
  })

  it("honours offset and limit", () => {
    const out = numberLines("a\nb\nc\nd\ne", { offset: 1, limit: 2 })
    expect(out).toContain("2: b")
    expect(out).toContain("3: c")
    expect(out).toContain("more lines")
  })

  it("caps at hardCap and notes truncation", () => {
    const input = Array.from({ length: 50 }, (_, i) => `L${i}`).join("\n")
    const out = numberLines(input, { hardCap: 5 })
    expect(out).toContain("1: L0")
    expect(out).toContain("5: L4")
    expect(out).toContain("45 more lines")
  })
})
