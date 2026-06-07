"use client"

import { useState } from "react"
import { ChevronDown, Zap } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { type CommandType } from "@/lib/observability-types"

const LABELS: Record<CommandType, string> = {
  inject_nan: "NaN",
  inject_divergence: "divergence",
  inject_stall: "Stall",
  inject_oom: "OOM",
}

export function InjectControls({
  projectId,
  disabled,
}: {
  projectId: string
  disabled: boolean
}) {
  const [busy, setBusy] = useState(false)

  async function inject(type: CommandType) {
    setBusy(true)
    toast.loading(`Injecting ${LABELS[type]}…`, { id: type })
    try {
      const res = await fetch(`/api/projects/${projectId}/inject`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ type }),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as {
          error?: string
        } | null
        toast.error(
          body?.error === "incident_in_progress"
            ? "Incident already in progress"
            : `Inject failed (${res.status})`,
          { id: type },
        )
        return
      }
      toast.success(`${LABELS[type]} queued`, { id: type })
    } catch {
      toast.error("Network error", { id: type })
    } finally {
      setBusy(false)
    }
  }

  const controls = (
    <div className="flex items-center gap-1.5">
      <Button
        variant="outline"
        size="sm"
        className="h-8 border-primary/40 text-primary hover:bg-primary/10"
        disabled={disabled || busy}
        onClick={() => inject("inject_oom")}
      >
        <Zap className="size-3" /> Inject OOM
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="h-8 border-primary/40 text-primary hover:bg-primary/10"
        disabled={disabled || busy}
        onClick={() => inject("inject_divergence")}
      >
        <Zap className="size-3" /> Inject divergence
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-8 border-primary/40 text-primary hover:bg-primary/10"
            disabled={disabled || busy}
          >
            More <ChevronDown className="size-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => inject("inject_nan")}>
            NaN
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => inject("inject_stall")}>
            Stall
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )

  if (!disabled) return controls

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-block">{controls}</span>
        </TooltipTrigger>
        <TooltipContent>incident in progress</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
