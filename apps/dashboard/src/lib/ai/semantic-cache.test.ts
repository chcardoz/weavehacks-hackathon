import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parseCachedVerdict } from "./monitor";

const ENV_KEYS = [
  "LANGCACHE_SERVER_URL",
  "LANGCACHE_CACHE_ID",
  "LANGCACHE_API_KEY",
] as const;

function clearEnv() {
  for (const k of ENV_KEYS) delete process.env[k];
}

function setEnv() {
  process.env.LANGCACHE_SERVER_URL = "https://cache.example";
  process.env.LANGCACHE_CACHE_ID = "cache_1";
  process.env.LANGCACHE_API_KEY = "lc_secret";
}

describe("semantic-cache (disabled env)", () => {
  beforeEach(() => {
    clearEnv();
    vi.resetModules();
  });

  it("isSemanticCacheEnabled is false when env is missing", async () => {
    const { isSemanticCacheEnabled } = await import("./semantic-cache");
    expect(isSemanticCacheEnabled()).toBe(false);
  });

  it("search returns null and store resolves without throwing", async () => {
    const { searchSemanticCache, storeSemanticCache } = await import(
      "./semantic-cache"
    );
    await expect(searchSemanticCache("anything")).resolves.toBeNull();
    await expect(storeSemanticCache("a", "b")).resolves.toBeUndefined();
  });

  it("is enabled once all three env vars are present", async () => {
    setEnv();
    const { isSemanticCacheEnabled } = await import("./semantic-cache");
    expect(isSemanticCacheEnabled()).toBe(true);
    clearEnv();
  });
});

describe("semantic-cache (mocked SDK)", () => {
  const search = vi.hoisted(() => vi.fn());
  const set = vi.hoisted(() => vi.fn());

  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    // Fresh singleton each test.
    delete (globalThis as Record<string, unknown>).__keepalive_langcache__;
    setEnv();
    vi.doMock("@redis-ai/langcache", () => ({
      LangCache: vi.fn(() => ({ search, set })),
    }));
    vi.doMock("@redis-ai/langcache/models", () => ({
      SearchStrategy: { Exact: "exact", Semantic: "semantic" },
    }));
  });

  afterEach(() => {
    clearEnv();
    delete (globalThis as Record<string, unknown>).__keepalive_langcache__;
  });

  it("returns the top hit's response on a cache hit", async () => {
    search.mockResolvedValue({
      data: [
        { id: "1", prompt: "p", response: "cached!", attributes: {}, similarity: 0.99, searchStrategy: "semantic" },
      ],
    });
    const { searchSemanticCache } = await import("./semantic-cache");
    await expect(searchSemanticCache("p")).resolves.toBe("cached!");
    expect(search).toHaveBeenCalledOnce();
    const arg = search.mock.calls[0][0];
    expect(arg.searchStrategies).toEqual(["exact", "semantic"]);
  });

  it("returns null on an empty result set", async () => {
    search.mockResolvedValue({ data: [] });
    const { searchSemanticCache } = await import("./semantic-cache");
    await expect(searchSemanticCache("p")).resolves.toBeNull();
  });

  it("returns null (never throws) when the SDK search throws", async () => {
    search.mockRejectedValue(new Error("network down"));
    const { searchSemanticCache } = await import("./semantic-cache");
    await expect(searchSemanticCache("p")).resolves.toBeNull();
  });

  it("store swallows SDK set errors", async () => {
    set.mockRejectedValue(new Error("nope"));
    const { storeSemanticCache } = await import("./semantic-cache");
    await expect(storeSemanticCache("p", "r")).resolves.toBeUndefined();
  });
});

describe("parseCachedVerdict", () => {
  it("returns the verdict for a valid payload", () => {
    const verdict = { confidence: 0.3, reasoning: "loss diverging", signals: ["divergence"] };
    expect(parseCachedVerdict(JSON.stringify(verdict))).toEqual(verdict);
  });

  it("returns null for malformed JSON", () => {
    expect(parseCachedVerdict("{not json")).toBeNull();
  });

  it("returns null for schema-invalid payloads", () => {
    expect(parseCachedVerdict(JSON.stringify({ confidence: 5 }))).toBeNull();
    expect(parseCachedVerdict(JSON.stringify({ confidence: 0.5, reasoning: "x", signals: ["bogus"] }))).toBeNull();
  });
});
