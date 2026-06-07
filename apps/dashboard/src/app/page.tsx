import Link from "next/link"
import { redirect } from "next/navigation"
import { headers } from "next/headers"
import { Activity, ArrowRight, BookOpen } from "lucide-react"
import { auth } from "@/lib/auth"
import { buttonVariants } from "@/components/ui/button"

function GithubIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-4"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 .5C5.73.5.5 5.73.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.25.45-2.28 1.18-3.08-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.9 10.9 0 0 1 2.87-.39c.97 0 1.95.13 2.87.39 2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.76.11 3.05.73.8 1.18 1.83 1.18 3.08 0 4.41-2.69 5.38-5.25 5.67.41.36.78 1.06.78 2.14 0 1.55-.01 2.8-.01 3.18 0 .31.21.67.8.56A11.51 11.51 0 0 0 23.5 12C23.5 5.73 18.27.5 12 .5z" />
    </svg>
  )
}

export default async function Home() {
  const session = await auth.api.getSession({ headers: await headers() })
  if (session) {
    redirect("/projects")
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-10 px-6 py-16">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <div className="flex aspect-square size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Activity className="size-4" />
        </div>
        <span className="font-semibold text-foreground">
          keep<span className="text-primary">alive</span>
        </span>
      </div>

      <div className="space-y-5">
        <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
          Agents that hold your training run accountable — and act when you
          don&apos;t.
        </h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          keepalive watches your ML training, catches NaNs, divergence and
          stalls, then dispatches coding agents that open fix PRs while you
          sleep.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Link href="/sign-in" className={buttonVariants({ size: "lg" })}>
          <GithubIcon /> Sign in with GitHub <ArrowRight className="size-4" />
        </Link>
        <Link
          href="/docs"
          className={buttonVariants({ variant: "outline", size: "lg" })}
        >
          <BookOpen className="size-4" /> Read the docs
        </Link>
      </div>

      <div className="space-y-2">
        <p className="text-sm text-muted-foreground">Get started locally:</p>
        <pre className="overflow-x-auto rounded-lg border border-border bg-card p-4 text-sm">
          <code className="font-mono text-foreground">
            pip install keepalive-club
          </code>
        </pre>
      </div>
    </main>
  )
}
