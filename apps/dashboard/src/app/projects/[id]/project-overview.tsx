"use client"

import { useEffect, useRef, useState } from "react"
import { ExternalLink, GitBranch, GitCommitHorizontal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Sparkline } from "@/components/sparkline"
import { InjectControls } from "@/components/projects/inject-controls"
import { LogViewer } from "@/components/projects/log-viewer"
import {
  type AgentRow,
  type EventRow,
  type Incident,
  isIncidentResolved,
  type Project,
  type ProjectDetail,
  type Run,
} from "@/lib/observability-types"

const MAX_EVENTS = 1000

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-mono text-sm">{value}</div>
    </div>
  )
}

function LatestRunCard({ run }: { run: Run | null }) {
  if (!run) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <span className="text-sm font-medium">Latest run</span>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No runs yet. Merge to your default branch to launch training.
          </p>
        </CardContent>
      </Card>
    )
  }
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <span className="text-sm font-medium">Latest run</span>
        {run.wandbUrl && (
          <Button asChild variant="ghost" size="sm" className="h-7 px-2">
            <a href={run.wandbUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="size-3" /> W&B
            </a>
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Step" value={run.currentStep ?? "—"} />
          <Stat
            label="Loss"
            value={run.latestLoss != null ? run.latestLoss.toFixed(4) : "—"}
          />
          <Stat
            label="Source"
            value={<span className="capitalize">{run.source}</span>}
          />
          <Stat
            label="Status"
            value={<span className="capitalize">{run.status}</span>}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-muted-foreground">
          {run.branch && (
            <span className="flex items-center gap-1">
              <GitBranch className="size-3" /> {run.branch}
            </span>
          )}
          {run.commitSha && (
            <span className="flex items-center gap-1">
              <GitCommitHorizontal className="size-3" />{" "}
              {run.commitSha.slice(0, 8)}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function LossChart({ run }: { run: Run | null }) {
  const points = run?.lossHistory ?? []
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <span className="text-sm font-medium">Loss</span>
        <span className="font-mono text-xs text-muted-foreground">
          {points.length} pts
        </span>
      </CardHeader>
      <CardContent>
        {points.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            No loss data yet.
          </div>
        ) : (
          <Sparkline
            points={points}
            width={640}
            height={140}
            className="w-full text-emerald-400"
          />
        )}
      </CardContent>
    </Card>
  )
}

export function ProjectOverview({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null)
  const [latestRun, setLatestRun] = useState<Run | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [, setAgents] = useState<AgentRow[]>([])
  const [events, setEvents] = useState<EventRow[]>([])
  const [agentFilter, setAgentFilter] = useState<string | null>(null)

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
        if (!res.ok) return
        const data = (await res.json()) as ProjectDetail
        if (!mounted.current) return
        setProject(data.project)
        setLatestRun(data.latestRun)
        setIncidents(data.incidents)
        setAgents(data.agents)
        setEvents((prev) => {
          const merged = after > 0 ? [...prev, ...data.events] : data.events
          const trimmed =
            merged.length > MAX_EVENTS
              ? merged.slice(merged.length - MAX_EVENTS)
              : merged
          lastEventId.current = trimmed.reduce(
            (m, e) => (e.id > m ? e.id : m),
            lastEventId.current,
          )
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

  if (!project) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    )
  }

  const newestIncident = incidents[0] ?? null
  const incidentOpen =
    newestIncident !== null && !isIncidentResolved(newestIncident.status)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Overview</h1>
        <InjectControls projectId={project.id} disabled={incidentOpen} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <LatestRunCard run={latestRun} />
        <LossChart run={latestRun} />
      </div>

      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Live events
        </h2>
        <LogViewer
          events={events}
          agentFilter={agentFilter}
          onClearAgentFilter={() => setAgentFilter(null)}
        />
      </section>
    </div>
  )
}
