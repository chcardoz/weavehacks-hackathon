import { ProjectOverview } from "./project-overview"

export default async function ProjectOverviewPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <ProjectOverview projectId={id} />
}
