import type { Sandbox } from "@vercel/sandbox"
import { tool } from "ai"
import { z } from "zod"

import { applyEdit, numberLines, truncateOutput } from "./text-utils"

// opencode-inspired filesystem + shell tools, implemented over a live Vercel
// Sandbox. Every `execute` returns a string and NEVER throws — on any failure it
// returns an `ERROR: ...` string so the tool loop can read the error and react.

const DEFAULT_BASH_TIMEOUT_SEC = 120

function errString(prefix: string, err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err)
  return `ERROR: ${prefix}: ${msg}`
}

/**
 * Runs `bash -lc <command>` in the sandbox at `repoRoot`, returning combined
 * stdout+stderr (truncated) with an exit-code header.
 */
async function runBash(
  sandbox: Sandbox,
  repoRoot: string,
  command: string,
  timeoutSec: number,
): Promise<string> {
  const result = await sandbox.runCommand({
    cmd: "bash",
    args: ["-lc", command],
    cwd: repoRoot,
    timeoutMs: timeoutSec * 1000,
  })
  const stdout = await result.stdout()
  const stderr = await result.stderr()
  const combined = [stdout, stderr].filter(Boolean).join("\n")
  const body = truncateOutput(combined)
  return `exit code: ${result.exitCode}\n${body}`.trimEnd()
}

export function makeSandboxTools(sandbox: Sandbox, repoRoot: string) {
  const read = tool({
    description:
      "Read a file from the repository. Returns line-numbered content (capped). Use offset/limit to page through large files.",
    inputSchema: z.object({
      filePath: z
        .string()
        .describe("Path to the file, relative to the repo root or absolute."),
      offset: z
        .number()
        .int()
        .min(0)
        .optional()
        .describe("0-based line to start reading from."),
      limit: z.number().int().min(1).optional().describe("Max lines to read."),
    }),
    execute: async ({ filePath, offset, limit }) => {
      try {
        const path = resolvePath(repoRoot, filePath)
        const buf = await sandbox.readFileToBuffer({ path })
        if (buf === null) return `ERROR: file not found: ${filePath}`
        return numberLines(buf.toString("utf8"), { offset, limit })
      } catch (err) {
        return errString(`read ${filePath}`, err)
      }
    },
  })

  const write = tool({
    description:
      "Write (create or overwrite) a file with the given content. Prefer `edit` for small changes to existing files.",
    inputSchema: z.object({
      filePath: z.string().describe("Path to the file to write."),
      content: z.string().describe("Full new file content."),
    }),
    execute: async ({ filePath, content }) => {
      try {
        const path = resolvePath(repoRoot, filePath)
        await sandbox.writeFiles([{ path, content }])
        return `wrote ${Buffer.byteLength(content, "utf8")} bytes to ${filePath}`
      } catch (err) {
        return errString(`write ${filePath}`, err)
      }
    },
  })

  const edit = tool({
    description:
      "Make an exact-string edit to an existing file. oldString must appear in the file; unless replaceAll is set it must be UNIQUE — include enough surrounding context to make it unique.",
    inputSchema: z.object({
      filePath: z.string().describe("Path to the file to edit."),
      oldString: z.string().describe("Exact text to replace."),
      newString: z.string().describe("Replacement text."),
      replaceAll: z
        .boolean()
        .optional()
        .describe("Replace every occurrence instead of requiring uniqueness."),
    }),
    execute: async ({ filePath, oldString, newString, replaceAll }) => {
      try {
        const path = resolvePath(repoRoot, filePath)
        const buf = await sandbox.readFileToBuffer({ path })
        if (buf === null) return `ERROR: file not found: ${filePath}`
        const result = applyEdit(
          buf.toString("utf8"),
          oldString,
          newString,
          replaceAll ?? false,
        )
        if (!result.ok || result.content === undefined) {
          return `ERROR: edit ${filePath}: ${result.error}`
        }
        await sandbox.writeFiles([{ path, content: result.content }])
        return `edited ${filePath}`
      } catch (err) {
        return errString(`edit ${filePath}`, err)
      }
    },
  })

  const bash = tool({
    description:
      "Run a shell command (bash -lc) in the repo root. Use this to inspect, build, lint, or test. Output is truncated to the tail.",
    inputSchema: z.object({
      command: z.string().describe("Shell command to run."),
      timeoutSec: z
        .number()
        .int()
        .min(1)
        .max(600)
        .optional()
        .describe(`Timeout in seconds (default ${DEFAULT_BASH_TIMEOUT_SEC}).`),
    }),
    execute: async ({ command, timeoutSec }) => {
      try {
        return await runBash(
          sandbox,
          repoRoot,
          command,
          timeoutSec ?? DEFAULT_BASH_TIMEOUT_SEC,
        )
      } catch (err) {
        return errString(`bash`, err)
      }
    },
  })

  const grep = tool({
    description:
      "Search file contents with grep (recursive, line numbers). Optionally restrict to a path and a glob include pattern.",
    inputSchema: z.object({
      pattern: z.string().describe("Pattern to search for (grep ERE)."),
      path: z.string().optional().describe("Directory or file to search in."),
      include: z
        .string()
        .optional()
        .describe("Glob to restrict files, e.g. '*.py'."),
    }),
    execute: async ({ pattern, path, include }) => {
      try {
        const includeArg = include ? `--include=${shellQuote(include)} ` : ""
        const target = path ? shellQuote(path) : "."
        const cmd = `grep -rnI ${includeArg}-e ${shellQuote(pattern)} ${target} | head -n 200`
        const out = await runBash(sandbox, repoRoot, cmd, 60)
        return out
      } catch (err) {
        return errString(`grep`, err)
      }
    },
  })

  const glob = tool({
    description:
      "List files matching a glob pattern (find-based). Returns up to 200 paths.",
    inputSchema: z.object({
      pattern: z
        .string()
        .describe("Glob pattern, e.g. '**/*.py' or 'src/*.ts'."),
    }),
    execute: async ({ pattern }) => {
      try {
        // -path matches against the whole path; translate ** loosely to *.
        const findPattern = pattern.includes("/")
          ? `*${pattern.replace(/\*\*/g, "*")}`
          : pattern
        const cmd = `find . -type f -path ${shellQuote(findPattern)} -not -path './.git/*' | head -n 200`
        return await runBash(sandbox, repoRoot, cmd, 60)
      } catch (err) {
        return errString(`glob`, err)
      }
    },
  })

  return { read, write, edit, bash, grep, glob }
}

export type SandboxTools = ReturnType<typeof makeSandboxTools>

// --- helpers ---

function resolvePath(repoRoot: string, filePath: string): string {
  if (filePath.startsWith("/")) return filePath
  const root = repoRoot.endsWith("/") ? repoRoot.slice(0, -1) : repoRoot
  return `${root}/${filePath}`
}

function shellQuote(value: string): string {
  // Single-quote and escape embedded single quotes for safe bash interpolation.
  return `'${value.replace(/'/g, `'\\''`)}'`
}
