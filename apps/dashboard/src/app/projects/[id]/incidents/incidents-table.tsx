"use client"

import { Fragment, useState } from "react"
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  GitPullRequest,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  type AgentRow,
  agentStateTone,
  type Incident,
  incidentStatusTone,
} from "@/lib/observability-types"
import { SimilarIncidentsCard } from "./similar-incidents-card"

function fmtDateTime(value: string | null): string {
  if (!value) return "—"
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function AgentRowItem({
  a,
  isWinner,
}: {
  a: AgentRow
  isWinner: boolean
}) {
  const tone = agentStateTone(a.state)
  return (
    <div
      className={`space-y-2 rounded-md border p-3 ${
        isWinner ? "border-primary/50 bg-primary/5" : "border-border"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-mono text-xs text-muted-foreground">
          {a.id}
          {isWinner && <span className="ml-1 text-primary">· winner</span>}
        </span>
        <Badge variant={tone.variant} className={tone.className}>
          {a.state}
        </Badge>
      </div>
      <p className="text-sm">{a.hypothesis}</p>
      {a.error && (
        <p className="font-mono text-xs text-red-400">{a.error}</p>
      )}
      <div className="flex items-center gap-2">
        {a.branch && (
          <span className="font-mono text-xs text-muted-foreground">
            {a.branch}
          </span>
        )}
        {a.prUrl && (
          <Button asChild variant="outline" size="sm" className="h-7 px-2">
            <a href={a.prUrl} target="_blank" rel="noreferrer">
              <GitPullRequest className="size-3" />
              {a.prNumber ? `PR #${a.prNumber}` : "PR"}
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}

function IncidentDetail({
  incident,
  agents,
}: {
  incident: Incident
  agents: AgentRow[]
}) {
  return (
    <div className="space-y-4 bg-muted/20 p-4">
      <SimilarIncidentsCard incidentId={incident.id} />
      {incident.reasoning && (
        <div className="space-y-1">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Monitor reasoning
          </div>
          <p className="text-sm text-muted-foreground">{incident.reasoning}</p>
        </div>
      )}
      {incident.diagnosis && (
        <div className="space-y-1">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Diagnosis
          </div>
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">
            {incident.diagnosis}
          </p>
        </div>
      )}
      {incident.weaveUrl && (
        <Button asChild variant="ghost" size="sm" className="h-7 px-2">
          <a href={incident.weaveUrl} target="_blank" rel="noreferrer">
            <ExternalLink className="size-3" /> Weave trace
          </a>
        </Button>
      )}
      <div className="space-y-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Agents ({agents.length})
        </div>
        {agents.length === 0 ? (
          <p className="text-sm text-muted-foreground">No agents yet.</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {agents.map((a) => (
              <AgentRowItem
                key={a.id}
                a={a}
                isWinner={incident.winnerAgentId === a.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function IncidentsTable({
  incidents,
  agents,
}: {
  incidents: Incident[]
  agents: AgentRow[]
}) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (incidents.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-muted/20 p-8 text-center">
        <p className="text-sm text-muted-foreground">
          No incidents yet. keepalive will list NaNs, divergence, stalls and
          monitor flags here.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead>Kind</TableHead>
            <TableHead>Step</TableHead>
            <TableHead>Confidence</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Resolved</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {incidents.map((inc) => {
            const tone = incidentStatusTone(inc.status)
            const open = expanded === inc.id
            const incAgents = agents.filter((a) => a.incidentId === inc.id)
            return (
              <Fragment key={inc.id}>
                <TableRow
                  className="cursor-pointer"
                  onClick={() => setExpanded(open ? null : inc.id)}
                >
                  <TableCell>
                    {open ? (
                      <ChevronDown className="size-4 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="size-4 text-muted-foreground" />
                    )}
                  </TableCell>
                  <TableCell className="font-mono">
                    {inc.kind ?? "—"}
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground">
                    {inc.step ?? "—"}
                  </TableCell>
                  <TableCell className="font-mono text-muted-foreground">
                    {inc.confidence != null
                      ? inc.confidence.toFixed(2)
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant={tone.variant} className={tone.className}>
                      {inc.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {fmtDateTime(inc.createdAt)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {fmtDateTime(inc.resolvedAt)}
                  </TableCell>
                </TableRow>
                {open && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={7} className="p-0">
                      <IncidentDetail incident={inc} agents={incAgents} />
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
