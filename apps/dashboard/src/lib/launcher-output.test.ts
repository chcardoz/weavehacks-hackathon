import { describe, expect, it } from "vitest"

import { parseLauncherOutput } from "./launcher-output"

describe("parseLauncherOutput", () => {
  it("extracts the sandbox id from a clean success line", () => {
    expect(parseLauncherOutput("WANDB_SANDBOX_ID=sbx_abc123")).toEqual({
      sandboxId: "sbx_abc123",
      error: null,
    })
  })

  it("extracts the sandbox id amid pip noise", () => {
    const out = [
      "Collecting wandb",
      "Successfully installed wandb-0.18.0",
      "WANDB_SANDBOX_ID=sbx_xyz",
    ].join("\n")
    expect(parseLauncherOutput(out)).toEqual({
      sandboxId: "sbx_xyz",
      error: null,
    })
  })

  it("extracts an error message", () => {
    expect(
      parseLauncherOutput("LAUNCH_ERROR=quota exceeded for sandboxes"),
    ).toEqual({ sandboxId: null, error: "quota exceeded for sandboxes" })
  })

  it("prefers an error over a sandbox id", () => {
    const out = "WANDB_SANDBOX_ID=sbx_1\nLAUNCH_ERROR=boom"
    expect(parseLauncherOutput(out)).toEqual({
      sandboxId: null,
      error: "boom",
    })
  })

  it("trims surrounding whitespace and handles CRLF", () => {
    expect(parseLauncherOutput("  WANDB_SANDBOX_ID=sbx_trim  \r\n")).toEqual({
      sandboxId: "sbx_trim",
      error: null,
    })
  })

  it("returns nulls when no marker is present", () => {
    expect(parseLauncherOutput("just some logs\nnothing here")).toEqual({
      sandboxId: null,
      error: null,
    })
  })

  it("ignores empty marker values", () => {
    expect(parseLauncherOutput("WANDB_SANDBOX_ID=\nLAUNCH_ERROR=")).toEqual({
      sandboxId: null,
      error: null,
    })
  })

  it("takes the last sandbox id when several appear", () => {
    const out = "WANDB_SANDBOX_ID=sbx_old\nWANDB_SANDBOX_ID=sbx_new"
    expect(parseLauncherOutput(out)).toEqual({
      sandboxId: "sbx_new",
      error: null,
    })
  })
})
