// Redis-backed semantic incident memory: embeds incident summaries with
// text-embedding-3-small (via the Vercel AI Gateway) and stores them as HNSW
// vectors for project-scoped KNN recall. Both entry points are total — they
// never throw, so the ingest/fixing paths are never blocked. When Redis or the
// embedding gateway is unavailable, search returns null and callers fall back
// to SQL ILIKE.

import { embed } from "ai"

import {
  ensureMemoryIndex,
  getRedis,
  MEMORY_INDEX,
  MEMORY_PREFIX,
} from "../redis"

const EMBEDDING_MODEL = "openai/text-embedding-3-small"
const DEFAULT_LIMIT = 5

export interface MemoryHit {
  id: string
  kind: string | null
  summary: string
  resolution: string | null
  similarity: number // 0..1, higher = more similar
}

export interface MemoryEntry {
  id: string
  projectId: string
  kind: string | null
  summary: string
  resolution: string | null
}

// --- pure helpers (unit-testable without Redis) ---------------------------

/**
 * Escapes the RediSearch TAG-special characters so a UUID can be matched
 * literally inside `@projectId:{...}`. Project ids are UUIDs whose only special
 * character is `-`, but we escape the full punctuation set defensively.
 */
export function escapeTag(value: string): string {
  return value.replace(/[-.,<>{}[\]"':;!@#$%^&*()+=~|/\\ ]/g, "\\$&")
}

/** Cosine distance (0 = identical, 2 = opposite) → similarity in 0..1. */
export function distanceToSimilarity(distance: number): number {
  const sim = 1 - distance
  if (Number.isNaN(sim)) return 0
  return Math.max(0, Math.min(1, sim))
}

/** Maps a MemoryEntry to the flat HASH field set (nulls → empty strings). */
export function toHashFields(
  entry: MemoryEntry,
  vector: Buffer,
): Record<string, string | Buffer> {
  return {
    projectId: entry.projectId,
    kind: entry.kind ?? "",
    summary: entry.summary,
    resolution: entry.resolution ?? "",
    embedding: vector,
  }
}

interface RawDocument {
  id: string
  value: Record<string, unknown>
}

/** Parses one FT.SEARCH document into a MemoryHit. Empty strings → null. */
export function parseHit(doc: RawDocument): MemoryHit {
  const value = doc.value
  const score = Number(value.score)
  const distance = Number.isFinite(score) ? score : 1
  const kind = typeof value.kind === "string" ? value.kind : ""
  const resolution =
    typeof value.resolution === "string" ? value.resolution : ""
  const summary = typeof value.summary === "string" ? value.summary : ""
  return {
    id: stripKeyPrefix(doc.id),
    kind: kind === "" ? null : kind,
    summary,
    resolution: resolution === "" ? null : resolution,
    similarity: distanceToSimilarity(distance),
  }
}

/** Strips the `mem:` key prefix to recover the bare incident id. */
export function stripKeyPrefix(key: string): string {
  return key.startsWith(MEMORY_PREFIX) ? key.slice(MEMORY_PREFIX.length) : key
}

/** True when an embedding call is even possible (gateway credentials present). */
export function canEmbed(): boolean {
  return Boolean(
    process.env.AI_GATEWAY_API_KEY ?? process.env.VERCEL_OIDC_TOKEN,
  )
}

function toVectorBuffer(embedding: number[]): Buffer {
  return Buffer.from(new Float32Array(embedding).buffer)
}

async function embedText(value: string): Promise<number[]> {
  const { embedding } = await embed({
    model: EMBEDDING_MODEL,
    value,
    experimental_telemetry: { isEnabled: true, functionId: "memory.embed" },
  })
  return embedding
}

// --- public API -----------------------------------------------------------

/** Embeds + upserts into Redis. NEVER throws. Silent no-op without REDIS_URL. */
export async function storeMemorySemantic(entry: MemoryEntry): Promise<void> {
  try {
    if (!canEmbed()) return
    const client = await getRedis()
    if (!client) return
    await ensureMemoryIndex(client)

    const embedding = await embedText(entry.summary)
    const vector = toVectorBuffer(embedding)
    await client.hSet(`${MEMORY_PREFIX}${entry.id}`, toHashFields(entry, vector))
  } catch (err) {
    console.error("[memory] storeMemorySemantic failed", err)
  }
}

/**
 * KNN search scoped to projectId. Returns null when Redis/embeddings are
 * unavailable (callers fall back to SQL ILIKE); [] when available but no hits.
 * NEVER throws.
 */
export async function searchMemorySemantic(
  projectId: string,
  query: string,
  limit: number = DEFAULT_LIMIT,
): Promise<MemoryHit[] | null> {
  try {
    if (!canEmbed()) return null
    const client = await getRedis()
    if (!client) return null
    await ensureMemoryIndex(client)

    const embedding = await embedText(query)
    const queryBuf = toVectorBuffer(embedding)

    const knn = `(@projectId:{${escapeTag(projectId)}})=>[KNN ${limit} @embedding $B AS score]`
    const reply = await client.ft.search(MEMORY_INDEX, knn, {
      PARAMS: { B: queryBuf },
      RETURN: ["score", "kind", "summary", "resolution"],
      SORTBY: "score",
      DIALECT: 2,
    })

    return reply.documents.map((doc) =>
      parseHit(doc as unknown as RawDocument),
    )
  } catch (err) {
    console.error("[memory] searchMemorySemantic failed", err)
    return null
  }
}
