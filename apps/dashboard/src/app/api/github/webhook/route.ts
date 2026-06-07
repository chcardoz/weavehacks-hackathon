import { and, eq } from "drizzle-orm"
import { start } from "workflow/api"

import { db } from "@/lib/db"
import { project } from "@/db/schema"
import { verifyGithubSignature } from "@/lib/github-webhook"
import { emitEvent } from "@/lib/server-events"
import { trainingLaunch } from "@/workflows/training-launch"

// HMAC verification needs Node crypto + the raw body, so force the Node runtime.
export const runtime = "nodejs"

interface PushPayload {
  ref?: string
  after?: string
  deleted?: boolean
  repository?: {
    name?: string
    owner?: { login?: string; name?: string }
  }
  pusher?: { name?: string; email?: string }
}

// POST /api/github/webhook
// GitHub push webhook. Verifies the HMAC over the raw bytes, then (for a push to
// the project's default branch) starts the trainingLaunch workflow. Always
// responds fast; failures are logged as events, never 500s.
export async function POST(request: Request) {
  // Read the RAW body first — the HMAC is computed over these exact bytes.
  const raw = await request.text()

  const signature = request.headers.get("x-hub-signature-256")
  if (!verifyGithubSignature(raw, signature, process.env.GITHUB_WEBHOOK_SECRET)) {
    return new Response("invalid signature", { status: 401 })
  }

  const githubEvent = request.headers.get("x-github-event")
  if (githubEvent === "ping") {
    return new Response("pong", { status: 200 })
  }
  if (githubEvent !== "push") {
    return new Response("ignored: not a push event", { status: 200 })
  }

  let payload: PushPayload
  try {
    payload = JSON.parse(raw) as PushPayload
  } catch {
    return new Response("invalid json", { status: 200 })
  }

  const repoOwner = payload.repository?.owner?.login
  const repoName = payload.repository?.name
  const commitSha = payload.after
  if (!repoOwner || !repoName || !commitSha) {
    return new Response("ignored: incomplete payload", { status: 200 })
  }

  const [proj] = await db
    .select()
    .from(project)
    .where(
      and(eq(project.repoOwner, repoOwner), eq(project.repoName, repoName)),
    )
    .limit(1)

  if (!proj) {
    return new Response("no project for repo", { status: 200 })
  }

  // Only fire on a push to the default branch. Agent fix branches
  // (keepalive/fix-*) must NEVER trigger a training run. Deletions are ignored.
  if (payload.ref !== `refs/heads/${proj.defaultBranch}` || payload.deleted) {
    return new Response("ignored: not the default branch", { status: 200 })
  }

  try {
    await start(trainingLaunch, [proj.id, commitSha])

    await emitEvent({
      projectId: proj.id,
      source: "github",
      type: "training.requested",
      message: `Push to ${proj.defaultBranch} (${commitSha.slice(0, 7)}) — launching training`,
      data: {
        commit_sha: commitSha,
        pusher: payload.pusher?.name ?? null,
      },
    })
  } catch (err) {
    await emitEvent({
      projectId: proj.id,
      source: "github",
      level: "error",
      type: "training.requested",
      message: `Failed to start training launch: ${err instanceof Error ? err.message : String(err)}`,
      data: { commit_sha: commitSha },
    })
  }

  return new Response("ok", { status: 200 })
}
