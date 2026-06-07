import { auth } from "@/lib/auth"

export interface ApiKeyIdentity {
  userId: string
  keyId: string
}

/** Pulls a `ka_live_` token out of an `Authorization: Bearer …` header. */
function extractBearer(request: Request): string | null {
  const header = request.headers.get("authorization")
  if (!header) return null
  const match = /^Bearer\s+(.+)$/i.exec(header.trim())
  const token = match?.[1]?.trim()
  return token && token.length > 0 ? token : null
}

/**
 * Authenticates a library request via the Better Auth api-key plugin.
 * Returns the verified key's owning user + key id, or null when the header is
 * missing/invalid. Never throws.
 */
export async function authenticateApiKey(
  request: Request,
): Promise<ApiKeyIdentity | null> {
  const key = extractBearer(request)
  if (!key) return null

  try {
    const result = await auth.api.verifyApiKey({ body: { key } })
    if (!result.valid || !result.key) return null
    return { userId: result.key.referenceId, keyId: result.key.id }
  } catch (err) {
    console.error("[api-auth] verifyApiKey failed:", err)
    return null
  }
}
