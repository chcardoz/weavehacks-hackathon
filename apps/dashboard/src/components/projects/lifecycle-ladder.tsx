"use client"

import { useState } from "react"
import { Check } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import {
  formatCountdown,
  humanReplyLabel,
  type Incident,
  type IncidentStatus,
} from "@/lib/observability-types"

// Stage index that maps the incident status to a position on the ladder.
const STAGES = [
  "Detected",
  "Diagnosed",
  "Escalated",
  "Human window",
  "Racing",
  "Resolved",
] as const

// Each incident status resolves to the index of the stage it has *reached*.
function statusStageIndex(status: IncidentStatus): number {
  switch (status) {
    case "detected":
      return 0
    case "diagnosing":
      return 1
    case "awaiting_human":
      return 3 // escalated + in human window
    case "racing":
      return 4
    case "resolved":
    case "stopped":
      return 5
    default:
      return 0
  }
}

export function LifecycleLadder({
  incident,
  now,
}: {
  incident: Incident
  now: number
}) {
  const [expanded, setExpanded] = useState(false)
  const reached = statusStageIndex(incident.status)
  const replyLabel = humanReplyLabel(incident.humanReply)
  const countdown = formatCountdown(incident.deadlineAt, now)
  const diagnosis = incident.diagnosis ?? ""

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-start justify-between gap-1 overflow-x-auto">
          {STAGES.map((stage, i) => {
            const isDone = i < reached || incident.status === "resolved"
            const isActive = i === reached && incident.status !== "resolved"
            const stageDoneOrActive = isDone || isActive
            return (
              <div
                key={stage}
                className="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center"
              >
                <div className="flex w-full items-center">
                  <span
                    className={`h-px flex-1 ${
                      i === 0 ? "opacity-0" : isDone ? "bg-primary" : "bg-border"
                    }`}
                  />
                  <span
                    className={`flex size-6 shrink-0 items-center justify-center rounded-full border ${
                      isDone
                        ? "border-primary bg-primary text-primary-foreground"
                        : isActive
                          ? "border-primary"
                          : "border-border"
                    }`}
                  >
                    {isDone ? (
                      <Check className="size-3.5" />
                    ) : isActive ? (
                      <span className="size-2 animate-pulse rounded-full bg-primary" />
                    ) : (
                      <span className="size-2 rounded-full bg-border" />
                    )}
                  </span>
                  <span
                    className={`h-px flex-1 ${
                      i === STAGES.length - 1
                        ? "opacity-0"
                        : i < reached
                          ? "bg-primary"
                          : "bg-border"
                    }`}
                  />
                </div>
                <span
                  className={`text-xs ${
                    stageDoneOrActive
                      ? "text-foreground"
                      : "text-muted-foreground"
                  }`}
                >
                  {stage}
                </span>
                {stage === "Escalated" && incident.deadlineAt && (
                  <span
                    className={`text-[10px] ${
                      countdown === "expired"
                        ? "text-muted-foreground"
                        : "text-amber-400"
                    }`}
                  >
                    {countdown === "expired" ? "expired" : countdown}
                  </span>
                )}
                {stage === "Human window" && (
                  <span className="text-[10px] text-muted-foreground">
                    {replyLabel ?? "no reply"}
                  </span>
                )}
              </div>
            )
          })}
        </div>

        {diagnosis && (
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p
              className={`whitespace-pre-wrap text-sm text-muted-foreground ${
                expanded ? "" : "line-clamp-4"
              }`}
            >
              {diagnosis}
            </p>
            {diagnosis.length > 200 && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="mt-1 text-xs text-primary hover:underline"
              >
                {expanded ? "Show less" : "Show more"}
              </button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
