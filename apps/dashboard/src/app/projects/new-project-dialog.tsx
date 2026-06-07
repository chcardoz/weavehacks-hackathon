"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Github, Loader2, Lock, Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface GithubRepo {
  owner: string
  name: string
  defaultBranch: string
  private: boolean
}

export function NewProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const [repos, setRepos] = useState<GithubRepo[] | null>(null)
  const [loadError, setLoadError] = useState<{
    message: string
    hint?: string
  } | null>(null)
  const [query, setQuery] = useState("")
  const [selected, setSelected] = useState<GithubRepo | null>(null)
  const [name, setName] = useState("")
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!open) return
    setRepos(null)
    setLoadError(null)
    setSelected(null)
    setName("")
    setQuery("")
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch("/api/github-repos", { cache: "no-store" })
        const json = await res.json()
        if (cancelled) return
        if (!res.ok) {
          setLoadError({
            message:
              json?.error === "github_not_connected"
                ? "GitHub is not connected"
                : "Could not load repositories",
            hint: json?.hint,
          })
          return
        }
        setRepos(json.repos as GithubRepo[])
      } catch {
        if (!cancelled) setLoadError({ message: "Network error" })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open])

  const filtered =
    repos?.filter((r) =>
      `${r.owner}/${r.name}`.toLowerCase().includes(query.toLowerCase()),
    ) ?? []

  async function onCreate() {
    if (!selected) return
    setCreating(true)
    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          repoOwner: selected.owner,
          repoName: selected.name,
          defaultBranch: selected.defaultBranch,
          name: name.trim() || undefined,
        }),
      })
      const json = await res.json().catch(() => null)
      if (!res.ok) {
        toast.error(json?.message ?? `Could not create project (${res.status})`)
        return
      }
      if (json?.webhookWarning) {
        toast.warning(json.webhookWarning)
      } else {
        toast.success("Project created")
      }
      onOpenChange(false)
      if (json?.project?.id) {
        router.push(`/projects/${json.project.id}`)
      } else {
        router.refresh()
      }
    } catch {
      toast.error("Network error")
    } finally {
      setCreating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader>
        <DialogTitle>New project</DialogTitle>
        <DialogDescription>
          Pick a GitHub repository to watch. We install a push webhook and mint a
          training key for it.
        </DialogDescription>
      </DialogHeader>

      {loadError ? (
        <div className="space-y-3 rounded-md border border-border bg-muted/30 p-4 text-sm">
          <div className="flex items-center gap-2 font-medium">
            <Github className="size-4" /> {loadError.message}
          </div>
          {loadError.hint && (
            <p className="text-muted-foreground">{loadError.hint}</p>
          )}
          <Button asChild size="sm" variant="outline">
            <a href="/sign-in">Connect GitHub</a>
          </Button>
        </div>
      ) : repos === null ? (
        <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading your repos…
        </div>
      ) : (
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search repositories"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-8"
            />
          </div>
          <div className="max-h-56 overflow-y-auto rounded-md border border-border">
            {filtered.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">
                No repositories match.
              </p>
            ) : (
              filtered.map((r) => {
                const key = `${r.owner}/${r.name}`
                const isSel =
                  selected?.owner === r.owner && selected?.name === r.name
                return (
                  <button
                    type="button"
                    key={key}
                    onClick={() => setSelected(r)}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-accent ${
                      isSel ? "bg-accent" : ""
                    }`}
                  >
                    <span className="truncate font-mono">{key}</span>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                      {r.private && <Lock className="size-3" />}
                      {r.defaultBranch}
                    </span>
                  </button>
                )
              })
            )}
          </div>
          {selected && (
            <div className="space-y-2">
              <Label htmlFor="project-name">Project name (optional)</Label>
              <Input
                id="project-name"
                placeholder={selected.name}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
          )}
        </div>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button onClick={onCreate} disabled={!selected || creating}>
          {creating ? "Creating…" : "Create project"}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
