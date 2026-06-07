import { headers } from "next/headers"
import { notFound, redirect } from "next/navigation"
import { auth } from "@/lib/auth"
import { getOwnedProject } from "@/lib/server/projects"
import { AgentConfigForm } from "./agent-config-form"

export default async function AgentsPage({
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
      <div>
        <h1 className="text-lg font-semibold">Agents</h1>
        <p className="text-sm text-muted-foreground">
          Tune how the monitoring and fixing agents watch and repair this
          project.
        </p>
      </div>
      <AgentConfigForm
        projectId={proj.id}
        initial={{
          monitoringPrompt: proj.monitoringPrompt,
          fixingPrompt: proj.fixingPrompt,
          confidenceThreshold: proj.confidenceThreshold,
          maxAgents: proj.maxAgents,
          monitorModel: proj.monitorModel,
        }}
      />
    </div>
  )
}
