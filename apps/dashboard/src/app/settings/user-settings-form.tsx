"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function UserSettingsForm({
  email,
  hasWandbKey,
}: {
  email: string
  hasWandbKey: boolean
}) {
  const router = useRouter()
  const [wandbKey, setWandbKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [savedHasKey, setSavedHasKey] = useState(hasWandbKey)

  async function onSave() {
    setSaving(true)
    try {
      const res = await fetch("/api/user-settings", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ wandbApiKey: wandbKey }),
      })
      const json = await res.json().catch(() => null)
      if (!res.ok) {
        toast.error(`Could not save (${res.status})`)
        return
      }
      setSavedHasKey(!!json?.hasKey)
      setWandbKey("")
      toast.success("Saved")
      router.refresh()
    } catch {
      toast.error("Network error")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Label>Email</Label>
          <Input readOnly value={email} className="text-muted-foreground" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            W&B API key
            {savedHasKey && (
              <Badge
                variant="muted"
                className="bg-emerald-500/15 text-emerald-400"
              >
                set
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Needed to launch training in W&B Sandboxes on your behalf. Stored
            encrypted at rest and never shown again after saving.
          </p>
          <div className="space-y-2">
            <Label htmlFor="wandb-key">
              {savedHasKey ? "Replace key" : "API key"}
            </Label>
            <Input
              id="wandb-key"
              type="password"
              autoComplete="off"
              placeholder={savedHasKey ? "•••••••• (unchanged)" : "wandb api key"}
              value={wandbKey}
              onChange={(e) => setWandbKey(e.target.value)}
            />
          </div>
          <div className="flex justify-end">
            <Button onClick={onSave} disabled={saving || wandbKey.trim() === ""}>
              {saving ? "Saving…" : "Save key"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
