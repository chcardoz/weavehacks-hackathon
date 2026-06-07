import { afterEach, describe, expect, it, vi } from "vitest";

const generateText = vi.hoisted(() => vi.fn());

vi.mock("ai", () => ({
  generateText,
  Output: { object: (cfg: unknown) => cfg },
}));

import { scoreMetrics, type ScoreMetricsParams } from "./monitor";

const baseParams: ScoreMetricsParams = {
  monitorModel: "openai/gpt-5.4-mini",
  monitoringPrompt: "Flag NaN loss.",
  metricsWindow: [{ step: 1, metrics: { loss: 0.5 } }],
  projectId: "proj_1",
  runId: "run_1",
};

describe("scoreMetrics", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns the model's structured verdict on success", async () => {
    generateText.mockResolvedValue({
      output: {
        confidence: 0.2,
        reasoning: "loss is NaN",
        signals: ["nan"],
      },
    });

    const verdict = await scoreMetrics(baseParams);
    expect(verdict).toEqual({
      confidence: 0.2,
      reasoning: "loss is NaN",
      signals: ["nan"],
    });
    expect(generateText).toHaveBeenCalledOnce();
  });

  it("returns the safe healthy verdict on ANY error", async () => {
    generateText.mockRejectedValue(new Error("boom"));

    const verdict = await scoreMetrics(baseParams);
    expect(verdict.confidence).toBe(1);
    expect(verdict.signals).toEqual(["none"]);
    expect(verdict.reasoning).toContain("monitor unavailable");
    expect(verdict.reasoning).toContain("boom");
  });

  it("passes telemetry metadata to generateText", async () => {
    generateText.mockResolvedValue({
      output: { confidence: 1, reasoning: "ok", signals: ["none"] },
    });

    await scoreMetrics(baseParams);
    const arg = generateText.mock.calls[0][0];
    expect(arg.experimental_telemetry).toMatchObject({
      isEnabled: true,
      functionId: "monitor.score",
      metadata: { projectId: "proj_1", runId: "run_1" },
    });
  });
});
