// Parses the single machine-readable line the launcher.py driver prints.
// Success: `WANDB_SANDBOX_ID=<id>`. Failure: `LAUNCH_ERROR=<msg>`.
//
// The driver may emit other noise (pip output, etc.) so we scan all lines and
// take the LAST matching marker of each kind. An error marker wins over a
// success marker (the launcher exits non-zero on error).

export interface LauncherResult {
  sandboxId: string | null
  error: string | null
}

export function parseLauncherOutput(stdout: string): LauncherResult {
  let sandboxId: string | null = null
  let error: string | null = null

  for (const rawLine of stdout.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (line.startsWith("WANDB_SANDBOX_ID=")) {
      const v = line.slice("WANDB_SANDBOX_ID=".length).trim()
      if (v) sandboxId = v
    } else if (line.startsWith("LAUNCH_ERROR=")) {
      const v = line.slice("LAUNCH_ERROR=".length).trim()
      if (v) error = v
    }
  }

  // An explicit error supersedes any sandbox id.
  if (error) return { sandboxId: null, error }
  return { sandboxId, error: null }
}
