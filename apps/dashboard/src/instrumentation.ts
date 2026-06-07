export async function register() {
  // weave is node-only; gate the import behind the nodejs runtime so it's never
  // pulled into the edge instrumentation bundle (serverExternalPackages does not
  // apply to instrumentation).
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { initWeave } = await import("@/lib/ai/telemetry");
    await initWeave();
  }
}
