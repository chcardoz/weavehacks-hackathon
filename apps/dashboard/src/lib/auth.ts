import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { apiKey } from "better-auth/plugins";
import { db } from "@/lib/db";
import { schema } from "@/db/schema";

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "pg",
    schema,
  }),
  emailAndPassword: {
    enabled: true,
  },
  plugins: [
    apiKey({
      defaultPrefix: "ka_live_",
      enableMetadata: true,
    }),
  ],
});

export type Session = typeof auth.$Infer.Session;
export type User = Session["user"];
