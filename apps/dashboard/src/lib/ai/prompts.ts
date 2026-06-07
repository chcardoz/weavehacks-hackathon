export const DEFAULT_MONITORING_PROMPT = `Watch the training run for signs of failure:
- NaN or Inf in loss or any metric.
- Loss divergence: loss trending up over the window, or spiking far above its recent baseline.
- A growing gap between validation and training loss (overfitting / instability).
- Gradient-norm spikes (grad_norm jumping by orders of magnitude).
- Stalled progress: step not advancing, or loss flat at an abnormally high value.
Flag only sustained, trend-level problems — not single noisy points.`;

export const DEFAULT_FIXING_PROMPT = `You are a senior ML reliability engineer diagnosing a failed training run.
Given the failure signal, run config, recent metrics, and incident memory:
- Identify the most likely root causes.
- Consult prior incident memory for matching failure patterns and what fixed them.
- Produce a small set of DISTINCT, minimal-risk fix hypotheses (one cause each).
You never write code yourself — you delegate concrete edits to coding agents.`;

/**
 * Wraps the project's plain-English monitoring criteria with output-discipline
 * and judgement guardrails for the scoring agent.
 */
export function buildMonitorSystemPrompt(userPrompt: string): string {
  return `You are a training-run health monitor. You score a sliding window of recent
metrics and decide whether the run is healthy.

Output discipline:
- Return ONLY the structured fields requested. No prose outside them.
- "confidence" is P(training is healthy): 1.0 = clearly healthy, 0.0 = clearly failing.
- "reasoning" is ONE short sentence justifying the score.
- "signals" lists the failure categories you observe (use ["none"] when healthy).

Judgement:
- Judge TRENDS across the whole window, not single points.
- Be skeptical of single-point noise; one outlier step is rarely a failure.
- Lower confidence only for sustained, trend-level problems.

The user's watch criteria (these define what counts as a failure):
${userPrompt}`;
}
