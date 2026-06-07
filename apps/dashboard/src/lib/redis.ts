// Singleton Redis client + idempotent vector-index bootstrap for semantic
// incident memory. Redis Cloud free tier caps at 30 connections, so the client
// is cached on globalThis to survive serverless instance reuse. NEVER throws —
// callers treat a null client as "Redis unavailable" and fall back to SQL.

import {
  createClient,
  SCHEMA_FIELD_TYPE,
  SCHEMA_VECTOR_FIELD_ALGORITHM,
} from "redis"
import type { RedisClientType } from "redis"

export const MEMORY_INDEX = "idx:memory"
export const MEMORY_PREFIX = "mem:"
export const MEMORY_VECTOR_DIM = 1536

interface RedisSingleton {
  client: RedisClientType | null
  connecting: Promise<RedisClientType | null> | null
  indexEnsured: boolean
}

const globalForRedis = globalThis as typeof globalThis & {
  __keepaliveRedis?: RedisSingleton
}

function state(): RedisSingleton {
  if (!globalForRedis.__keepaliveRedis) {
    globalForRedis.__keepaliveRedis = {
      client: null,
      connecting: null,
      indexEnsured: false,
    }
  }
  return globalForRedis.__keepaliveRedis
}

/**
 * Returns a connected Redis client, or null when REDIS_URL is unset or the
 * connection fails. The client is cached across serverless invocations and
 * reconnected if it has been closed. Never throws.
 */
export async function getRedis(): Promise<RedisClientType | null> {
  const url = process.env.REDIS_URL
  if (!url) return null

  const s = state()

  if (s.client?.isOpen) return s.client
  if (s.connecting) return s.connecting

  s.connecting = (async () => {
    try {
      // Reuse an existing-but-closed client object so we don't leak connections.
      const client: RedisClientType =
        s.client ?? (createClient({ url }) as RedisClientType)
      // A client that errors after connect would otherwise throw unhandled.
      client.removeAllListeners("error")
      client.on("error", (err) => {
        console.error("[redis] client error", err)
      })
      if (!client.isOpen) await client.connect()
      s.client = client
      return client
    } catch (err) {
      console.error("[redis] connect failed", err)
      s.client = null
      return null
    } finally {
      s.connecting = null
    }
  })()

  return s.connecting
}

/**
 * Idempotently creates the HNSW vector index over `mem:*` hashes. Runs at most
 * once per serverless instance. Swallows the "index already exists" error;
 * logs (but does not rethrow) anything else.
 */
export async function ensureMemoryIndex(
  client: RedisClientType,
): Promise<void> {
  const s = state()
  if (s.indexEnsured) return

  try {
    await client.ft.create(
      MEMORY_INDEX,
      {
        projectId: { type: SCHEMA_FIELD_TYPE.TAG },
        kind: { type: SCHEMA_FIELD_TYPE.TEXT },
        summary: { type: SCHEMA_FIELD_TYPE.TEXT },
        resolution: { type: SCHEMA_FIELD_TYPE.TEXT },
        embedding: {
          type: SCHEMA_FIELD_TYPE.VECTOR,
          ALGORITHM: SCHEMA_VECTOR_FIELD_ALGORITHM.HNSW,
          TYPE: "FLOAT32",
          DIM: MEMORY_VECTOR_DIM,
          DISTANCE_METRIC: "COSINE",
        },
      },
      { ON: "HASH", PREFIX: MEMORY_PREFIX },
    )
    s.indexEnsured = true
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    if (msg.toLowerCase().includes("index already exists")) {
      s.indexEnsured = true
      return
    }
    console.error("[redis] ensureMemoryIndex failed", err)
  }
}
