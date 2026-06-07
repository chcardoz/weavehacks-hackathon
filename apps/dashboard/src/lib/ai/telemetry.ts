import type { WeaveClient } from "weave";

/**
 * Native W&B Weave tracing.
 *
 * We use the `weave` SDK directly (NOT OpenTelemetry): `initWeave()` calls
 * `weave.init()` once per process, and the agent entry points (monitor.score,
 * hypothesis.generate, coder.run) are wrapped in `weave.op(...)` so their
 * inputs/outputs upload to trace.wandb.ai as a call tree.
 *
 * Weave reads WANDB_API_KEY from the env itself; we pass WANDB_PROJECT (full
 * `entity/project` form) to init. No-op when either is unset (local dev / CI).
 */

let client: WeaveClient | null = null;
let initPromise: Promise<void> | null = null;

/**
 * Initializes the global Weave client exactly once per process. Idempotent and
 * never throws — tracing must never break a request. Safe to call at the top of
 * any serverless handler or workflow step (cheap after the first call).
 */
export function initWeave(): Promise<void> {
  if (initPromise) return initPromise;

  initPromise = (async () => {
    // weave is node-only; skip on the edge runtime.
    if (process.env.NEXT_RUNTIME && process.env.NEXT_RUNTIME !== "nodejs") {
      return;
    }

    const project = process.env.WANDB_PROJECT;
    const apiKey = process.env.WANDB_API_KEY;
    if (!project || !apiKey) return;

    try {
      // Dynamic import keeps weave out of any edge bundle.
      const weave = await import("weave");
      client = await weave.init(project);
    } catch (err) {
      // Swallow: a tracing failure must not take down ingest / fixing.
      console.error("[weave] init failed:", err);
      client = null;
    }
  })();

  return initPromise;
}

/**
 * Flushes pending Weave calls. Serverless functions MUST await this before
 * returning or batched spans are silently dropped. No-op when Weave isn't
 * initialized.
 */
export async function flushTraces(): Promise<void> {
  if (!client) return;
  try {
    await client.waitForBatchProcessing();
  } catch (err) {
    console.error("[weave] flush failed:", err);
  }
}
