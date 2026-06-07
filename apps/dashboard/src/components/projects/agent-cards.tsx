"use client"

import { GitBranch, ScrollText, Trophy } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Sparkline } from "@/components/sparkline"
import { agentStateTone, type AgentRow } from "@/lib/observability-types"

function AgentCard({
  agent,
  repo,
  onLogs,
}: {
  agent: AgentRow
  repo: string | null
  onLogs: (id: string) => void
}) {
  const tone = agentStateTone(agent.state)
  const isWinner = agent.state === "winner"
  const branchUrl =
    repo && agent.branch
      ? `https://github.com/${repo}/tree/${agent.branch}`
      : null

  return (
    <Card className={isWinner ? "border-primary/50" : ""}>
      <CardHeader className="flex-row items-center justify-between gap-2 space-y-0 pb-2">
        <span className="truncate font-mono text-xs text-muted-foreground">
          {agent.id}
        </span>
        <Badge variant={tone.variant} className={tone.className}>
          {isWinner && <Trophy className="mr-1 size-3" />}
          {agent.state}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-2.5 text-sm">
        {agent.hypothesis && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="line-clamp-2 cursor-default text-muted-foreground">
                  {agent.hypothesis}
                </p>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                {agent.hypothesis}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}

        {agent.branch && (
          <div className="flex items-center gap-1.5 font-mono text-xs">
            <GitBranch className="size-3 shrink-0 text-muted-foreground" />
            {branchUrl ? (
              <a
                href={branchUrl}
                target="_blank"
                rel="noreferrer"
                className="truncate text-sky-400 hover:underline"
              >
                {agent.branch}
              </a>
            ) : (
              <span className="truncate text-muted-foreground">
                {agent.branch}
              </span>
            )}
          </div>
        )}

        {agent.error && (
          <p className="line-clamp-2 font-mono text-xs text-red-400">
            {agent.error}
          </p>
        )}

        <div className="flex items-center justify-between">
          <Sparkline
            points={agent.lossHistory}
            width={100}
            height={26}
            className={isWinner ? "text-primary" : "text-muted-foreground"}
          />
          <span className="font-mono text-xs text-muted-foreground">
            {agent.finalLoss !== null
              ? `loss ${agent.finalLoss.toFixed(4)}`
              : "—"}
          </span>
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onLogs(agent.id)}
        >
          <ScrollText className="size-3" /> Logs
        </Button>
      </CardContent>
    </Card>
  )
}

export function AgentCards({
  agents,
  repo,
  onLogs,
}: {
  agents: AgentRow[]
  repo: string | null
  onLogs: (id: string) => void
}) {
  if (agents.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No probe agents yet.</p>
    )
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {agents.map((a) => (
        <AgentCard key={a.id} agent={a} repo={repo} onLogs={onLogs} />
      ))}
    </div>
  )
}
