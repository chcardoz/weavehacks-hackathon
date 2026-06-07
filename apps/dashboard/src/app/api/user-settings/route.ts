import { headers } from "next/headers"
import { NextResponse, type NextRequest } from "next/server"
import { eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { user } from "@/db/schema"

export const dynamic = "force-dynamic"

export async function PATCH(req: NextRequest) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 })
  }

  const raw = (body as { wandbApiKey?: unknown } | null)?.wandbApiKey
  if (typeof raw !== "string") {
    return NextResponse.json(
      { error: "invalid_body", message: "wandbApiKey must be a string" },
      { status: 400 },
    )
  }

  const trimmed = raw.trim()
  const value = trimmed === "" ? null : trimmed

  await db
    .update(user)
    .set({ wandbApiKey: value, updatedAt: new Date() })
    .where(eq(user.id, session.user.id))

  return NextResponse.json({ ok: true, hasKey: value !== null })
}
