export const MONITOR_MODEL_DEFAULT = "openai/gpt-5.4-mini";
export const LEGACY_WANDB_MONITOR_MODEL =
  "wandb/microsoft/Phi-4-mini-instruct";

export const MONITOR_MODEL_OPTIONS = [
  MONITOR_MODEL_DEFAULT,
  "openai/gpt-5.4",
] as const;

export function normalizeMonitorModel(modelId: string): string {
  if (modelId === LEGACY_WANDB_MONITOR_MODEL || modelId.startsWith("wandb/")) {
    return MONITOR_MODEL_DEFAULT;
  }
  return modelId;
}
