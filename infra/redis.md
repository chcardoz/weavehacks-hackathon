# Redis + Agent Memory Server — cloud (Railway)

keepalive uses Redis five ways: Streams (failure events), ZSET deadlines, the Agent Memory
Server (working + long-term incident memory), RedisVL SemanticRouter, and RedisVL
SemanticCache. Everything runs in the Railway project alongside the relay — no local
containers.

## Redis service

- Railway → New → Database → Redis. **Pin the image to `redis:8`** in the service settings —
  the query/vector engine is in Redis 8 core, and older defaults won't have `FT.*`.
- Do **NOT** use `redis-stack` — it's legacy.
- Copy the connection string into `REDIS_URL` on the relay service, the memory-server
  service, and your GPU box (the library).

### Verify the query engine + the five uses

```bash
redis-cli -u "$REDIS_URL" PING                    # PONG
redis-cli -u "$REDIS_URL" FT._LIST                # succeeds => query engine present

# Streams + consumer groups
redis-cli -u "$REDIS_URL" XADD failures '*' k v
redis-cli -u "$REDIS_URL" XGROUP CREATE failures wd '$' MKSTREAM
redis-cli -u "$REDIS_URL" XINFO GROUPS failures

# ZSET deadline polling
redis-cli -u "$REDIS_URL" ZADD deadlines 1750000000 inc1
redis-cli -u "$REDIS_URL" ZRANGEBYSCORE deadlines -inf 1750000000

# Vector index sanity (what RedisVL does under the hood)
redis-cli -u "$REDIS_URL" FT.CREATE vidx ON HASH PREFIX 1 v: \
  SCHEMA emb VECTOR HNSW 6 TYPE FLOAT32 DIM 4 DISTANCE_METRIC COSINE
```

## Agent Memory Server service

Deploy as its own Railway service from the Docker image `redislabs/agent-memory-server`
(REST on `8000`/`$PORT`, MCP on `9000`).

Env vars on the service:

| Var | Value |
| --- | ----- |
| `REDIS_URL` | the Railway Redis 8 service (it uses RedisVL → needs the query engine) |
| `OPENAI_API_KEY` | embeddings for long-term memory semantic search + dedup |
| `AUTH_MODE` | `disabled` (hackathon; it's the default — `DISABLE_AUTH=true` also works) |
| `GENERATION_MODEL` | optional, defaults to `gpt-4o` — override if desired |
| `EMBEDDING_MODEL` | optional, defaults to `text-embedding-3-small` |

Generate a public domain (Settings → Networking) and point the library's
`AGENT_MEMORY_URL` at it.

```bash
curl https://<memory-service>.up.railway.app/v1/health
```

Client side: `pip install agent-memory-client`. keepalive's `IncidentMemory` no-ops
gracefully if the client / server aren't available.

## Gotcha: vectors stay bytes

RedisVL vectors must be stored as **bytes** (`np.float32(...).tobytes()`). Never set
`decode_responses=True` on a client that touches vectors — it corrupts them. KNN queries
need `.dialect(2)`; a dimension mismatch fails **silently**. The library keeps vector
clients on a raw (non-decoding) connection for exactly this reason.
