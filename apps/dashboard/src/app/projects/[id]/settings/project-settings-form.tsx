"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Check, Copy, Eye, EyeOff, Trash2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export interface ProjectSettings {
  name: string
  trainCommand: string
  defaultBranch: string
  repoOwner: string
  repoName: string
  webhookId: number | null
  trainingApiKey: string | null
}

export function ProjectSettingsForm({
  projectId,
  initial,
}: {
  projectId: string
  initial: ProjectSettings
}) {
  const router = useRouter()
  const [name, setName] = useState(initial.name)
  const [trainCommand, setTrainCommand] = useState(initial.trainCommand)
  const [defaultBranch, setDefaultBranch] = useState(initial.defaultBranch)
  const [saving, setSaving] = useState(false)
  const [revealKey, setRevealKey] = useState(false)
  const [copied, setCopied] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function onSave() {
    setSaving(true)
    try {
      const res = await fetch(`/api/projects/${projectId}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, trainCommand, defaultBranch }),
      })
      if (!res.ok) {
        toast.error(`Could not save (${res.status})`)
        return
      }
      toast.success("Settings saved")
      router.refresh()
    } catch {
      toast.error("Network error")
    } finally {
      setSaving(false)
    }
  }

  async function onCopyKey() {
    if (!initial.trainingApiKey) return
    await navigator.clipboard.writeText(initial.trainingApiKey)
    setCopied(true)
    toast.success("Key copied")
    setTimeout(() => setCopied(false), 1500)
  }

  async function onDelete() {
    setDeleting(true)
    try {
      const res = await fetch(`/api/projects/${projectId}`, {
        method: "DELETE",
      })
      if (!res.ok) {
        toast.error(`Could not delete (${res.status})`)
        return
      }
      toast.success("Project deleted")
      router.push("/projects")
    } catch {
      toast.error("Network error")
    } finally {
      setDeleting(false)
    }
  }

  const maskedKey = initial.trainingApiKey
    ? revealKey
      ? initial.trainingApiKey
      : `${initial.trainingApiKey.slice(0, 8)}${"•".repeat(24)}`
    : null

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">General</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="train-command">Train command</Label>
            <Input
              id="train-command"
              className="font-mono"
              value={trainCommand}
              onChange={(e) => setTrainCommand(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="default-branch">Default branch</Label>
            <Input
              id="default-branch"
              className="font-mono"
              value={defaultBranch}
              onChange={(e) => setDefaultBranch(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Pushes to this branch launch training.
            </p>
          </div>
          <div className="space-y-2">
            <Label>Repository</Label>
            <Input
              readOnly
              className="font-mono text-muted-foreground"
              value={`${initial.repoOwner}/${initial.repoName}`}
            />
          </div>
          <div className="flex items-center gap-2">
            <Label className="m-0">Push webhook</Label>
            {initial.webhookId != null ? (
              <Badge
                variant="muted"
                className="bg-emerald-500/15 text-emerald-400"
              >
                installed
              </Badge>
            ) : (
              <Badge variant="muted" className="bg-amber-500/15 text-amber-400">
                not installed
              </Badge>
            )}
          </div>
          <div className="flex justify-end">
            <Button onClick={onSave} disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Training API key</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            The <code className="font-mono">ka_live_</code> key used by sandbox
            training runs for this project.
          </p>
          {maskedKey ? (
            <div className="flex items-center gap-2">
              <code className="flex-1 truncate rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-sm">
                {maskedKey}
              </code>
              <Button
                variant="outline"
                size="icon"
                aria-label={revealKey ? "Hide key" : "Reveal key"}
                onClick={() => setRevealKey((v) => !v)}
              >
                {revealKey ? <EyeOff /> : <Eye />}
              </Button>
              <Button
                variant="outline"
                size="icon"
                aria-label="Copy key"
                onClick={onCopyKey}
              >
                {copied ? <Check /> : <Copy />}
              </Button>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No key minted.</p>
          )}
        </CardContent>
      </Card>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-base text-destructive">
            Danger zone
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4">
          <p className="text-sm text-muted-foreground">
            Delete this project, its runs, incidents and the GitHub webhook.
            This cannot be undone.
          </p>
          <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
            <Trash2 /> Delete
          </Button>
        </CardContent>
      </Card>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogHeader>
          <DialogTitle>Delete {initial.name}?</DialogTitle>
          <DialogDescription>
            This permanently deletes the project and all of its data, and
            removes the GitHub push webhook.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onDelete}
            disabled={deleting}
          >
            {deleting ? "Deleting…" : "Delete project"}
          </Button>
        </DialogFooter>
      </Dialog>
    </div>
  )
}
