// Pure string helpers shared by the sandbox tools. Kept side-effect-free so the
// tricky bits (edit uniqueness guard, output truncation, line numbering) are unit
// testable without a live sandbox or LLM.

export interface EditResult {
  ok: boolean
  content?: string
  error?: string
}

/**
 * opencode-style exact-match edit with a uniqueness guard.
 *
 * - `oldString` must be present in `source`.
 * - When `replaceAll` is false, `oldString` must occur EXACTLY once (otherwise the
 *   edit is ambiguous and is rejected with a count).
 * - `oldString` and `newString` must differ.
 *
 * Returns the new file content or an error message — never throws.
 */
export function applyEdit(
  source: string,
  oldString: string,
  newString: string,
  replaceAll = false,
): EditResult {
  if (oldString === newString) {
    return { ok: false, error: "oldString and newString are identical" }
  }
  if (oldString === "") {
    return { ok: false, error: "oldString must not be empty" }
  }

  const count = countOccurrences(source, oldString)
  if (count === 0) {
    return { ok: false, error: "oldString not found in file" }
  }
  if (!replaceAll && count > 1) {
    return {
      ok: false,
      error: `oldString is not unique: found ${count} occurrences. Provide more surrounding context to disambiguate, or set replaceAll.`,
    }
  }

  const content = replaceAll
    ? source.split(oldString).join(newString)
    : source.replace(oldString, newString)

  return { ok: true, content }
}

/** Counts non-overlapping occurrences of `needle` in `haystack`. */
export function countOccurrences(haystack: string, needle: string): number {
  if (needle === "") return 0
  let count = 0
  let idx = haystack.indexOf(needle)
  while (idx !== -1) {
    count++
    idx = haystack.indexOf(needle, idx + needle.length)
  }
  return count
}

export interface TruncateOptions {
  maxLines?: number
  maxBytes?: number
}

/**
 * Truncates command output to the LAST `maxLines` lines and at most `maxBytes`
 * bytes, prepending a one-line `...truncated...` header noting what was dropped.
 * Tail-biased because the useful signal (errors, final status) is usually at the
 * end of build/test logs.
 */
export function truncateOutput(
  output: string,
  opts: TruncateOptions = {},
): string {
  const maxLines = opts.maxLines ?? 200
  const maxBytes = opts.maxBytes ?? 16_384

  if (output === "") return ""

  const lines = output.split("\n")
  let droppedLines = 0
  let kept = lines
  if (lines.length > maxLines) {
    droppedLines = lines.length - maxLines
    kept = lines.slice(lines.length - maxLines)
  }

  let body = kept.join("\n")

  // Byte cap (UTF-8 aware) on the line-trimmed body, taking the tail.
  let droppedBytes = 0
  const bodyBytes = Buffer.byteLength(body, "utf8")
  if (bodyBytes > maxBytes) {
    const buf = Buffer.from(body, "utf8")
    const sliced = buf.subarray(buf.length - maxBytes)
    droppedBytes = buf.length - sliced.length
    body = sliced.toString("utf8")
  }

  if (droppedLines === 0 && droppedBytes === 0) {
    return body
  }

  const parts: string[] = []
  if (droppedLines > 0) parts.push(`${droppedLines} earlier lines`)
  if (droppedBytes > 0) parts.push(`${droppedBytes} earlier bytes`)
  return `...truncated ${parts.join(" and ")}...\n${body}`
}

/**
 * Renders file content with 1-based line numbers (`N: ...`), supporting an
 * optional 0-based `offset` window and a `limit`. Caps at `hardCap` lines and
 * notes truncation.
 */
export function numberLines(
  content: string,
  opts: { offset?: number; limit?: number; hardCap?: number } = {},
): string {
  const hardCap = opts.hardCap ?? 2000
  const allLines = content.split("\n")
  const offset = Math.max(0, opts.offset ?? 0)
  const requested = opts.limit ?? allLines.length
  const limit = Math.min(requested, hardCap)

  const slice = allLines.slice(offset, offset + limit)
  const numbered = slice
    .map((line, i) => `${offset + i + 1}: ${line}`)
    .join("\n")

  const remaining = allLines.length - (offset + slice.length)
  if (remaining > 0) {
    return `${numbered}\n... ${remaining} more lines (use offset/limit to read further) ...`
  }
  return numbered
}
