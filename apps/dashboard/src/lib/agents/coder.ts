import type { Sandbox } from "@vercel/sandbox"
import { ToolLoopAgent, stepCountIs } from "ai"
import { op } from "weave"

import { CODER_MODEL, resolveModel } from "@/lib/ai"
import { makeSandboxTools } from "./sandbox-tools"
import type { Hypothesis } from "./hypothesis"

export interface RunCoderParams {
  sandbox: Sandbox
  repoRoot: string
  hypothesis: Hypothesis
  diagnosis: string
  incidentId: string
  agentId: string
}

export interface RunCoderResult {
  /** The agent's own final natural-language summary of what it changed. */
  summary: string
  /** Number of LLM steps taken. */
  steps: number
}

const CODER_MAX_STEPS = 30

function buildInstructions(hypothesis: Hypothesis, diagnosis: string): string {
  return `You are an automated coding agent fixing a failed ML training run. You work inside a checked-out git repository at the repo root.

DIAGNOSIS (from the lead engineer):
${diagnosis}

YOUR ASSIGNED HYPOTHESIS — implement THIS one only:
Title: ${hypothesis.title}
Why: ${hypothesis.detail}
Approach: ${hypothesis.approach}

GROUND RULES:
- Make the MINIMAL change that implements this hypothesis. Do not refactor or fix unrelated things.
- Match the existing code style, indentation, and conventions.
- Before editing, READ the relevant files and use grep/glob to locate the code. Verify your assumptions.
- Use the 'edit' tool for surgical changes (exact-match, unique context). Use 'write' only for whole-file rewrites.
- After editing, re-read the changed regions to confirm the change is correct and the file is not broken.
- You are already in the repo root; paths are relative to it. Do NOT run git, commit, or push — that is handled for you.
- When done, write a SHORT final message summarizing exactly what you changed and why (file names + the gist). This becomes the PR report.`
}

/**
 * Runs the coding agent loop over the sandbox. The agent reads/edits files and
 * runs shell commands via the sandbox tools, implementing exactly one hypothesis.
 * Returns the agent's final summary text. Throws only on a hard model failure
 * (the caller's step try/catch records it).
 */
export async function runCoder(params: RunCoderParams): Promise<RunCoderResult> {
  const { sandbox, repoRoot, hypothesis, diagnosis, incidentId, agentId } =
    params

  const tools = makeSandboxTools(sandbox, repoRoot)

  const agent = new ToolLoopAgent({
    model: resolveModel(CODER_MODEL),
    instructions: buildInstructions(hypothesis, diagnosis),
    tools,
    stopWhen: stepCountIs(CODER_MAX_STEPS),
    experimental_telemetry: {
      isEnabled: true,
      functionId: "coder.run",
      metadata: { incidentId, agentId },
    },
  })

  // Trace only the serializable inputs (the assigned hypothesis + ids); the
  // sandbox/agent/tools are captured via closure so Weave never tries to
  // serialize them. The op records the agent's final PR-report summary.
  const traced = op(
    async (
      _hypothesis: Hypothesis,
      _diagnosis: string,
      _incidentId: string,
      _agentId: string,
    ): Promise<RunCoderResult> => {
      const result = await agent.generate({
        prompt: `Implement the assigned hypothesis now. Start by exploring the repo to find the relevant code.`,
      })
      return { summary: result.text, steps: result.steps.length }
    },
    {
      name: "coder.run",
      parameterNames: ["hypothesis", "diagnosis", "incidentId", "agentId"],
    },
  )

  return traced(hypothesis, diagnosis, incidentId, agentId)
}
