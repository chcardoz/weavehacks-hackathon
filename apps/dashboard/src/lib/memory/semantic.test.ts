import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Never let a test reach the real embedding gateway or a real Redis socket.
vi.mock("ai", () => ({
  embed: vi.fn(async () => ({ embedding: new Array(1536).fill(0) })),
}))

import {
  canEmbed,
  distanceToSimilarity,
  escapeTag,
  parseHit,
  searchMemorySemantic,
  storeMemorySemantic,
  stripKeyPrefix,
  toHashFields,
} from "./semantic"

describe("escapeTag", () => {
  it("escapes hyphens in a UUID", () => {
    expect(escapeTag("a1b2-c3d4-e5f6")).toBe("a1b2\\-c3d4\\-e5f6")
  })

  it("leaves plain alphanumerics untouched", () => {
    expect(escapeTag("abc123")).toBe("abc123")
  })

  it("escapes other TAG-special characters", () => {
    expect(escapeTag("a@b c")).toBe("a\\@b\\ c")
  })
})

describe("distanceToSimilarity", () => {
  it("maps 0 distance to similarity 1", () => {
    expect(distanceToSimilarity(0)).toBe(1)
  })

  it("maps 1 distance to similarity 0", () => {
    expect(distanceToSimilarity(1)).toBe(0)
  })

  it("maps 0.25 distance to 0.75 similarity", () => {
    expect(distanceToSimilarity(0.25)).toBeCloseTo(0.75)
  })

  it("clamps cosine distances above 1 to 0", () => {
    expect(distanceToSimilarity(1.6)).toBe(0)
  })

  it("clamps below 0 to similarity 1", () => {
    expect(distanceToSimilarity(-0.1)).toBe(1)
  })

  it("returns 0 for NaN", () => {
    expect(distanceToSimilarity(Number.NaN)).toBe(0)
  })
})

describe("stripKeyPrefix", () => {
  it("strips the mem: prefix", () => {
    expect(stripKeyPrefix("mem:abc")).toBe("abc")
  })

  it("returns the key unchanged when unprefixed", () => {
    expect(stripKeyPrefix("abc")).toBe("abc")
  })
})

describe("toHashFields", () => {
  const vector = Buffer.from(new Float32Array([1, 2, 3]).buffer)

  it("maps all fields, vector included", () => {
    const fields = toHashFields(
      {
        id: "i1",
        projectId: "p1",
        kind: "nan",
        summary: "loss went NaN",
        resolution: "lowered lr",
      },
      vector,
    )
    expect(fields).toEqual({
      projectId: "p1",
      kind: "nan",
      summary: "loss went NaN",
      resolution: "lowered lr",
      embedding: vector,
    })
  })

  it("renders null kind/resolution as empty strings", () => {
    const fields = toHashFields(
      {
        id: "i1",
        projectId: "p1",
        kind: null,
        summary: "s",
        resolution: null,
      },
      vector,
    )
    expect(fields.kind).toBe("")
    expect(fields.resolution).toBe("")
    expect(fields.summary).toBe("s")
  })
})

describe("parseHit", () => {
  it("parses a full document and converts distance to similarity", () => {
    const hit = parseHit({
      id: "mem:i1",
      value: {
        score: "0.2",
        kind: "divergence",
        summary: "loss diverged",
        resolution: "added grad clip",
      },
    })
    expect(hit).toEqual({
      id: "i1",
      kind: "divergence",
      summary: "loss diverged",
      resolution: "added grad clip",
      similarity: expect.closeTo(0.8, 5),
    })
  })

  it("maps empty kind/resolution back to null", () => {
    const hit = parseHit({
      id: "mem:i2",
      value: { score: "0", kind: "", summary: "s", resolution: "" },
    })
    expect(hit.kind).toBeNull()
    expect(hit.resolution).toBeNull()
    expect(hit.summary).toBe("s")
    expect(hit.similarity).toBe(1)
  })

  it("defaults missing/invalid score to distance 1 (similarity 0)", () => {
    const hit = parseHit({ id: "mem:i3", value: { summary: "s" } })
    expect(hit.similarity).toBe(0)
    expect(hit.summary).toBe("s")
  })
})

describe("canEmbed", () => {
  const prev = {
    gateway: process.env.AI_GATEWAY_API_KEY,
    oidc: process.env.VERCEL_OIDC_TOKEN,
  }

  afterEach(() => {
    if (prev.gateway === undefined) delete process.env.AI_GATEWAY_API_KEY
    else process.env.AI_GATEWAY_API_KEY = prev.gateway
    if (prev.oidc === undefined) delete process.env.VERCEL_OIDC_TOKEN
    else process.env.VERCEL_OIDC_TOKEN = prev.oidc
  })

  it("is false without any gateway credentials", () => {
    delete process.env.AI_GATEWAY_API_KEY
    delete process.env.VERCEL_OIDC_TOKEN
    expect(canEmbed()).toBe(false)
  })

  it("is true with a gateway key", () => {
    process.env.AI_GATEWAY_API_KEY = "gw"
    delete process.env.VERCEL_OIDC_TOKEN
    expect(canEmbed()).toBe(true)
  })

  it("is true with an OIDC token", () => {
    delete process.env.AI_GATEWAY_API_KEY
    process.env.VERCEL_OIDC_TOKEN = "tok"
    expect(canEmbed()).toBe(true)
  })
})

describe("fallback behaviour without REDIS_URL", () => {
  const prevRedis = process.env.REDIS_URL

  beforeEach(() => {
    delete process.env.REDIS_URL
    // Embedding credentials present so we exercise the getRedis()-null path.
    process.env.AI_GATEWAY_API_KEY = "gw"
  })

  afterEach(() => {
    if (prevRedis === undefined) delete process.env.REDIS_URL
    else process.env.REDIS_URL = prevRedis
    delete process.env.AI_GATEWAY_API_KEY
  })

  it("storeMemorySemantic resolves without throwing", async () => {
    await expect(
      storeMemorySemantic({
        id: "i1",
        projectId: "p1",
        kind: "nan",
        summary: "s",
        resolution: null,
      }),
    ).resolves.toBeUndefined()
  })

  it("searchMemorySemantic returns null", async () => {
    await expect(searchMemorySemantic("p1", "why did loss spike")).resolves.toBe(
      null,
    )
  })

  it("searchMemorySemantic returns null when embedding is impossible", async () => {
    delete process.env.AI_GATEWAY_API_KEY
    delete process.env.VERCEL_OIDC_TOKEN
    await expect(searchMemorySemantic("p1", "q")).resolves.toBe(null)
  })
})
