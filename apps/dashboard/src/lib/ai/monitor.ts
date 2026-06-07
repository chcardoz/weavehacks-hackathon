import { Output, generateText } from "ai";
import { z } from "zod";

import { normalizeMonitorModel } from "./model-ids";
import { resolveModel } from "./models";
import { buildMonitorSystemPrompt } from "./prompts";
import { searchSemanticCache, storeSemanticCache } from "./semantic-cache";

const MONITOR_TIMEOUT_MS = 15_000;

export const MONITOR_SIGNALS = [
  "nan",
  "divergence",
  "stall",
  "oom",
  "plateau",
  "grad_explosion",
  "none",
] as const;

export type MonitorSignal = (typeof MONITOR_SIGNALS)[number];

const monitorSchema = z.object({
  confidence: z.number().min(0).max(1),
  reasoning: z.string(),
  signals: z.array(z.enum(MONITOR_SIGNALS)),
});

export type MonitorVerdict = z.infer<typeof monitorSchema>;

/**
 * Parses a cached verdict string and validates it against `monitorSchema`.
 * Returns the verdict on success, or null if the payload is malformed or fails
 * validation (so the caller falls through to the model).
 */
export function parseCachedVerdict(raw: string): MonitorVerdict | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  const result = monitorSchema.safeParse(parsed);
  return result.success ? result.data : null;
}

export interface MetricsWindowEntry {
  step: number;
  metrics: Record<string, number | null>;
}

export interface ScoreMetricsParams {
  monitorModel: string;
  monitoringPrompt: string;
  metricsWindow: MetricsWindowEntry[];
  projectId: string;
  runId: string;
  /** Optional incident-memory context to bias the verdict. */
  incidentContext?: string;
}

/**
 * Scores a window of recent training metrics against the project's monitoring
 * prompt. NEVER throws — on any error (timeout, model, parse) it returns a safe
 * "healthy" verdict so the ingest path is never blocked.
 */
export async function scoreMetrics(
  params: ScoreMetricsParams,
): Promise<MonitorVerdict> {
  const {
    monitorModel,
    monitoringPrompt,
    metricsWindow,
    projectId,
    runId,
    incidentContext,
  } = params;

  try {
    const promptBody = {
      metricsWindow,
      ...(incidentContext ? { incidentContext } : {}),
    };

    // Key the cache on the watch criteria + metrics so different monitoring
    // prompts never share verdicts.
    const cachePrompt = monitoringPrompt + "\n" + JSON.stringify(promptBody);

    const cachedRaw = await searchSemanticCache(cachePrompt);
    if (cachedRaw !== null) {
      const cached = parseCachedVerdict(cachedRaw);
      if (cached) return cached;
    }

    const { output } = await generateText({
      model: resolveModel(normalizeMonitorModel(monitorModel)),
      system: buildMonitorSystemPrompt(monitoringPrompt),
      prompt: JSON.stringify(promptBody),
      output: Output.object({ schema: monitorSchema }),
      abortSignal: AbortSignal.timeout(MONITOR_TIMEOUT_MS),
      experimental_telemetry: {
        isEnabled: true,
        functionId: "monitor.score",
        metadata: { projectId, runId },
      },
    });

    // Only cache real model output — never the catch-branch fallback verdict.
    await storeSemanticCache(cachePrompt, JSON.stringify(output));

    return output;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      confidence: 1,
      reasoning: `monitor unavailable: ${msg}`,
      signals: ["none"],
    };
  }
}
