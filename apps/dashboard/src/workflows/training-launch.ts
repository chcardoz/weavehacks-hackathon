import { eq } from "drizzle-orm"
import { Sandbox } from "@vercel/sandbox"

import { db } from "@/lib/db"
import { project, user } from "@/db/schema"
import { getGithubToken } from "@/lib/github"
import { emitEvent } from "@/lib/server-events"
import { LAUNCHER_SCRIPT } from "@/lib/launcher-script"
import { parseLauncherOutput } from "@/lib/launcher-output"

// Context resolved in step 1 and handed to the launch step. Secrets are carried
// only through workflow state (the Workflow runtime serializes this between
// steps); we never log them.
interface LaunchContext {
  ok: boolean
  reason?: string
  repo?: string // owner/name
  trainCommand?: string
  githubToken?: string
  wandbApiKey?: string
  trainingApiKey?: string
  keepaliveUrl?: string
}

interface LaunchResult {
  ok: boolean
  sandboxId?: string
  error?: string
}

// step 1 — gather everything the launcher needs and validate it up front so a
// missing key surfaces as a readable event instead of a sandbox crash.
async function loadLaunchContext(
  projectId: string,
  commitSha: string,
): Promise<LaunchContext> {
  "use step"

  const [proj] = await db
    .select()
    .from(project)
    .where(eq(project.id, projectId))
    .limit(1)

  if (!proj) {
    // No project row — nothing we can launch or even attribute an event to.
    return { ok: false, reason: "Project not found" }
  }

  await emitEvent({
    projectId,
    source: "github",
    type: "training.launching",
    message: `Preparing training launch for ${proj.repoOwner}/${proj.repoName} @ ${commitSha.slice(0, 7)}`,
    data: { commit_sha: commitSha },
  })

  const [owner] = await db
    .select({ wandbApiKey: user.wandbApiKey })
    .from(user)
    .where(eq(user.id, proj.userId))
    .limit(1)

  const githubToken = await getGithubToken(proj.userId)

  const missing: string[] = []
  if (!owner?.wandbApiKey) missing.push("Set your W&B API key in Settings")
  if (!githubToken)
    missing.push("Reconnect your GitHub account (no access token found)")
  if (!proj.trainingApiKey)
    missing.push("This project has no training API key — recreate the project")

  if (missing.length > 0) {
    const reason = missing.join("; ")
    await emitEvent({
      projectId,
      source: "github",
      level: "error",
      type: "training.failed",
      message: `Cannot launch training: ${reason}`,
      data: { commit_sha: commitSha, reason },
    })
    return { ok: false, reason }
  }

  return {
    ok: true,
    repo: `${proj.repoOwner}/${proj.repoName}`,
    trainCommand: proj.trainCommand,
    githubToken: githubToken ?? undefined,
    wandbApiKey: owner?.wandbApiKey ?? undefined,
    trainingApiKey: proj.trainingApiKey ?? undefined,
    keepaliveUrl:
      process.env.BETTER_AUTH_URL ??
      "https://weavehacks-hackathon-dashboard.vercel.app",
  }
}

// step 2 — spin up a Vercel Sandbox (python), pip-install the W&B Sandbox SDK,
// write + run launcher.py which itself starts a W&B Sandbox training run.
// Everything here is defensive: a preview-product failure must land as a
// readable event, not an unhandled workflow crash.
async function launchSandboxTraining(
  projectId: string,
  commitSha: string,
  ctx: LaunchContext,
): Promise<LaunchResult> {
  "use step"

  if (!ctx.ok) {
    return { ok: false, error: ctx.reason ?? "missing launch context" }
  }

  let sandbox: Sandbox | undefined
  try {
    sandbox = await Sandbox.create({
      runtime: "python3.13",
      resources: { vcpus: 2 },
      timeout: 10 * 60 * 1000, // ~10 minutes
    })

    // 1. Install the W&B Sandbox SDK.
    const install = await sandbox.runCommand({
      cmd: "pip",
      args: ["install", "wandb[sandbox]"],
    })
    if (install.exitCode !== 0) {
      const stderr = await install.stderr()
      const error = `pip install "wandb[sandbox]" failed (exit ${install.exitCode}): ${stderr.slice(-500)}`
      await emitEvent({
        projectId,
        source: "sandbox",
        level: "error",
        type: "training.failed",
        message: "Failed to install the W&B Sandbox SDK in the launcher sandbox",
        data: { commit_sha: commitSha, error },
      })
      return { ok: false, error }
    }

    // 2. Write the driver script.
    await sandbox.writeFiles([
      { path: "launcher.py", content: LAUNCHER_SCRIPT },
    ])

    // 3. Run it. Secrets travel via env, never via argv. WANDB_API_KEY must be
    //    present for the wandb sandbox client itself to authenticate.
    const run = await sandbox.runCommand({
      cmd: "python",
      args: ["launcher.py"],
      env: {
        LAUNCH_REPO: ctx.repo ?? "",
        LAUNCH_SHA: commitSha,
        LAUNCH_TRAIN_CMD: ctx.trainCommand ?? "python train.py",
        LAUNCH_GITHUB_TOKEN: ctx.githubToken ?? "",
        LAUNCH_WANDB_KEY: ctx.wandbApiKey ?? "",
        LAUNCH_KEEPALIVE_KEY: ctx.trainingApiKey ?? "",
        LAUNCH_KEEPALIVE_URL:
          ctx.keepaliveUrl ?? "https://weavehacks-hackathon-dashboard.vercel.app",
        WANDB_API_KEY: ctx.wandbApiKey ?? "",
      },
    })

    const stdout = await run.stdout()
    const parsed = parseLauncherOutput(stdout)

    if (parsed.error) {
      return { ok: false, error: parsed.error }
    }
    if (!parsed.sandboxId) {
      const stderr = await run.stderr()
      return {
        ok: false,
        error: `Launcher did not report a W&B sandbox id (exit ${run.exitCode}). ${stderr.slice(-500)}`,
      }
    }

    return { ok: true, sandboxId: parsed.sandboxId }
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    }
  } finally {
    if (sandbox) {
      try {
        await sandbox.stop()
      } catch (stopErr) {
        console.error("[training-launch] failed to stop sandbox:", stopErr)
      }
    }
  }
}

// step 3 — record the outcome. On success the W&B sandbox is now training; the
// run row is created later by the ingest path when the keepalive library inside
// the sandbox reports its run id, so we do NOT pre-create one here.
async function recordLaunch(
  projectId: string,
  commitSha: string,
  result: LaunchResult,
): Promise<void> {
  "use step"

  if (result.ok && result.sandboxId) {
    await db
      .update(project)
      .set({ status: "training", updatedAt: new Date() })
      .where(eq(project.id, projectId))

    await emitEvent({
      projectId,
      source: "sandbox",
      type: "training.launched",
      message: `Training launched in W&B sandbox ${result.sandboxId}`,
      data: { sandbox_id: result.sandboxId, commit_sha: commitSha },
    })
    return
  }

  await emitEvent({
    projectId,
    source: "sandbox",
    level: "error",
    type: "training.failed",
    message: `Training launch failed: ${result.error ?? "unknown error"}`,
    data: { commit_sha: commitSha, error: result.error ?? "unknown error" },
  })
}

// Orchestrates the launch. Triggered by start(trainingLaunch, [projectId, sha])
// from the GitHub push webhook.
export async function trainingLaunch(
  projectId: string,
  commitSha: string,
): Promise<void> {
  "use workflow"

  const ctx = await loadLaunchContext(projectId, commitSha)
  if (!ctx.ok) {
    // loadLaunchContext already emitted a readable training.failed event.
    return
  }

  const result = await launchSandboxTraining(projectId, commitSha, ctx)
  await recordLaunch(projectId, commitSha, result)
}
