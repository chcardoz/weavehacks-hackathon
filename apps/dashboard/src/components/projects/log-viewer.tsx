"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Pause, Play, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  type EventRow,
  type EventSource,
  eventLevelClass,
  eventSourceClass,
} from "@/lib/observability-types"

const ALL_SOURCES: EventSource[] = [
  "library",
  "server",
  "monitor",
  "hypothesis",
  "coder",
  "sandbox",
  "github",
]

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "--:--:--"
  return d.toLocaleTimeString(undefined, { hour12: false })
}

export function LogViewer({
  events,
  agentFilter,
  onClearAgentFilter,
}: {
  events: EventRow[]
  agentFilter: string | null
  onClearAgentFilter: () => void
}) {
  const [enabledSources, setEnabledSources] = useState<Set<EventSource>>(
    () => new Set(ALL_SOURCES),
  )
  const [paused, setPaused] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  function toggleSource(s: EventSource) {
    setEnabledSources((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
  }

  const filtered = useMemo(() => {
    return events.filter((e) => {
      if (!enabledSources.has(e.source)) return false
      if (agentFilter && e.agentId !== agentFilter) return false
      return true
    })
  }, [events, enabledSources, agentFilter])

  // Track whether the user is stuck to the bottom.
  function onScroll() {
    const el = scrollRef.current
    if (!el) return
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 24
    stickRef.current = atBottom
  }

  useEffect(() => {
    if (paused) return
    const el = scrollRef.current
    if (!el) return
    if (stickRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [filtered, paused])

  return (
    <Card>
      <CardHeader className="gap-2 pb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {ALL_SOURCES.map((s) => {
            const on = enabledSources.has(s)
            return (
              <button
                key={s}
                type="button"
                onClick={() => toggleSource(s)}
                className={`rounded-full px-2 py-0.5 text-xs font-medium transition-opacity ${eventSourceClass(
                  s,
                )} ${on ? "" : "opacity-30"}`}
              >
                {s}
              </button>
            )
          })}
          <div className="ml-auto flex items-center gap-1.5">
            {agentFilter && (
              <Badge
                variant="muted"
                className="cursor-pointer gap-1"
                onClick={onClearAgentFilter}
              >
                <span className="font-mono">{agentFilter}</span>
                <X className="size-3" />
              </Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              onClick={() => setPaused((v) => !v)}
            >
              {paused ? (
                <>
                  <Play className="size-3" /> Resume
                </>
              ) : (
                <>
                  <Pause className="size-3" /> Pause
                </>
              )}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="h-[420px] overflow-y-auto rounded-md border border-border bg-muted/20 p-2 font-mono text-xs"
        >
          {filtered.length === 0 ? (
            <p className="p-2 text-muted-foreground">No log lines.</p>
          ) : (
            filtered.map((e) => (
              <div
                key={e.id}
                className="flex items-start gap-2 px-1 py-0.5 leading-relaxed"
              >
                <span className="shrink-0 text-muted-foreground">
                  {fmtTime(e.createdAt)}
                </span>
                <span
                  className={`shrink-0 rounded px-1.5 ${eventSourceClass(
                    e.source,
                  )}`}
                >
                  {e.source}
                </span>
                <span className={`break-words ${eventLevelClass(e.level)}`}>
                  {e.message}
                </span>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )
}
