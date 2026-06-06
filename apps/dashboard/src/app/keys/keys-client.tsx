"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Copy, KeyRound, LogOut, Plus, Trash2 } from "lucide-react"
import { authClient } from "@/lib/auth-client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export interface ApiKeyRow {
  id: string
  name: string | null
  start: string | null
  enabled: boolean | null
  createdAt: string
  lastRequest: string | null
}

function fmtDate(value: string | null): string {
  if (!value) return "—"
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function KeysClient({
  keys,
  userEmail,
}: {
  keys: ApiKeyRow[]
  userEmail: string
}) {
  const router = useRouter()
  const [createOpen, setCreateOpen] = useState(false)
  const [name, setName] = useState("")
  const [creating, setCreating] = useState(false)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [newKey, setNewKey] = useState<string | null>(null)

  async function onCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreating(true)
    const { data, error } = await authClient.apiKey.create({
      name: name.trim() || undefined,
      prefix: "ka_live_",
    })
    setCreating(false)
    if (error || !data) {
      toast.error(error?.message ?? "Could not create key")
      return
    }
    setCreateOpen(false)
    setName("")
    setNewKey(data.key)
    router.refresh()
  }

  async function onRevoke(keyId: string) {
    if (!window.confirm("Revoke this key? This cannot be undone.")) return
    setRevoking(keyId)
    const { error } = await authClient.apiKey.delete({ keyId })
    setRevoking(null)
    if (error) {
      toast.error(error.message ?? "Could not revoke key")
      return
    }
    toast.success("Key revoked")
    router.refresh()
  }

  async function copyKey() {
    if (!newKey) return
    await navigator.clipboard.writeText(newKey)
    toast.success("Copied to clipboard")
  }

  async function onSignOut() {
    await authClient.signOut()
    router.push("/sign-in")
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API keys</h1>
          <p className="text-sm text-muted-foreground">{userEmail}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onSignOut}>
          <LogOut /> Sign out
        </Button>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div className="space-y-1.5">
            <CardTitle>Your keys</CardTitle>
            <CardDescription>
              Use a <code className="font-mono">ka_live_</code> key as a Bearer
              token from the keepalive library.
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus /> Create key
          </Button>
        </CardHeader>
        <CardContent>
          {keys.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <KeyRound className="size-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                No keys yet. Create one to get started.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Last used</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell className="font-medium">
                      {k.name || "Untitled"}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {k.start ? `${k.start}…` : "ka_live_…"}
                    </TableCell>
                    <TableCell>
                      {k.enabled === false ? (
                        <Badge variant="muted">disabled</Badge>
                      ) : (
                        <Badge>active</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmtDate(k.createdAt)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {fmtDate(k.lastRequest)}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Revoke key"
                        disabled={revoking === k.id}
                        onClick={() => onRevoke(k.id)}
                      >
                        <Trash2 className="text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <form onSubmit={onCreate}>
          <DialogHeader>
            <DialogTitle>Create API key</DialogTitle>
            <DialogDescription>
              Give the key a name so you can recognize it later.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="key-name">Name</Label>
            <Input
              id="key-name"
              placeholder="training-box-1"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={creating}>
              {creating ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </Dialog>

      <Dialog
        open={newKey !== null}
        onOpenChange={(open) => {
          if (!open) setNewKey(null)
        }}
      >
        <DialogHeader>
          <DialogTitle>Copy your API key</DialogTitle>
          <DialogDescription className="text-accent">
            You won&apos;t be able to see this key again. Store it somewhere
            safe.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 p-3">
          <code className="flex-1 break-all font-mono text-sm">{newKey}</code>
          <Button
            size="icon"
            variant="outline"
            aria-label="Copy key"
            onClick={copyKey}
          >
            <Copy />
          </Button>
        </div>
        <DialogFooter>
          <Button onClick={() => setNewKey(null)}>Done</Button>
        </DialogFooter>
      </Dialog>
    </main>
  )
}
