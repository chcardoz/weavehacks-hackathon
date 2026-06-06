# Redis + Agent Memory Server — local stack

keepalive uses Redis five ways: Streams (failure events), ZSET deadlines, the Agent Memory
Server (working + long-term incident memory), RedisVL SemanticRouter, and RedisVL
SemanticCache. Locally you need two containers: `redis:8` and the Agent Memory Server.

## Image choice

- Use **`redis:8`**. The query / vector engine is in Redis core now.
- Do **NOT** use `redis-stack` — it's legacy.

## Bring up the stack

```bash
docker compose -f infra/docker-compose.yml up -d
```

This starts:

- **redis** on `localhost:6379` (so `REDIS_URL=redis://localhost:6379/0`).
- **agent-memory-server** on `localhost:8001` (container `8000` → host `8001`, to avoid
  colliding with the local relay on `8000`), wired to the redis container and given
  `OPENAI_API_KEY` for embeddings.

Export `OPENAI_API_KEY` in your shell first — compose passes it through to the memory
server.

```bash
export OPENAI_API_KEY="sk-..."
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps
```

## Agent Memory Server image

The compose file references `andrewbrookins510/agent-memory-server`. **Verify the current
image name at the event** — if it's stale, build from source:

```bash
git clone https://github.com/redis/agent-memory-server
docker build -t agent-memory-server ./agent-memory-server
```

Then swap the `image:` line in `docker-compose.yml` for `image: agent-memory-server`.

Client side: `pip install agent-memory-client`. keepalive's `IncidentMemory` no-ops
gracefully if the client / server aren't available.

## Gotcha: vectors stay bytes

RedisVL vectors must be stored as **bytes** (`np.float32(...).tobytes()`). Never set
`decode_responses=True` on a client that touches vectors — it corrupts them. KNN queries
need `.dialect(2)`; a dimension mismatch fails **silently**. The library keeps vector
clients on a raw (non-decoding) connection for exactly this reason.

## Smoke test

```bash
redis-cli ping                      # PONG
curl http://localhost:8001/health   # agent memory server health (verify path at event)
```
