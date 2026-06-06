import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";
import { KeysClient, type ApiKeyRow } from "./keys-client";

export default async function KeysPage() {
  const hdrs = await headers();
  const session = await auth.api.getSession({ headers: hdrs });
  if (!session) {
    redirect("/sign-in");
  }

  const keys = await auth.api.listApiKeys({ headers: hdrs });

  const rows: ApiKeyRow[] = keys.map((k) => ({
    id: k.id,
    name: k.name,
    start: k.start,
    enabled: k.enabled,
    createdAt:
      k.createdAt instanceof Date
        ? k.createdAt.toISOString()
        : (k.createdAt as unknown as string),
    lastRequest:
      k.lastRequest instanceof Date
        ? k.lastRequest.toISOString()
        : (k.lastRequest as unknown as string | null),
  }));

  return <KeysClient keys={rows} userEmail={session.user.email} />;
}
