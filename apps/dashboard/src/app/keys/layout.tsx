import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { UserShell } from "@/components/user-shell"

export default async function KeysLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    redirect("/sign-in")
  }
  return (
    <UserShell userEmail={session.user.email} title="API keys">
      {children}
    </UserShell>
  )
}
