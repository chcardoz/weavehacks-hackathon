import Link from "next/link";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { buttonVariants } from "@/components/ui/button";

export default async function Home() {
  const session = await auth.api.getSession({ headers: await headers() });
  const target = session ? "/keys" : "/sign-in";

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <div className="space-y-3">
        <h1 className="text-4xl font-semibold tracking-tight">
          keep<span className="text-accent">alive</span>
        </h1>
        <p className="text-lg text-muted-foreground">
          agents that hold you accountable — and stop waiting when you
          don&apos;t show up.
        </p>
      </div>

      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">
          A watchdog for your GPU training runs.
        </p>
        <pre className="overflow-x-auto rounded-lg border border-border bg-card p-4 text-sm">
          <code className="font-mono text-foreground">pip install keepalive</code>
        </pre>
      </div>

      <div>
        <Link href={target} className={buttonVariants()}>
          Get API key →
        </Link>
      </div>
    </main>
  );
}
