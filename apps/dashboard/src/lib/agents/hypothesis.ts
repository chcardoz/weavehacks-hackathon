import { Output, ToolLoopAgent, generateText, stepCountIs, tool } from "ai"
import { and, desc, eq, ilike, or } from "drizzle-orm"
import { z } from "zod"

import { db } from "@/lib/db"
import { memory } from "@/db/schema"
import {
  DEFAULT_FIXING_PROMPT,
  HYPOTHESIS_MODEL,
  resolveModel,
} from "@/lib/ai"

export interface HypothesisInput {
  projectId: string
  incidentId: string
  fixingPrompt: string | null
  maxAgents: number
  incident: {
    kind: string | null
    step: number | null
    confidence: number | null
    reasoning: string | null
  }
  /** Tail of the run's metrics window (most recent entries). */
  metricsTail: unknown[]
  /** Recent error/incident events for the run. */
  errorEvents: { type: string; message: string; data?: unknown }[]
  /** Recent incident-memory rows for the project (baseline context). */
  recentMemory?: {
    kind: string | null
    summary: string
    resolution: string | null
  }[]
}

export interface Hypothesis {
  title: string
  detail: string
  approach: string
}

export interface HypothesisOutput {
  diagnosis: string
  hypotheses: Hypothesis[]
}

const hypothesisSchema = z.object({
  diagnosis: z
    .string()
    .describe("One-paragraph root-cause summary of the failure."),
  hypotheses: z
    .array(
      z.object({
        title: z.string().describe("Short imperative fix title."),
        detail: z
          .string()
          .describe("Why this is a likely cause and what the fix targets."),
        approach: z
          .string()
          .describe("Concrete change a coding agent should make."),
      }),
    )
    .min(1),
})

/**
 * Drizzle-backed incident-memory search: ILIKE on summary/kind for this project,
 * most-recent first, top 5. Used as the hypothesis agent's only tool.
 */
async function searchProjectMemory(
  projectId: string,
  query: string,
): Promise<string> {
  const pattern = `%${query}%`
  const matchClause = query.trim()
    ? or(ilike(memory.summary, pattern), ilike(memory.kind, pattern))
    : undefined

  const rows = await db
    .select({
      kind: memory.kind,
      summary: memory.summary,
      resolution: memory.resolution,
      createdAt: memory.createdAt,
    })
    .from(memory)
    .where(and(eq(memory.projectId, projectId), matchClause))
    .orderBy(desc(memory.createdAt))
    .limit(5)

  if (rows.length === 0) return "No matching incident memory."
  return JSON.stringify(rows)
}

/**
 * Runs the hypothesis agent: a short tool-loop that may consult incident memory,
 * followed by one structured generation producing a diagnosis + distinct
 * hypotheses (clamped to maxAgents). NO code tools.
 */
export async function generateHypotheses(
  input: HypothesisInput,
): Promise<HypothesisOutput> {
  const system = input.fixingPrompt ?? DEFAULT_FIXING_PROMPT
  const model = resolveModel(HYPOTHESIS_MODEL)

  const telemetry = {
    isEnabled: true as const,
    functionId: "hypothesis.generate",
    metadata: { incidentId: input.incidentId, projectId: input.projectId },
  }

  const searchIncidentMemory = tool({
    description:
      "Search this project's incident memory for prior failures matching a query (failure kind, symptom, or keyword). Returns the top matches with their summaries and resolutions.",
    inputSchema: z.object({
      query: z
        .string()
        .describe("Keywords describing the failure, e.g. 'nan loss high lr'."),
    }),
    execute: async ({ query }) => searchProjectMemory(input.projectId, query),
  })

  const context = JSON.stringify({
    incident: input.incident,
    recentMetrics: input.metricsTail,
    recentErrorEvents: input.errorEvents,
    recentIncidentMemory: input.recentMemory ?? [],
    maxHypotheses: input.maxAgents,
  })

  const investigation = `Investigate this training failure. First, search incident memory for matching past failures, then reason about the most likely root causes.

Failure context:
${context}`

  // Phase 1: short tool-loop investigation (may call searchIncidentMemory).
  const agent = new ToolLoopAgent({
    model,
    instructions: system,
    tools: { searchIncidentMemory },
    stopWhen: stepCountIs(4),
    experimental_telemetry: telemetry,
  })

  let investigationNotes = ""
  try {
    const result = await agent.generate({ prompt: investigation })
    investigationNotes = result.text
  } catch {
    investigationNotes = ""
  }

  // Phase 2: structured diagnosis + hypotheses.
  const { output } = await generateText({
    model,
    system,
    prompt: `${investigation}

Investigation notes:
${investigationNotes || "(none)"}

Produce a concise diagnosis and AT MOST ${input.maxAgents} DISTINCT, minimal-risk fix hypotheses — each targeting a different root cause. Do not propose duplicates.`,
    output: Output.object({ schema: hypothesisSchema }),
    experimental_telemetry: telemetry,
  })

  const hypotheses = output.hypotheses.slice(0, Math.max(1, input.maxAgents))
  return { diagnosis: output.diagnosis, hypotheses }
}
