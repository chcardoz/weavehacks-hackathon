import { createHmac } from "node:crypto"
import { describe, expect, it } from "vitest"

import { verifyGithubSignature } from "./github-webhook"

function sign(raw: string, secret: string): string {
  return "sha256=" + createHmac("sha256", secret).update(raw, "utf8").digest("hex")
}

describe("verifyGithubSignature", () => {
  const secret = "s3cr3t"
  const raw = JSON.stringify({ ref: "refs/heads/main", after: "abc123" })

  it("accepts a valid signature", () => {
    expect(verifyGithubSignature(raw, sign(raw, secret), secret)).toBe(true)
  })

  it("rejects a tampered body", () => {
    const sig = sign(raw, secret)
    expect(verifyGithubSignature(raw + "x", sig, secret)).toBe(false)
  })

  it("rejects a wrong secret", () => {
    expect(verifyGithubSignature(raw, sign(raw, "other"), secret)).toBe(false)
  })

  it("rejects a missing header", () => {
    expect(verifyGithubSignature(raw, null, secret)).toBe(false)
    expect(verifyGithubSignature(raw, undefined, secret)).toBe(false)
  })

  it("rejects a missing secret", () => {
    expect(verifyGithubSignature(raw, sign(raw, secret), undefined)).toBe(false)
  })

  it("rejects a length mismatch without throwing", () => {
    expect(verifyGithubSignature(raw, "sha256=deadbeef", secret)).toBe(false)
  })

  it("rejects a malformed header that is not the digest", () => {
    expect(verifyGithubSignature(raw, "not-a-signature", secret)).toBe(false)
  })
})
