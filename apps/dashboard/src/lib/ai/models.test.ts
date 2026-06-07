import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveModel } from "./models";

describe("resolveModel", () => {
  const orig = { ...process.env };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    process.env = { ...orig };
  });

  it("returns non-wandb ids unchanged (gateway routing)", () => {
    expect(resolveModel("openai/gpt-5.4")).toBe("openai/gpt-5.4");
    expect(resolveModel("openai/gpt-5.4-mini")).toBe("openai/gpt-5.4-mini");
  });

  it("returns a provider model object for wandb/ ids when key set", () => {
    process.env.WANDB_API_KEY = "test-key";
    const model = resolveModel("wandb/microsoft/Phi-4-mini-instruct");
    expect(typeof model).not.toBe("string");
    expect(model).toBeTruthy();
  });

  it("falls back to gpt-5.4-mini with a warn when WANDB_API_KEY unset", () => {
    delete process.env.WANDB_API_KEY;
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const model = resolveModel("wandb/microsoft/Phi-4-mini-instruct");
    expect(model).toBe("openai/gpt-5.4-mini");
    expect(warn).toHaveBeenCalledOnce();
  });
});
