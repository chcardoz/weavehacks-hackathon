import { Sandbox } from "@vercel/sandbox"
import { desc, eq } from "drizzle-orm"

import { db } from "@/lib/db"
import {
  agent as agentTable,
  event as eventTable,
  incident as incidentTable,
  memory as memoryTable,
  project as projectTable,
  run as runTable,
  user as userTable,
} from "@/db/schema"
import { flushTraces, initWeave } from "@/lib/ai"
import { emitEvent } from "@/lib/server-events"
import { getGithubToken, getOctokit } from "@/lib/github"
import { dashboardBaseUrl, sendIncidentReport } from "@/lib/email"
import {
  generateHypotheses,
  type Hypothesis,
} from "@/lib/agents/hypothesis"
import { runCoder } from "@/lib/agents/coder"
import { storeMemorySemantic } from "@/lib/memory/semantic"

// --- serializable context passed between workflow steps (pass-by-value) ---

interface PipelineContext {
  incidentId: string
  projectId: string
  runId: string
  userId: string
  ownerEmail: string | null
  repoOwner: string
  repoName: string
  defaultBranch: string
  fixingPrompt: string | null
  maxAgents: number
  projectName: string
  commitSha: string | null
  incident: {
    kind: string | null
    step: number | null
    confidence: number | null
    reasoning: string | null
  }
  metricsTail: unknown[]
  errorEvents: { type: string; message: string; data?: unknown }[]
  recentMemory: {
    kind: string | null
    summary: string
    resolution: string | null
  }[]
  diagnosis: string
  hypotheses: Hypothesis[]
}

interface AgentRunResult {
  agentId: string
  state: string
  prUrl?: string
  prNumber?: number
  error?: string
  hypothesisTitle: string
}

const SANDBOX_TIMEOUT_MS = 15 * 60 * 1000 // 15 minutes
const REPO_ROOT = "/vercel/sandbox"

// ===================================================================
// Workflow orchestrator
// ===================================================================

export async function fixingPipeline(incidentId: string) {
  "use workflow"

  const ctx = await loadContext(incidentId)
  const withHypotheses = await generateHypothesesStep(ctx)

  const results = await Promise.all(
    withHypotheses.hypotheses.map((h, i) =>
      runCodingAgent(withHypotheses, h, i),
    ),
  )

  await finalize(withHypotheses, results)

  return {
    incidentId,
    diagnosis: withHypotheses.diagnosis,
    agents: results,
  }
}

// ===================================================================
// Step a: loadContext
// ===================================================================

async function loadContext(incidentId: string): Promise<PipelineContext> {
  "use step"

  const [inc] = await db
    .select()
    .from(incidentTable)
    .where(eq(incidentTable.id, incidentId))
    .limit(1)
  if (!inc) throw new Error(`incident ${incidentId} not found`)

  const [proj] = await db
    .select()
    .from(projectTable)
    .where(eq(projectTable.id, inc.projectId))
    .limit(1)
  if (!proj) throw new Error(`project ${inc.projectId} not found`)

  const [r] = await db
    .select()
    .from(runTable)
    .where(eq(runTable.id, inc.runId))
    .limit(1)

  const [owner] = await db
    .select({ email: userTable.email })
    .from(userTable)
    .where(eq(userTable.id, proj.userId))
    .limit(1)

  const memoryRows = await db
    .select({
      kind: memoryTable.kind,
      summary: memoryTable.summary,
      resolution: memoryTable.resolution,
    })
    .from(memoryTable)
    .where(eq(memoryTable.projectId, proj.id))
    .orderBy(desc(memoryTable.createdAt))
    .limit(8)

  const recentEvents = await db
    .select({
      type: eventTable.type,
      level: eventTable.level,
      message: eventTable.message,
      data: eventTable.data,
    })
    .from(eventTable)
    .where(eq(eventTable.runId, inc.runId))
    .orderBy(desc(eventTable.id))
    .limit(30)

  const errorEvents = recentEvents
    .filter((e) => e.level === "error" || e.type.startsWith("incident"))
    .map((e) => ({ type: e.type, message: e.message, data: e.data }))

  const metricsWindow = Array.isArray(r?.metricsWindow)
    ? (r.metricsWindow as unknown[])
    : []
  const metricsTail = metricsWindow.slice(-12)

  // Transition: hypothesizing + emit start event.
  await db
    .update(incidentTable)
    .set({ status: "hypothesizing" })
    .where(eq(incidentTable.id, incidentId))

  await emitEvent({
    projectId: proj.id,
    runId: inc.runId,
    incidentId,
    source: "server",
    type: "incident.fixing_started",
    message: `Fixing pipeline started for ${inc.kind ?? "incident"}`,
    data: { kind: inc.kind, step: inc.step },
  })

  return {
    incidentId,
    projectId: proj.id,
    runId: inc.runId,
    userId: proj.userId,
    ownerEmail: owner?.email ?? null,
    repoOwner: proj.repoOwner,
    repoName: proj.repoName,
    defaultBranch: proj.defaultBranch,
    fixingPrompt: proj.fixingPrompt,
    maxAgents: proj.maxAgents,
    projectName: proj.name,
    commitSha: r?.commitSha ?? null,
    incident: {
      kind: inc.kind,
      step: inc.step,
      confidence: inc.confidence,
      reasoning: inc.reasoning,
    },
    metricsTail,
    errorEvents,
    recentMemory: memoryRows,
    diagnosis: "",
    hypotheses: [],
  }
}

// ===================================================================
// Step b: generateHypotheses (the hypothesis agent)
// ===================================================================

async function generateHypothesesStep(
  ctx: PipelineContext,
): Promise<PipelineContext> {
  "use step"

  await initWeave()
  try {
    const { diagnosis, hypotheses } = await generateHypotheses({
      projectId: ctx.projectId,
      incidentId: ctx.incidentId,
      fixingPrompt: ctx.fixingPrompt,
      maxAgents: ctx.maxAgents,
      incident: ctx.incident,
      metricsTail: ctx.metricsTail,
      errorEvents: ctx.errorEvents,
      recentMemory: ctx.recentMemory,
    })

    await db
      .update(incidentTable)
      .set({ diagnosis, status: "fixing" })
      .where(eq(incidentTable.id, ctx.incidentId))

    await emitEvent({
      projectId: ctx.projectId,
      runId: ctx.runId,
      incidentId: ctx.incidentId,
      source: "hypothesis",
      type: "incident.diagnosed",
      message: diagnosis.slice(0, 280),
      data: { diagnosis, hypotheses },
    })

    return { ...ctx, diagnosis, hypotheses }
  } finally {
    await flushTraces()
  }
}

// ===================================================================
// Step c: runCodingAgent (one per hypothesis, fanned out)
// ===================================================================

async function runCodingAgent(
  ctx: PipelineContext,
  hypothesis: Hypothesis,
  index: number,
): Promise<AgentRunResult> {
  "use step"

  await initWeave()
  const agentId = crypto.randomUUID()
  const branch = `keepalive/fix-${ctx.incidentId.slice(0, 8)}-${index + 1}`

  await db.insert(agentTable).values({
    id: agentId,
    incidentId: ctx.incidentId,
    projectId: ctx.projectId,
    hypothesis: `${hypothesis.title}\n\n${hypothesis.detail}`,
    branch,
    state: "spawned",
  })

  await emitEvent({
    projectId: ctx.projectId,
    runId: ctx.runId,
    incidentId: ctx.incidentId,
    agentId,
    source: "coder",
    type: "agent.spawned",
    message: `Agent ${index + 1}: ${hypothesis.title}`,
    data: { branch, hypothesis },
  })

  let sandbox: Sandbox | undefined

  try {
    const token = await getGithubToken(ctx.userId)
    if (!token) throw new Error("no linked GitHub token for project owner")

    const cloneUrl = `https://github.com/${ctx.repoOwner}/${ctx.repoName}.git`

    sandbox = await Sandbox.create({
      source: {
        type: "git",
        url: cloneUrl,
        username: "x-access-token",
        password: token,
        revision: ctx.commitSha || undefined,
        depth: 64,
      },
      runtime: "node24",
      resources: { vcpus: 2 },
      timeout: SANDBOX_TIMEOUT_MS,
    })

    const sandboxId = sandbox.name

    // Create the working branch.
    const checkout = await sandbox.runCommand({
      cmd: "git",
      args: ["checkout", "-b", branch],
      cwd: REPO_ROOT,
    })
    if (checkout.exitCode !== 0) {
      throw new Error(
        `git checkout failed: ${await checkout.stderr()}`.slice(0, 500),
      )
    }

    await db
      .update(agentTable)
      .set({ state: "coding", sandboxId, updatedAt: new Date() })
      .where(eq(agentTable.id, agentId))

    await emitEvent({
      projectId: ctx.projectId,
      runId: ctx.runId,
      incidentId: ctx.incidentId,
      agentId,
      source: "sandbox",
      type: "agent.coding",
      message: `Sandbox ${sandboxId} cloned; coding agent started`,
      data: { sandboxId, branch },
    })

    // Run the coding agent loop.
    const { summary } = await runCoder({
      sandbox,
      repoRoot: REPO_ROOT,
      hypothesis,
      diagnosis: ctx.diagnosis,
      incidentId: ctx.incidentId,
      agentId,
    })

    // Stage changes and verify there is a diff.
    await sandbox.runCommand({ cmd: "git", args: ["add", "-A"], cwd: REPO_ROOT })
    const staged = await sandbox.runCommand({
      cmd: "git",
      args: ["diff", "--cached", "--stat"],
      cwd: REPO_ROOT,
    })
    const diffStat = (await staged.stdout()).trim()
    if (diffStat === "") {
      await db
        .update(agentTable)
        .set({
          state: "failed",
          error: "no changes produced",
          report: summary,
          updatedAt: new Date(),
        })
        .where(eq(agentTable.id, agentId))
      await emitEvent({
        projectId: ctx.projectId,
        runId: ctx.runId,
        incidentId: ctx.incidentId,
        agentId,
        source: "coder",
        level: "warn",
        type: "agent.failed",
        message: "Agent produced no changes",
        data: { hypothesisTitle: hypothesis.title },
      })
      return {
        agentId,
        state: "failed",
        error: "no changes",
        hypothesisTitle: hypothesis.title,
      }
    }

    // Commit.
    const commit = await sandbox.runCommand({
      cmd: "git",
      args: [
        "-c",
        "user.name=keepalive[bot]",
        "-c",
        "user.email=bot@keepalive.club",
        "commit",
        "-m",
        `keepalive: ${hypothesis.title}`,
      ],
      cwd: REPO_ROOT,
    })
    if (commit.exitCode !== 0) {
      throw new Error(`git commit failed: ${await commit.stderr()}`.slice(0, 500))
    }

    // Push using the token in the URL to avoid credential prompts.
    const pushUrl = `https://x-access-token:${token}@github.com/${ctx.repoOwner}/${ctx.repoName}.git`
    const push = await sandbox.runCommand({
      cmd: "git",
      args: ["push", pushUrl, `HEAD:${branch}`],
      cwd: REPO_ROOT,
    })
    if (push.exitCode !== 0) {
      throw new Error(`git push failed: ${await push.stderr()}`.slice(0, 500))
    }

    await db
      .update(agentTable)
      .set({ state: "pushed", updatedAt: new Date() })
      .where(eq(agentTable.id, agentId))

    await emitEvent({
      projectId: ctx.projectId,
      runId: ctx.runId,
      incidentId: ctx.incidentId,
      agentId,
      source: "coder",
      type: "agent.pushed",
      message: `Pushed branch ${branch}`,
      data: { branch },
    })

    // Open the PR.
    const report = buildReport(ctx, hypothesis, diffStat, summary)
    const octokit = await getOctokit(ctx.userId)
    const pr = await octokit.rest.pulls.create({
      owner: ctx.repoOwner,
      repo: ctx.repoName,
      head: branch,
      base: ctx.defaultBranch,
      title: `🤖 keepalive fix: ${hypothesis.title}`,
      body: report,
    })

    await db
      .update(agentTable)
      .set({
        state: "pr_opened",
        prUrl: pr.data.html_url,
        prNumber: pr.data.number,
        report,
        updatedAt: new Date(),
      })
      .where(eq(agentTable.id, agentId))

    await emitEvent({
      projectId: ctx.projectId,
      runId: ctx.runId,
      incidentId: ctx.incidentId,
      agentId,
      source: "coder",
      type: "agent.pr_opened",
      message: `Opened PR #${pr.data.number}: ${hypothesis.title}`,
      data: { prUrl: pr.data.html_url, prNumber: pr.data.number, branch },
    })

    return {
      agentId,
      state: "pr_opened",
      prUrl: pr.data.html_url,
      prNumber: pr.data.number,
      hypothesisTitle: hypothesis.title,
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    await db
      .update(agentTable)
      .set({ state: "failed", error: message.slice(0, 1000), updatedAt: new Date() })
      .where(eq(agentTable.id, agentId))
    await emitEvent({
      projectId: ctx.projectId,
      runId: ctx.runId,
      incidentId: ctx.incidentId,
      agentId,
      source: "coder",
      level: "error",
      type: "agent.failed",
      message: `Agent ${index + 1} failed: ${message}`.slice(0, 500),
      data: { hypothesisTitle: hypothesis.title },
    })
    return {
      agentId,
      state: "failed",
      error: message,
      hypothesisTitle: hypothesis.title,
    }
  } finally {
    if (sandbox) {
      try {
        await sandbox.stop()
      } catch (stopErr) {
        console.error("[fixing-pipeline] sandbox.stop failed:", stopErr)
      }
    }
    await flushTraces()
  }
}

// ===================================================================
// Step d: finalize
// ===================================================================

async function finalize(
  ctx: PipelineContext,
  results: AgentRunResult[],
): Promise<void> {
  "use step"

  const opened = results.filter((r) => r.state === "pr_opened")
  const anyOpened = opened.length > 0

  // Incident memory row.
  const stepLabel = ctx.incident.step != null ? `step ${ctx.incident.step}` : "unknown step"
  const summary = `${ctx.incident.kind ?? "incident"} at ${stepLabel}: ${ctx.diagnosis}. ${opened.length} PR${opened.length === 1 ? "" : "s"} opened.`
  const resolution = opened.length
    ? opened
        .map((r) => `${r.hypothesisTitle}: ${r.prUrl}`)
        .join("\n")
    : "No PRs opened."

  const memoryId = crypto.randomUUID()
  await db.insert(memoryTable).values({
    id: memoryId,
    projectId: ctx.projectId,
    incidentId: ctx.incidentId,
    kind: ctx.incident.kind,
    summary,
    resolution,
    data: { results, diagnosis: ctx.diagnosis },
  })

  // Dual-write to Redis: Postgres is the source of truth for the UI, Redis is
  // the semantic search index for the hypothesis agent. Never throws.
  await storeMemorySemantic({
    id: memoryId,
    projectId: ctx.projectId,
    kind: ctx.incident.kind,
    summary,
    resolution,
  })

  // Incident status.
  const winner = opened[0]
  await db
    .update(incidentTable)
    .set({
      status: anyOpened ? "resolved" : "failed",
      resolvedAt: new Date(),
      ...(winner ? { winnerAgentId: winner.agentId } : {}),
    })
    .where(eq(incidentTable.id, ctx.incidentId))

  // Project + run status.
  await db
    .update(projectTable)
    .set({ status: anyOpened ? "recovered" : "incident", updatedAt: new Date() })
    .where(eq(projectTable.id, ctx.projectId))

  await db
    .update(runTable)
    .set({ status: anyOpened ? "recovered" : "incident" })
    .where(eq(runTable.id, ctx.runId))

  await emitEvent({
    projectId: ctx.projectId,
    runId: ctx.runId,
    incidentId: ctx.incidentId,
    source: "server",
    level: anyOpened ? "info" : "warn",
    type: "incident.resolved",
    message: anyOpened
      ? `Incident resolved: ${opened.length} fix PR${opened.length === 1 ? "" : "s"} opened`
      : "Incident pipeline finished with no PRs",
    data: { results },
  })

  await sendIncidentReport({
    to: ctx.ownerEmail,
    project: { id: ctx.projectId, name: ctx.projectName },
    incident: {
      id: ctx.incidentId,
      kind: ctx.incident.kind,
      step: ctx.incident.step,
      diagnosis: ctx.diagnosis,
    },
    results: results.map((r) => ({
      agentId: r.agentId,
      state: r.state,
      prUrl: r.prUrl,
      error: r.error,
    })),
  })
}

// ===================================================================
// Report markdown (PR body)
// ===================================================================

function buildReport(
  ctx: PipelineContext,
  hypothesis: Hypothesis,
  diffStat: string,
  agentSummary: string,
): string {
  const conf =
    ctx.incident.confidence != null
      ? `${Math.round(ctx.incident.confidence * 100)}%`
      : "n/a"
  return `## 🤖 keepalive automated fix

### Incident
- **Failure:** \`${ctx.incident.kind ?? "unknown"}\`${ctx.incident.step != null ? ` at step ${ctx.incident.step}` : ""}
- **Monitor confidence (healthy):** ${conf}
- **Monitor reasoning:** ${ctx.incident.reasoning ?? "(none)"}

### Diagnosis
${ctx.diagnosis || "(none)"}

### This hypothesis
**${hypothesis.title}**

${hypothesis.detail}

_Approach:_ ${hypothesis.approach}

### What changed
\`\`\`
${diffStat}
\`\`\`

${agentSummary || "_(no agent summary)_"}

### How to validate
Check out this branch and resume training from the last good checkpoint; confirm the failure (\`${ctx.incident.kind ?? "the incident"}\`) no longer reproduces.

---
Opened automatically by [keepalive](${dashboardBaseUrl()}/projects/${ctx.projectId}). One of several parallel fix hypotheses for this incident.`
}
