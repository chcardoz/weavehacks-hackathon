import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { UserShell } from "@/components/user-shell"
import { ProjectsGrid } from "./projects-grid"

export default async function ProjectsPage() {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    redirect("/sign-in")
  }
  return (
    <UserShell userEmail={session.user.email} title="Projects">
      <ProjectsGrid />
    </UserShell>
  )
}
