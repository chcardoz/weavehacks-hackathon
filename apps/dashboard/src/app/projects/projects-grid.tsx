"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { ExternalLink, FolderGit2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Sparkline } from "@/components/sparkline"
import {
  formatCountdown,
  formatRelative,
  type ProjectListItem,
  projectActivityKind,
  projectStatusTone,
} from "@/lib/observability-types"
import { useNow } from "./use-now"

function ActivityLine({
  item,
  now,
}: {
  item: ProjectListItem
  now: number
}) {
  const kind = projectActivityKind(item)
  switch (item.status) {
    case "training": {
      const step = item.currentStep ?? 0
      const loss =
        item.latestLoss !== null ? item.latestLoss.toFixed(4) : "—"
      return (
        <div className="flex items-center gap-2">
          <span className="text-emerald-400">
            training · step {step} · loss {loss}
          </span>
          {item.lossHistory.length > 0 && (
            <Sparkline
              points={item.lossHistory}
              width={80}
              height={20}
              className="text-emerald-400"
            />
          )}
        </div>
      )
    }
    case "incident":
      return <span className="text-red-400">{kind} detected</span>
    case "awaiting_human": {
      const countdown = formatCountdown(
        item.activeIncident?.deadlineAt ?? null,
        now,
      )
      return (
        <span className="text-amber-400">
          {kind} · waiting on human · {countdown}
        </span>
      )
    }
    case "racing":
      return (
        <span className="text-primary">
          {item.racingAgentCount} agent
          {item.racingAgentCount === 1 ? "" : "s"} racing
        </span>
      )
    case "recovered":
      return <span className="text-sky-400">recovered via probe</span>
    case "stopped":
      return <span className="text-muted-foreground">stopped</span>
    default:
      return <span className="text-muted-foreground">{item.status}</span>
  }
}

function ProjectCard({ item, now }: { item: ProjectListItem; now: number }) {
  const tone = projectStatusTone(item.status)
  return (
    <Link href={`/projects/${item.id}`} className="block">
      <Card className="h-full transition-colors hover:border-primary/40">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <span
              className={`inline-block size-2.5 shrink-0 rounded-full ${tone.dot}`}
              aria-hidden="true"
            />
            <span className="truncate font-medium">{item.name}</span>
          </div>
          <div className="truncate font-mono text-xs text-muted-foreground">
            {item.repo ?? "no repo"}
            {item.wandbRunId ? ` · ${item.wandbRunId}` : ""}
          </div>
        </CardHeader>
        <CardContent className="pb-3 text-sm">
          <ActivityLine item={item} now={now} />
        </CardContent>
        <CardFooter className="justify-between text-xs text-muted-foreground">
          <span>last event {formatRelative(item.lastEventAt, now)}</span>
          {item.wandbUrl && (
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              onClick={(e) => e.stopPropagation()}
            >
              <a
                href={item.wandbUrl}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink className="size-3" /> W&B
              </a>
            </Button>
          )}
        </CardFooter>
      </Card>
    </Link>
  )
}

function EmptyState() {
  return (
    <div className="mx-auto flex max-w-xl flex-1 items-center justify-center py-16">
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FolderGit2 className="size-5 text-muted-foreground" />
            <span className="font-medium">No projects yet</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Start a watched training run and it will show up here live.
          </p>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-lg border border-border bg-muted/40 p-4 text-xs">
            <code className="font-mono text-foreground">{`import keepalive

with keepalive.watchdog(run, escalate=["telegram"],
                        timeout=120, checkpoint_dir="ckpt"):
    train(model)`}</code>
          </pre>
        </CardContent>
      </Card>
    </div>
  )
}

export function ProjectsGrid() {
  const [items, setItems] = useState<ProjectListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const now = useNow(1000)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    let controller: AbortController | null = null

    async function load() {
      if (document.hidden) return
      controller?.abort()
      controller = new AbortController()
      try {
        const res = await fetch("/api/projects", {
          signal: controller.signal,
          cache: "no-store",
        })
        if (!res.ok) {
          if (mounted.current) setError(`Failed to load (${res.status})`)
          return
        }
        const json = (await res.json()) as { projects: ProjectListItem[] }
        if (mounted.current) {
          setItems(json.projects)
          setError(null)
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") return
        if (mounted.current) setError("Network error")
      }
    }

    load()
    const interval = setInterval(load, 2000)
    return () => {
      mounted.current = false
      clearInterval(interval)
      controller?.abort()
    }
  }, [])

  if (items === null) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return <EmptyState />
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <ProjectCard key={item.id} item={item} now={now} />
        ))}
      </div>
    </div>
  )
}
