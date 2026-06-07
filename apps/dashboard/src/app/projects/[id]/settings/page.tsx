import { headers } from "next/headers"
import { notFound, redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { getOwnedProject } from "@/lib/server/projects"
import { ProjectSettingsForm } from "./project-settings-form"

export default async function ProjectSettingsPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) redirect("/sign-in")

  const { id } = await params
  const proj = await getOwnedProject(id, session.user.id)
  if (!proj) notFound()

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <h1 className="text-lg font-semibold">Settings</h1>
      <ProjectSettingsForm
        projectId={proj.id}
        initial={{
          name: proj.name,
          trainCommand: proj.trainCommand,
          defaultBranch: proj.defaultBranch,
          repoOwner: proj.repoOwner,
          repoName: proj.repoName,
          webhookId: proj.webhookId,
          trainingApiKey: proj.trainingApiKey,
        }}
      />
    </div>
  )
}
