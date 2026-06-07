import { betterAuth } from "better-auth"
import { drizzleAdapter } from "better-auth/adapters/drizzle"
import { apiKey } from "@better-auth/api-key"
import { db } from "@/lib/db"
import { schema } from "@/db/schema"

function hostFromURL(value: string | undefined) {
  if (!value) return undefined
  try {
    return new URL(value.startsWith("http") ? value : `https://${value}`).host
  } catch {
    return undefined
  }
}

function originFromURL(value: string | undefined) {
  if (!value) return undefined
  try {
    return new URL(value.startsWith("http") ? value : `https://${value}`).origin
  } catch {
    return undefined
  }
}

function unique(values: Array<string | undefined>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))]
}

const fallbackAuthOrigin =
  originFromURL(process.env.BETTER_AUTH_URL) ??
  originFromURL(process.env.VERCEL_PROJECT_PRODUCTION_URL) ??
  originFromURL(process.env.VERCEL_URL) ??
  "http://localhost:3000"

const allowedAuthHosts = unique([
  "localhost:3000",
  "127.0.0.1:3000",
  "*.vercel.app",
  hostFromURL(process.env.BETTER_AUTH_URL),
  hostFromURL(process.env.VERCEL_PROJECT_PRODUCTION_URL),
  hostFromURL(process.env.VERCEL_URL),
])

export const auth = betterAuth({
  baseURL: {
    allowedHosts: allowedAuthHosts,
    fallback: fallbackAuthOrigin,
    protocol: "auto",
  },
  database: drizzleAdapter(db, {
    provider: "pg",
    schema,
  }),
  emailAndPassword: {
    enabled: true,
  },
  socialProviders: {
    github: {
      clientId: process.env.GITHUB_CLIENT_ID as string,
      clientSecret: process.env.GITHUB_CLIENT_SECRET as string,
      // `scope` (singular) APPENDS to the default ["read:user","user:email"].
      // `repo` covers contents/branches/PRs/webhook creation on admined repos.
      scope: ["repo"],
    },
  },
  account: {
    accountLinking: {
      enabled: true,
      trustedProviders: ["github"],
    },
  },
  advanced: {
    trustedProxyHeaders: true,
  },
  plugins: [
    apiKey({
      defaultPrefix: "ka_live_",
      enableMetadata: true,
    }),
  ],
})

export type Session = typeof auth.$Infer.Session
export type User = Session["user"]
