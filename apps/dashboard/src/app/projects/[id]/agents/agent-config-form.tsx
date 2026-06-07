"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Textarea } from "@/components/ui/textarea"

const MONITOR_PROMPT_PLACEHOLDER =
  "Flag if val/loss diverges from train/loss, the loss goes NaN/Inf, grad_norm spikes, or training stalls (no loss improvement over many steps)."
const FIXING_PROMPT_PLACEHOLDER =
  "Prefer minimal, well-justified changes. Consider lowering the learning rate, adding gradient clipping, fixing data normalization, or guarding against NaNs."

const MODELS = [
  {
    value: "wandb/microsoft/Phi-4-mini-instruct",
    label: "Phi-4-mini · W&B Inference (fast/cheap)",
  },
  { value: "openai/gpt-5.4-mini", label: "GPT-5.4 mini · Gateway" },
  { value: "openai/gpt-5.4", label: "GPT-5.4 · Gateway" },
]

export interface AgentConfig {
  monitoringPrompt: string | null
  fixingPrompt: string | null
  confidenceThreshold: number
  maxAgents: number
  monitorModel: string
}

export function AgentConfigForm({
  projectId,
  initial,
}: {
  projectId: string
  initial: AgentConfig
}) {
  const router = useRouter()
  const [monitoringPrompt, setMonitoringPrompt] = useState(
    initial.monitoringPrompt ?? "",
  )
  const [fixingPrompt, setFixingPrompt] = useState(initial.fixingPrompt ?? "")
  const [threshold, setThreshold] = useState(initial.confidenceThreshold)
  const [maxAgents, setMaxAgents] = useState(initial.maxAgents)
  const [monitorModel, setMonitorModel] = useState(initial.monitorModel)
  const [saving, setSaving] = useState(false)

  async function onSave() {
    setSaving(true)
    try {
      const res = await fetch(`/api/projects/${projectId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          monitoringPrompt,
          fixingPrompt,
          confidenceThreshold: threshold,
          maxAgents,
          monitorModel,
        }),
      })
      if (!res.ok) {
        toast.error(`Could not save (${res.status})`)
        return
      }
      toast.success("Agent settings saved")
      router.refresh()
    } catch {
      toast.error("Network error")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardContent className="space-y-6 pt-6">
        <div className="space-y-2">
          <Label htmlFor="monitoring-prompt">Monitoring prompt</Label>
          <p className="text-xs text-muted-foreground">
            Plain-English criteria the monitoring agent scores each metrics
            window against.
          </p>
          <Textarea
            id="monitoring-prompt"
            rows={4}
            placeholder={MONITOR_PROMPT_PLACEHOLDER}
            value={monitoringPrompt}
            onChange={(e) => setMonitoringPrompt(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="fixing-prompt">Fixing prompt</Label>
          <p className="text-xs text-muted-foreground">
            Guidance for the hypothesis agent when it proposes fixes.
          </p>
          <Textarea
            id="fixing-prompt"
            rows={4}
            placeholder={FIXING_PROMPT_PLACEHOLDER}
            value={fixingPrompt}
            onChange={(e) => setFixingPrompt(e.target.value)}
          />
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Confidence threshold</Label>
            <span className="font-mono text-sm text-muted-foreground">
              {threshold.toFixed(2)}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            An incident opens when the monitor&apos;s confidence drops below
            this.
          </p>
          <Slider
            min={0}
            max={1}
            step={0.01}
            value={[threshold]}
            onValueChange={(v) => setThreshold(v[0] ?? 0)}
          />
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Max agents</Label>
            <span className="font-mono text-sm text-muted-foreground">
              {maxAgents}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            How many fix-writing agents fan out per incident.
          </p>
          <Slider
            min={1}
            max={5}
            step={1}
            value={[maxAgents]}
            onValueChange={(v) => setMaxAgents(v[0] ?? 1)}
          />
        </div>

        <div className="space-y-2">
          <Label>Monitor model</Label>
          <Select value={monitorModel} onValueChange={setMonitorModel}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODELS.map((m) => (
                <SelectItem key={m.value} value={m.value}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex justify-end">
          <Button onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
