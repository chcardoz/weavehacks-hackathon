import { OTLPHttpJsonTraceExporter, registerOTel } from "@vercel/otel";
import { trace } from "@opentelemetry/api";

const WEAVE_TRACE_URL = "https://trace.wandb.ai/otel/v1/traces";

let registered = false;

/**
 * Registers the Weave OTel exporter. AI SDK calls with
 * `experimental_telemetry.isEnabled` are then exported to trace.wandb.ai.
 * No-op when WANDB_API_KEY is unset (local dev / CI).
 */
export function registerWeaveTelemetry(): void {
  if (registered) return;

  const apiKey = process.env.WANDB_API_KEY;
  const project = process.env.WANDB_PROJECT;
  if (!apiKey || !project) return;

  const auth = Buffer.from(`api:${apiKey}`).toString("base64");

  registerOTel({
    serviceName: "keepalive-dashboard",
    traceExporter: new OTLPHttpJsonTraceExporter({
      url: WEAVE_TRACE_URL,
      headers: {
        Authorization: `Basic ${auth}`,
        project_id: project,
      },
    }),
  });

  registered = true;
}

/**
 * Force-flushes buffered spans. Serverless functions MUST await this before
 * returning or spans are silently dropped. No-op when telemetry isn't active.
 */
export async function flushTraces(): Promise<void> {
  if (!registered) return;

  const provider = trace.getTracerProvider() as unknown as {
    getDelegate?: () => unknown;
  };
  // ProxyTracerProvider → real provider (which exposes forceFlush()).
  const delegate =
    typeof provider.getDelegate === "function"
      ? provider.getDelegate()
      : provider;

  const flushable = delegate as { forceFlush?: () => Promise<void> };
  if (typeof flushable.forceFlush === "function") {
    await flushable.forceFlush();
  }
}
