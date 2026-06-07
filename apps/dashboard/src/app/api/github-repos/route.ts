import { headers } from "next/headers"
import { NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { getOctokit } from "@/lib/github"

export const dynamic = "force-dynamic"

export interface GithubRepo {
  owner: string
  name: string
  defaultBranch: string
  private: boolean
}

export async function GET() {
  const session = await auth.api.getSession({ headers: await headers() })
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 })
  }

  let octokit
  try {
    octokit = await getOctokit(session.user.id)
  } catch {
    return NextResponse.json(
      {
        error: "github_not_connected",
        hint: "Sign in with GitHub to connect your account, then try again.",
      },
      { status: 400 },
    )
  }

  try {
    const { data } = await octokit.rest.repos.listForAuthenticatedUser({
      per_page: 100,
      sort: "pushed",
      direction: "desc",
    })
    const repos: GithubRepo[] = data.map((r) => ({
      owner: r.owner.login,
      name: r.name,
      defaultBranch: r.default_branch ?? "main",
      private: r.private,
    }))
    return NextResponse.json({ repos })
  } catch (e) {
    return NextResponse.json(
      {
        error: "github_error",
        hint: "Could not list your GitHub repositories.",
        detail: (e as Error).message,
      },
      { status: 502 },
    )
  }
}
