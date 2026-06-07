import { describe, expect, it } from "vitest";

import { buildMonitorSystemPrompt } from "./prompts";

describe("buildMonitorSystemPrompt", () => {
  it("embeds the user's monitoring criteria verbatim", () => {
    const user = "Flag if val/loss diverges from train/loss.";
    const out = buildMonitorSystemPrompt(user);
    expect(out).toContain(user);
  });

  it("includes output-discipline guardrails", () => {
    const out = buildMonitorSystemPrompt("anything");
    expect(out).toContain("P(training is healthy)");
    expect(out.toLowerCase()).toContain("trend");
  });
});
