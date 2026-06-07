import { betterAuth } from "better-auth"
import { drizzleAdapter } from "better-auth/adapters/drizzle"
import { apiKey } from "@better-auth/api-key"
import { db } from "@/lib/db"
import { schema } from "@/db/schema"

export const auth = betterAuth({
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
  plugins: [
    apiKey({
      defaultPrefix: "ka_live_",
      enableMetadata: true,
    }),
  ],
})

export type Session = typeof auth.$Infer.Session
export type User = Session["user"]
