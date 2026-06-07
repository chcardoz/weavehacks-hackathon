import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { auth } from "@/lib/auth"

// Passthrough auth gate. The user-level shell lives on the /projects list page
// (page.tsx) and the project-level shell lives in [id]/layout.tsx, so they do
// not nest into a double sidebar.
export default async function ProjectsLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    redirect("/sign-in")
  }
  return <>{children}</>
}
