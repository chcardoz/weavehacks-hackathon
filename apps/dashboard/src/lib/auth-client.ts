import { createAuthClient } from "better-auth/react"
import { apiKeyClient } from "@better-auth/api-key/client"

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_APP_URL,
  plugins: [apiKeyClient()],
})

export const { signIn, signUp, signOut, useSession } = authClient
