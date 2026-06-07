"use client"

import { useEffect, useState } from "react"
import { Brain, ExternalLink } from "lucide-react"
import type { MemoryHit } from "@/lib/memory/semantic"

interface SimilarResponse {
  available: boolean
  hits: MemoryHit[]
}

// Renders the resolution text, linkifying the first https URL it finds
// (resolutions often embed a PR link).
function Resolution({ text }: { text: string }) {
  const match = text.match(/https?:\/\/\S+/)
  if (!match) {
    return <p className="text-xs text-muted-foreground">{text}</p>
  }
  const url = match[0]
  const before = text.slice(0, match.index ?? 0)
  const after = text.slice((match.index ?? 0) + url.length)
  return (
    <p className="text-xs text-muted-foreground">
      {before}
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-0.5 text-primary hover:underline"
      >
        {url}
        <ExternalLink className="size-3" />
      </a>
      {after}
    </p>
  )
}

export function SimilarIncidentsCard({
  incidentId,
}: {
  incidentId: string
}) {
  const [data, setData] = useState<SimilarResponse | null>(null)

  useEffect(() => {
    let active = true
    fetch(`/api/incidents/${incidentId}/similar`)
      .then((res) => (res.ok ? (res.json() as Promise<SimilarResponse>) : null))
      .then((body) => {
        if (active && body) setData(body)
      })
      .catch(() => {
        // Feature is best-effort; stay invisible on failure.
      })
    return () => {
      active = false
    }
  }, [incidentId])

  // Invisible while loading, when Redis is unavailable, or when no hits.
  if (!data || !data.available || data.hits.length === 0) return null

  return (
    <div className="space-y-2 rounded-md border border-border bg-card p-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Brain className="size-3.5" />
        Similar past incidents (Redis memory)
      </div>
      <div className="space-y-2">
        {data.hits.map((hit) => (
          <div
            key={hit.id}
            className="space-y-1 rounded-md border border-border bg-muted/20 p-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm">{hit.summary}</span>
              <span className="shrink-0 font-mono text-xs text-primary">
                {Math.round(hit.similarity * 100)}% match
              </span>
            </div>
            {hit.resolution && <Resolution text={hit.resolution} />}
          </div>
        ))}
      </div>
    </div>
  )
}
