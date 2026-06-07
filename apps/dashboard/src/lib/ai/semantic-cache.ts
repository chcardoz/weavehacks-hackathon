import { LangCache } from "@redis-ai/langcache";
import { SearchStrategy } from "@redis-ai/langcache/models";

/**
 * Redis LangCache semantic cache for the monitoring agent. Best-effort and
 * fully fail-open: every public function swallows errors and falls back to a
 * cache miss, and a slow cache can never stall the ingest path (~2s guard).
 */

const CACHE_TIMEOUT_MS = 2_000;

function readConfig():
  | { serverURL: string; cacheId: string; apiKey: string }
  | null {
  const serverURL = process.env.LANGCACHE_SERVER_URL;
  const cacheId = process.env.LANGCACHE_CACHE_ID;
  const apiKey = process.env.LANGCACHE_API_KEY;
  if (!serverURL || !cacheId || !apiKey) return null;
  return { serverURL, cacheId, apiKey };
}

export function isSemanticCacheEnabled(): boolean {
  return readConfig() !== null;
}

const GLOBAL_KEY = "__keepalive_langcache__";

interface CacheGlobal {
  [GLOBAL_KEY]?: LangCache;
}

/** Lazily constructs and caches the LangCache client on globalThis. */
function getClient(): LangCache | null {
  const config = readConfig();
  if (!config) return null;

  const store = globalThis as unknown as CacheGlobal;
  if (!store[GLOBAL_KEY]) {
    store[GLOBAL_KEY] = new LangCache({
      serverURL: config.serverURL,
      cacheId: config.cacheId,
      apiKey: config.apiKey,
    });
  }
  return store[GLOBAL_KEY] ?? null;
}

/**
 * Semantic-search the cache for a prior response to `prompt`. Returns the top
 * hit's response string, or null on miss / disabled / any error. NEVER throws.
 */
export async function searchSemanticCache(
  prompt: string,
): Promise<string | null> {
  const client = getClient();
  if (!client) return null;

  try {
    const res = await client.search(
      {
        prompt,
        searchStrategies: [SearchStrategy.Exact, SearchStrategy.Semantic],
      },
      { timeoutMs: CACHE_TIMEOUT_MS },
    );
    const hit = res.data[0];
    return hit ? hit.response : null;
  } catch (err) {
    console.error("semantic-cache search failed", err);
    return null;
  }
}

/**
 * Best-effort store of `response` under `prompt`. No-op when disabled; NEVER
 * throws and never blocks longer than the ~2s guard.
 */
export async function storeSemanticCache(
  prompt: string,
  response: string,
): Promise<void> {
  const client = getClient();
  if (!client) return;

  try {
    await client.set({ prompt, response }, { timeoutMs: CACHE_TIMEOUT_MS });
  } catch (err) {
    console.error("semantic-cache set failed", err);
  }
}
