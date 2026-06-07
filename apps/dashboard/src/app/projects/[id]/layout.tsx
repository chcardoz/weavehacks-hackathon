import { cookies, headers } from "next/headers"
import { notFound, redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { getOwnedProject } from "@/lib/server/projects"
import { ProjectSidebar } from "@/components/project-sidebar"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { projectStatusTone, type ProjectStatus } from "@/lib/observability-types"

export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>
}) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    redirect("/sign-in")
  }

  const { id } = await params
  const proj = await getOwnedProject(id, session.user.id)
  if (!proj) {
    notFound()
  }

  const cookieStore = await cookies()
  const defaultOpen = cookieStore.get("sidebar_state")?.value !== "false"
  const tone = projectStatusTone(proj.status as ProjectStatus)

  return (
    <SidebarProvider defaultOpen={defaultOpen}>
      <ProjectSidebar
        projectId={proj.id}
        projectName={proj.name}
        userEmail={session.user.email}
      />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
          <div className="flex w-full items-center gap-2 px-4">
            <SidebarTrigger className="-ml-1" />
            <Separator
              orientation="vertical"
              className="mr-2 data-[orientation=vertical]:h-4"
            />
            <div className="flex min-w-0 items-center gap-2">
              <span
                className={`inline-block size-2.5 shrink-0 rounded-full ${tone.dot}`}
                aria-hidden="true"
              />
              <span className="truncate font-semibold">{proj.name}</span>
              <span className="hidden truncate font-mono text-xs text-muted-foreground sm:inline">
                {proj.repoOwner}/{proj.repoName}
              </span>
            </div>
            <Badge variant="muted" className={`ml-auto ${tone.text}`}>
              {proj.status}
            </Badge>
          </div>
        </header>
        <div className="flex flex-1 flex-col gap-4 p-4 pt-0">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  )
}
