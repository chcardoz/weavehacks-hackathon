import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const generateText = vi.hoisted(() => vi.fn());
const searchSemanticCache = vi.hoisted(() => vi.fn());
const storeSemanticCache = vi.hoisted(() => vi.fn());

vi.mock("ai", () => ({
  generateText,
  Output: { object: (cfg: unknown) => cfg },
}));

vi.mock("./semantic-cache", () => ({
  searchSemanticCache,
  storeSemanticCache,
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
  beforeEach(() => {
    // Default: cache miss, store is a no-op.
    searchSemanticCache.mockResolvedValue(null);
    storeSemanticCache.mockResolvedValue(undefined);
  });

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

  it("returns a cached verdict and skips the model on a cache hit", async () => {
    searchSemanticCache.mockResolvedValue(
      JSON.stringify({
        confidence: 0.4,
        reasoning: "cached divergence",
        signals: ["divergence"],
      }),
    );

    const verdict = await scoreMetrics(baseParams);
    expect(verdict).toEqual({
      confidence: 0.4,
      reasoning: "cached divergence",
      signals: ["divergence"],
    });
    expect(generateText).not.toHaveBeenCalled();
    expect(storeSemanticCache).not.toHaveBeenCalled();
  });

  it("ignores a malformed cache hit and falls through to the model", async () => {
    searchSemanticCache.mockResolvedValue("{not valid json");
    generateText.mockResolvedValue({
      output: { confidence: 1, reasoning: "ok", signals: ["none"] },
    });

    const verdict = await scoreMetrics(baseParams);
    expect(verdict.confidence).toBe(1);
    expect(generateText).toHaveBeenCalledOnce();
  });

  it("stores real model output but never the fallback verdict", async () => {
    generateText.mockResolvedValue({
      output: { confidence: 0.3, reasoning: "diverging", signals: ["divergence"] },
    });
    await scoreMetrics(baseParams);
    expect(storeSemanticCache).toHaveBeenCalledOnce();

    vi.clearAllMocks();
    searchSemanticCache.mockResolvedValue(null);
    generateText.mockRejectedValue(new Error("boom"));
    const verdict = await scoreMetrics(baseParams);
    expect(verdict.confidence).toBe(1);
    expect(storeSemanticCache).not.toHaveBeenCalled();
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

  it("routes legacy W&B monitor ids to the Gateway mini model", async () => {
    generateText.mockResolvedValue({
      output: { confidence: 1, reasoning: "ok", signals: ["none"] },
    });

    await scoreMetrics({
      ...baseParams,
      monitorModel: "wandb/microsoft/Phi-4-mini-instruct",
    });

    expect(generateText.mock.calls[0][0].model).toBe("openai/gpt-5.4-mini");
  });
});
