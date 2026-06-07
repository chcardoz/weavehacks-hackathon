import { createOpenAICompatible } from "@ai-sdk/openai-compatible";
import type { LanguageModel } from "ai";
import { MONITOR_MODEL_DEFAULT } from "./model-ids";

export { MONITOR_MODEL_DEFAULT } from "./model-ids";

export const HYPOTHESIS_MODEL = "openai/gpt-5.4";
export const CODER_MODEL = "openai/gpt-5.4";

const WANDB_FALLBACK = MONITOR_MODEL_DEFAULT;

/**
 * Resolves a model id to an AI SDK model.
 *
 * - `wandb/<id>` routes through W&B Inference (OpenAI-compatible). Falls back to
 *   the gateway when WANDB_API_KEY is unset.
 * - anything else is returned as a plain string for Vercel AI Gateway routing.
 */
export function resolveModel(modelId: string): LanguageModel {
  if (modelId.startsWith("wandb/")) {
    const rest = modelId.slice("wandb/".length);
    const apiKey = process.env.WANDB_API_KEY;
    if (!apiKey) {
      console.warn(
        `[ai/models] WANDB_API_KEY unset; falling back to ${WANDB_FALLBACK} for "${modelId}"`,
      );
      return WANDB_FALLBACK;
    }
    const provider = createOpenAICompatible({
      name: "wandb-inference",
      baseURL: "https://api.inference.wandb.ai/v1",
      apiKey,
      headers: { "OpenAI-Project": process.env.WANDB_PROJECT ?? "" },
    });
    return provider(rest);
  }

  return modelId;
}
