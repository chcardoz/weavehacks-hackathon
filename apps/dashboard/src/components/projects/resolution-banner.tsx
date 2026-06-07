"use client"

import { CircleCheck, CircleSlash, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { type EventRow, type Incident } from "@/lib/observability-types"

// Pull a PR url out of any event data, if a probe/library reported one.
function findPrUrl(events: EventRow[]): string | null {
  for (const e of events) {
    const data = e.data
    if (data && typeof data === "object") {
      const rec = data as Record<string, unknown>
      const candidate =
        rec.pr_url ?? rec.prUrl ?? rec.pull_request_url ?? rec.pr
      if (typeof candidate === "string" && candidate.startsWith("http")) {
        return candidate
      }
    }
  }
  return null
}

export function ResolutionBanner({
  incident,
  events,
}: {
  incident: Incident
  events: EventRow[]
}) {
  if (incident.status === "resolved") {
    const prUrl = findPrUrl(events)
    return (
      <Card className="border-emerald-500/40 bg-emerald-500/5">
        <CardContent className="flex flex-wrap items-center gap-3 py-4">
          <CircleCheck className="size-5 text-emerald-400" />
          <span className="text-sm">
            Recovered —{" "}
            <span className="font-mono text-emerald-400">
              {incident.winnerAgentId ?? "winner"}
            </span>{" "}
            promoted
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            {prUrl && (
              <Button asChild variant="ghost" size="sm" className="h-7 px-2">
                <a href={prUrl} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-3" /> PR
                </a>
              </Button>
            )}
            {incident.weaveUrl && (
              <Button asChild variant="ghost" size="sm" className="h-7 px-2">
                <a href={incident.weaveUrl} target="_blank" rel="noreferrer">
                  <ExternalLink className="size-3" /> Weave trace
                </a>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (incident.status === "stopped") {
    return (
      <Card className="border-border bg-muted/30">
        <CardContent className="flex items-center gap-3 py-4">
          <CircleSlash className="size-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            Run stopped. No probe promoted.
          </span>
        </CardContent>
      </Card>
    )
  }

  return null
}
