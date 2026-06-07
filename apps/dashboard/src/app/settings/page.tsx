import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { eq } from "drizzle-orm"
import { auth } from "@/lib/auth"
import { db } from "@/lib/db"
import { user } from "@/db/schema"
import { UserSettingsForm } from "./user-settings-form"

export default async function SettingsPage() {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) redirect("/sign-in")

  const [row] = await db
    .select({ wandbApiKey: user.wandbApiKey })
    .from(user)
    .where(eq(user.id, session.user.id))
    .limit(1)

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Account-level configuration.
        </p>
      </div>
      <UserSettingsForm
        email={session.user.email}
        hasWandbKey={!!row?.wandbApiKey}
      />
    </div>
  )
}
