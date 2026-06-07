"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { ArrowLeft, ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  type AgentRow,
  type EventRow,
  type Incident,
  isIncidentResolved,
  type Project,
  type ProjectDetail,
  projectStatusTone,
} from "@/lib/observability-types"
import { useNow } from "@/app/projects/use-now"
import { AgentCards } from "./agent-cards"
import { InjectControls } from "./inject-controls"
import { LifecycleLadder } from "./lifecycle-ladder"
import { LogViewer } from "./log-viewer"
import { ResolutionBanner } from "./resolution-banner"

const MAX_EVENTS = 1000

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h2>
  )
}

export function ProjectDetailView({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [agents, setAgents] = useState<AgentRow[]>([])
  const [events, setEvents] = useState<EventRow[]>([])
  const [notFound, setNotFound] = useState(false)
  const [agentFilter, setAgentFilter] = useState<string | null>(null)

  const now = useNow(1000)
  const lastEventId = useRef<number>(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    let controller: AbortController | null = null

    async function load() {
      if (document.hidden) return
      controller?.abort()
      controller = new AbortController()
      const after = lastEventId.current
      const url =
        after > 0
          ? `/api/projects/${projectId}?after=${after}`
          : `/api/projects/${projectId}`
      try {
        const res = await fetch(url, {
          signal: controller.signal,
          cache: "no-store",
        })
        if (res.status === 404) {
          if (mounted.current) setNotFound(true)
          return
        }
        if (!res.ok) return
        const data = (await res.json()) as ProjectDetail
        if (!mounted.current) return
        setProject(data.project)
        setIncidents(data.incidents)
        setAgents(data.agents)
        setEvents((prev) => {
          const merged =
            after > 0 ? [...prev, ...data.events] : data.events
          const trimmed =
            merged.length > MAX_EVENTS
              ? merged.slice(merged.length - MAX_EVENTS)
              : merged
          const maxId = trimmed.reduce(
            (m, e) => (e.id > m ? e.id : m),
            lastEventId.current,
          )
          lastEventId.current = maxId
          return trimmed
        })
      } catch (e) {
        if ((e as Error).name === "AbortError") return
      }
    }

    load()
    const interval = setInterval(load, 2000)
    return () => {
      mounted.current = false
      clearInterval(interval)
      controller?.abort()
    }
  }, [projectId])

  if (notFound) {
    return (
      <div className="space-y-4">
        <Link
          href="/projects"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> Projects
        </Link>
        <p className="text-sm text-muted-foreground">Project not found.</p>
      </div>
    )
  }

  if (!project) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    )
  }

  const newestIncident = incidents[0] ?? null
  const unresolved =
    newestIncident !== null && !isIncidentResolved(newestIncident.status)
  const tone = projectStatusTone(project.status)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-3">
        <Link
          href="/projects"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> Projects
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block size-2.5 rounded-full ${tone.dot}`}
              aria-hidden="true"
            />
            <h1 className="text-xl font-semibold">{project.name}</h1>
            <Badge variant="muted" className={tone.text}>
              {project.status}
            </Badge>
          </div>
          <InjectControls projectId={project.id} disabled={unresolved} />
        </div>
        <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-muted-foreground">
          <span>
            {project.repo ?? "no repo"}
            {project.commitSha ? ` @ ${project.commitSha.slice(0, 8)}` : ""}
          </span>
          {project.wandbUrl && (
            <Button asChild variant="ghost" size="sm" className="h-7 px-2">
              <a href={project.wandbUrl} target="_blank" rel="noreferrer">
                <ExternalLink className="size-3" /> W&B run
              </a>
            </Button>
          )}
          {newestIncident?.weaveUrl && (
            <Button asChild variant="ghost" size="sm" className="h-7 px-2">
              <a
                href={newestIncident.weaveUrl}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink className="size-3" /> Weave trace
              </a>
            </Button>
          )}
        </div>
      </div>

      {/* Zone 4: resolution banner (top, when resolved/stopped) */}
      {newestIncident && (
        <ResolutionBanner incident={newestIncident} events={events} />
      )}

      {/* Zone 1: lifecycle ladder */}
      {newestIncident ? (
        <section className="space-y-2">
          <SectionTitle>Latest incident · {newestIncident.kind}</SectionTitle>
          <LifecycleLadder incident={newestIncident} now={now} />
        </section>
      ) : (
        <section className="space-y-2">
          <SectionTitle>Status</SectionTitle>
          <p className="text-sm text-muted-foreground">
            No incidents. Training is healthy.
          </p>
        </section>
      )}

      {/* Zone 2: agent cards */}
      <section className="space-y-2">
        <SectionTitle>Probe agents</SectionTitle>
        <AgentCards
          agents={agents}
          repo={project.repo}
          onLogs={setAgentFilter}
        />
      </section>

      {/* Zone 3: unified log viewer */}
      <section className="space-y-2">
        <SectionTitle>Logs</SectionTitle>
        <LogViewer
          events={events}
          agentFilter={agentFilter}
          onClearAgentFilter={() => setAgentFilter(null)}
        />
      </section>
    </div>
  )
}
