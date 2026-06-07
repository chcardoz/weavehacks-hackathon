import { Octokit } from "octokit"
import { and, eq } from "drizzle-orm"
import { db } from "@/lib/db"
import { account } from "@/db/schema"

// Returns the GitHub OAuth access token for a user, or null if not linked.
// GitHub OAuth-app tokens don't expire, so there's no refresh logic.
export async function getGithubToken(userId: string): Promise<string | null> {
  const [row] = await db
    .select({ accessToken: account.accessToken })
    .from(account)
    .where(and(eq(account.providerId, "github"), eq(account.userId, userId)))
    .limit(1)

  return row?.accessToken ?? null
}

// Returns an Octokit client authed as the user's linked GitHub account.
// Throws if the user has not connected GitHub.
export async function getOctokit(userId: string): Promise<Octokit> {
  const token = await getGithubToken(userId)
  if (!token) {
    throw new Error(
      "No linked GitHub account for this user. Sign in with GitHub to connect.",
    )
  }
  return new Octokit({ auth: token })
}
