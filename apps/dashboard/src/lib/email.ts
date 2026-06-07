import { Resend } from "resend"

// Incident-report email via Resend. Silently no-ops unless RESEND_API_KEY is set,
// so the pipeline never fails because email isn't configured.

const FROM = "keepalive <reports@keepalive.club>"

/** Public dashboard base URL for links in outbound emails/PRs. */
export function dashboardBaseUrl(): string {
  return (
    process.env.BETTER_AUTH_URL ??
    "https://weavehacks-hackathon-dashboard.vercel.app"
  )
}

export interface IncidentEmailResult {
  agentId: string
  state: string
  prUrl?: string
  error?: string
}

export interface SendIncidentReportParams {
  to: string | null | undefined
  project: { id: string; name: string }
  incident: {
    id: string
    kind: string | null
    step: number | null
    diagnosis: string | null
  }
  results: IncidentEmailResult[]
}

/**
 * Sends an incident-recap email summarizing the diagnosis and the PRs opened.
 * No-op (returns false) when RESEND_API_KEY is unset or `to` is missing.
 */
export async function sendIncidentReport(
  params: SendIncidentReportParams,
): Promise<boolean> {
  const apiKey = process.env.RESEND_API_KEY
  if (!apiKey || !params.to) return false

  const { project, incident, results } = params
  const opened = results.filter((r) => r.prUrl)
  const failed = results.filter((r) => !r.prUrl)

  const prList = opened
    .map((r) => `<li><a href="${r.prUrl}">${r.prUrl}</a></li>`)
    .join("")
  const failedList = failed
    .map(
      (r) =>
        `<li>${escapeHtml(r.agentId)} — ${escapeHtml(r.error ?? r.state)}</li>`,
    )
    .join("")

  const subject = `keepalive: ${incident.kind ?? "incident"} on ${project.name} — ${opened.length} fix PR${opened.length === 1 ? "" : "s"}`

  const html = `<div style="font-family:system-ui,sans-serif;line-height:1.5">
  <h2>keepalive incident report</h2>
  <p><strong>Project:</strong> ${escapeHtml(project.name)}</p>
  <p><strong>Failure:</strong> ${escapeHtml(incident.kind ?? "unknown")}${incident.step != null ? ` at step ${incident.step}` : ""}</p>
  <p><strong>Diagnosis:</strong> ${escapeHtml(incident.diagnosis ?? "(none)")}</p>
  ${opened.length ? `<p><strong>Fix PRs opened:</strong></p><ul>${prList}</ul>` : "<p>No fix PRs were opened.</p>"}
  ${failed.length ? `<p><strong>Agents that failed:</strong></p><ul>${failedList}</ul>` : ""}
  <p style="color:#666;font-size:13px">View the full incident in your <a href="${dashboardBaseUrl()}/projects/${project.id}">keepalive dashboard</a>.</p>
</div>`

  try {
    const resend = new Resend(apiKey)
    await resend.emails.send({ from: FROM, to: params.to, subject, html })
    return true
  } catch (err) {
    console.error("[email] sendIncidentReport failed:", err)
    return false
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}
