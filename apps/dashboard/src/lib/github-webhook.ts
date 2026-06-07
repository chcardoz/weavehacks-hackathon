import { createHmac, timingSafeEqual } from "node:crypto"

// Validates a GitHub webhook `x-hub-signature-256` header against the raw
// request body using the shared secret. The HMAC is computed over the EXACT
// bytes GitHub sent — callers must pass `await req.text()`, never a re-serialized
// JSON object.
//
// Returns true only on an exact, constant-time match.
export function verifyGithubSignature(
  raw: string,
  header: string | null | undefined,
  secret: string | undefined,
): boolean {
  if (!header || !secret) return false

  const expected =
    "sha256=" + createHmac("sha256", secret).update(raw, "utf8").digest("hex")

  // timingSafeEqual throws on length mismatch, so length-check first.
  if (header.length !== expected.length) return false

  const a = Buffer.from(header)
  const b = Buffer.from(expected)
  if (a.length !== b.length) return false

  return timingSafeEqual(a, b)
}
