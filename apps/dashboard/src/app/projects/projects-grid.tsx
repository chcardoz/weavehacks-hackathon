"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { ExternalLink, FolderGit2, Plus, TriangleAlert } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Sparkline } from "@/components/sparkline"
import {
  formatRelative,
  type ProjectListItem,
  projectActivityKind,
  projectStatusTone,
} from "@/lib/observability-types"
import { useNow } from "./use-now"
import { NewProjectDialog } from "./new-project-dialog"

function ActivityLine({ item }: { item: ProjectListItem }) {
  const kind = projectActivityKind(item)
  const run = item.latestRun
  switch (item.status) {
    case "idle":
      return <span className="text-muted-foreground">idle</span>
    case "training": {
      const step = run?.currentStep ?? 0
      const loss = run?.latestLoss != null ? run.latestLoss.toFixed(4) : "—"
      return (
        <div className="flex items-center gap-2">
          <span className="text-emerald-400">
            training · step {step} · loss {loss}
          </span>
          {run && run.lossHistory.length > 0 && (
            <Sparkline
              points={run.lossHistory}
              width={80}
              height={20}
              className="text-emerald-400"
            />
          )}
        </div>
      )
    }
    case "incident":
      return (
        <span className="flex items-center gap-1.5 text-red-400">
          <TriangleAlert className="size-3.5" /> {kind} detected
        </span>
      )
    case "fixing":
      return (
        <span className="text-primary">
          {item.fixingAgentCount} agent
          {item.fixingAgentCount === 1 ? "" : "s"} fixing
        </span>
      )
    case "recovered":
      return <span className="text-sky-400">recovered via fix</span>
    case "stopped":
      return <span className="text-muted-foreground">stopped</span>
    default:
      return <span className="text-muted-foreground">{item.status}</span>
  }
}

function ProjectCard({ item, now }: { item: ProjectListItem; now: number }) {
  const tone = projectStatusTone(item.status)
  const run = item.latestRun
  const repo = `${item.repoOwner}/${item.repoName}`
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
            {item.activeIncident && (
              <span className="ml-auto inline-flex size-2 shrink-0 animate-pulse rounded-full bg-red-500" />
            )}
          </div>
          <div className="truncate font-mono text-xs text-muted-foreground">
            {repo}
            {run?.wandbRunId ? ` · ${run.wandbRunId}` : ""}
          </div>
        </CardHeader>
        <CardContent className="pb-3 text-sm">
          <ActivityLine item={item} />
        </CardContent>
        <CardFooter className="justify-between text-xs text-muted-foreground">
          <span>last event {formatRelative(run?.lastEventAt ?? null, now)}</span>
          {run?.wandbUrl && (
            <Button
              asChild
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              onClick={(e) => e.stopPropagation()}
            >
              <a
                href={run.wandbUrl}
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

function OnboardingCard({ onNew }: { onNew: () => void }) {
  return (
    <div className="mx-auto flex max-w-xl flex-1 items-center justify-center py-12">
      <Card className="w-full">
        <CardHeader>
          <div className="flex items-center gap-2">
            <FolderGit2 className="size-5 text-muted-foreground" />
            <span className="font-medium">Create your first project</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Connect a GitHub repo, then wire keepalive into your training script.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button onClick={onNew}>
            <Plus /> New project
          </Button>
          <ol className="space-y-3 text-sm">
            <li className="space-y-1">
              <span className="text-muted-foreground">
                1. Install + log in locally
              </span>
              <pre className="overflow-x-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
                <code className="font-mono">{`pip install keepalive
keepalive login`}</code>
              </pre>
            </li>
            <li className="text-muted-foreground">
              2. Hand the agent blurb to your coding agent to wire keepalive +
              wandb in —{" "}
              <Link
                href="/docs/agent-blurb"
                className="text-primary hover:underline"
              >
                copy the blurb
              </Link>
              .
            </li>
            <li className="text-muted-foreground">
              3. Merge to your default branch and training launches in a W&B
              Sandbox.
            </li>
          </ol>
        </CardContent>
      </Card>
    </div>
  )
}

export function ProjectsGrid() {
  const [items, setItems] = useState<ProjectListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Repos keepalive is watching.
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus /> New project
        </Button>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {items.length === 0 ? (
        <OnboardingCard onNew={() => setDialogOpen(true)} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <ProjectCard key={item.id} item={item} now={now} />
          ))}
        </div>
      )}

      <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  )
}
