"use client"

import { ArrowRight } from "lucide-react"
import { Deck } from "@/components/ui/slide-cn/deck"
import { Slide } from "@/components/ui/slide-cn/slide"
import { SlideFooter } from "@/components/ui/slide-cn/slide-footer"
import { cn } from "@/lib/utils"

const footer = <SlideFooter showHint={false} />

const messyGpuCode = `if (torch.cuda.is_available()) {
  for (const gpu of cluster.devices) {
    switch (gpu.state) {
      case "ALLOCATED":
        if (loss.isnan() || loss === Infinity) pageHuman();
        if (vram.free < 0.08 && step > warmup) retryOOM();
        if (wandb.run.summary.grad_norm > threshold) alert();
        break;
      case "PREEMPTED":
        if (queue.depth > 19) checkpointMaybe();
        if (driver.version !== cuda.version) shrug();
        break;
      case "THERMAL_THROTTLE":
        fanCurve = fanCurve || process.env.DO_NOT_SLEEP;
        if (temp > 88 && utilization < 12) pageHuman();
        break;
      default:
        if (metrics.loss.slope > 0 && accuracy.flatline()) {
          switch (optimizer.name) {
            case "adamw": lowerLearningRate();
            case "sgd": maybeMomentum();
            default: pageHuman();
          }
        }
    }
  }
}

if (stderr.includes("CUDA out of memory")) pageHuman();
if (/illegal memory access|NCCL|SIGKILL/.test(logs)) pageHuman();
if (step % 500 === 0 && !wandbHeartbeat()) pageHuman();
if (gpu.util === 0 && dataloader.workers > 0) pageHuman();
if (loss.didNotMoveFor("14m")) pageHuman();
if (run.cost > budget && epoch < 1) pageHuman();`

export default function SlidesPage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-black text-white">
      <Deck showNavigationToast={false} className="bg-black text-white">
        <Slide key="title" footer={footer}>
          <SlideShell className="items-center justify-center text-center">
            <div className="space-y-8">
              <h1 className="text-6xl font-semibold leading-none tracking-tight md:text-8xl lg:text-9xl">
                keepalive
              </h1>
              <p className="text-2xl font-medium leading-tight text-neutral-300 md:text-4xl">
                an intelligent gpu watchdog
              </p>
            </div>
          </SlideShell>
        </Slide>

        <Slide key="problem" footer={footer}>
          <SlideShell className="items-center justify-center text-center">
            <div className="space-y-8">
              <div className="text-8xl font-semibold leading-none md:text-9xl">
                &quot;
              </div>
              <p className="max-w-5xl text-5xl font-semibold leading-tight tracking-tight md:text-7xl">
                dont rain on my model train
              </p>
              <div className="text-8xl font-semibold leading-none md:text-9xl">
                &quot;
              </div>
            </div>
          </SlideShell>
        </Slide>

        <Slide key="loop" footer={footer}>
          <SlideShell className="justify-center">
            <div className="grid flex-1 items-center gap-8 lg:grid-cols-3">
              <SlideThreePanel label="papers and ideas">
                <ResearchPaperIllustration />
              </SlideThreePanel>

              <SlideThreePanel label="ask jensen for compute">
                <img
                  src="/slides/jensen-huang.jpg"
                  alt="Jensen Huang"
                  className="h-full w-full rounded-lg border border-white object-cover grayscale"
                />
              </SlideThreePanel>

              <SlideThreePanel label="gpus failling during runs">
                <img
                  src="/slides/this-is-fine.gif"
                  alt="This is fine fire GIF"
                  className="h-full w-full rounded-lg border border-white object-cover"
                />
              </SlideThreePanel>
            </div>
          </SlideShell>
        </Slide>

        <Slide key="architecture" footer={footer}>
          <MonitoringSleepSlide />
        </Slide>

        <Slide key="demo" footer={footer}>
          <MonitoringSleepSlide
            crossShaq
            rightHeader={<MatrixAgentImage />}
          />
        </Slide>

        <Slide key="close" footer={footer}>
          <MonitoringSleepSlide
            crossCode
            crossShaq
            codeHeader={<MatrixAgentImage />}
            rightHeader={<MatrixAgentImage />}
          />
        </Slide>

        <Slide key="how-it-works" footer={footer}>
          <HowItWorksSlide />
        </Slide>

        <Slide key="dashboard-demo" footer={footer}>
          <DashboardDemoSlide />
        </Slide>

        <Slide key="sponsor-stack" footer={footer}>
          <SponsorStackSlide />
        </Slide>
      </Deck>
    </main>
  )
}

function SlideShell({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={cn(
        "mx-auto flex min-h-full w-full max-w-7xl flex-col gap-10 px-6 py-10 md:px-12 md:py-14 lg:px-16",
        className,
      )}
    >
      {children}
    </section>
  )
}

function SlideThreePanel({
  children,
  label,
}: {
  children: React.ReactNode
  label: string
}) {
  return (
    <div className="flex flex-col items-center gap-5">
      <div className="aspect-square w-full max-w-[18rem] overflow-hidden rounded-lg">
        {children}
      </div>
      <p className="text-center text-sm font-medium uppercase tracking-[0.18em] text-neutral-300">
        {label}
      </p>
    </div>
  )
}

function ResearchPaperIllustration() {
  return (
    <div className="flex h-full w-full items-center justify-center rounded-lg border border-white bg-black p-6">
      <div className="relative aspect-[3/4] w-full max-w-[10rem] rounded-md border border-white bg-black p-4">
        <div className="mb-5 h-5 w-3/4 rounded-sm border border-white" />
        <div className="space-y-3">
          <div className="h-2 w-full bg-white" />
          <div className="h-2 w-11/12 bg-white" />
          <div className="h-2 w-10/12 bg-white" />
          <div className="h-2 w-full bg-white" />
        </div>
        <div className="mt-8 grid grid-cols-2 gap-4">
          <div className="aspect-square rounded-sm border border-white" />
          <div className="space-y-3">
            <div className="h-2 w-full bg-white" />
            <div className="h-2 w-4/5 bg-white" />
            <div className="h-2 w-11/12 bg-white" />
          </div>
        </div>
        <div className="absolute -right-4 -top-4 flex size-10 items-center justify-center rounded-full border border-white bg-black text-xl font-semibold">
          ?
        </div>
      </div>
    </div>
  )
}

function MonitoringSleepSlide({
  crossCode = false,
  crossShaq = false,
  codeHeader,
  rightHeader,
}: {
  crossCode?: boolean
  crossShaq?: boolean
  codeHeader?: React.ReactNode
  rightHeader?: React.ReactNode
}) {
  return (
    <SlideShell className="justify-center">
      <div className="grid flex-1 items-center gap-8 lg:grid-cols-[1fr_auto_0.75fr]">
        <div className="flex flex-col items-center gap-5">
          {codeHeader}
          <div className="relative rounded-lg border border-white bg-black p-6">
            <pre className="max-h-[34rem] overflow-hidden text-left font-mono text-[0.62rem] leading-4 text-white md:text-xs md:leading-5">
              <code>{messyGpuCode}</code>
            </pre>
            {crossCode && <RedCross />}
          </div>
        </div>

        <ArrowRight className="mx-auto size-16 shrink-0 text-white" />

        <div className="flex flex-col items-center gap-5">
          {rightHeader}
          <div className="relative">
            <img
              src="/slides/shaq-sleeping.png"
              alt="A person sleeping"
              className="aspect-square w-full max-w-[20rem] rounded-lg border border-white object-cover"
            />
            {crossShaq && <RedCross />}
          </div>
          <p className="text-center text-sm font-medium uppercase tracking-[0.18em] text-neutral-300">
            human sleeping
          </p>
        </div>
      </div>
    </SlideShell>
  )
}

function MatrixAgentImage() {
  return (
    <img
      src="/slides/matrix-agent.png"
      alt="Matrix agent"
      className="aspect-video w-full max-w-[16rem] rounded-lg border border-white object-cover"
    />
  )
}

function HowItWorksSlide() {
  return (
    <SlideShell className="justify-center">
      <div className="grid flex-1 items-center gap-10 lg:grid-cols-[0.8fr_1fr]">
        <div className="space-y-8">
          <h2 className="max-w-3xl text-5xl font-semibold leading-none tracking-tight md:text-7xl">
            how keepalive works
          </h2>
          <div className="space-y-4 text-2xl font-medium text-neutral-300 md:text-3xl">
            <p>pip install</p>
            <p>wrap train()</p>
            <p>merge to main</p>
            <p>agents open prs</p>
          </div>
        </div>

        <div className="space-y-4">
          <TerminalBlock>{`pip install keepalive-club
keepalive login`}</TerminalBlock>
          <TerminalBlock>{`import keepalive, wandb

run = wandb.init(project="my-model")

with keepalive.watchdog(
    run,
    prompt="Flag divergence, NaNs, OOMs, stalls",
    threshold=0.6,
    max_agents=3,
):
    train()`}</TerminalBlock>
        </div>
      </div>
    </SlideShell>
  )
}

function DashboardDemoSlide() {
  const events = [
    ["library", "step=420 loss=0.391 gpu=91%"],
    ["monitor", "confidence dropped to 0.42"],
    ["hypothesis", "likely lr schedule or exploding grads"],
    ["coder", "agent-a opened branch fix/lr-warmup"],
    ["github", "PR #12 ready with report"],
  ]

  return (
    <SlideShell className="justify-center">
      <div className="rounded-lg border border-white bg-black p-5">
        <div className="mb-5 flex items-center justify-between border-b border-white pb-4">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-neutral-300">
              dashboard
            </p>
            <h2 className="mt-1 text-3xl font-semibold tracking-tight">
              Overview
            </h2>
          </div>
          <div className="rounded-full border border-white px-3 py-1 text-xs uppercase tracking-[0.18em] text-neutral-300">
            fixing
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
          <div className="space-y-4">
            <MockCard title="Latest run">
              <div className="grid grid-cols-2 gap-4 font-mono text-sm">
                <MockStat label="Step" value="420" />
                <MockStat label="Loss" value="0.3910" />
                <MockStat label="Source" value="sandbox" />
                <MockStat label="Status" value="running" />
              </div>
            </MockCard>

            <MockCard title="Loss">
              <svg viewBox="0 0 320 120" className="h-32 w-full text-white">
                <polyline
                  points="0,88 35,70 70,54 105,46 140,48 175,58 210,76 245,92 280,100 320,108"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="245" cy="92" r="5" className="animate-pulse fill-white" />
                <circle cx="280" cy="100" r="5" className="animate-pulse fill-white" />
                <circle cx="320" cy="108" r="5" className="animate-pulse fill-white" />
              </svg>
            </MockCard>

            <MockCard title="Live events">
              <div className="space-y-2 font-mono text-xs">
                {events.map(([source, message]) => (
                  <div key={message} className="flex gap-2">
                    <span className="w-20 shrink-0 rounded border border-white px-1.5 py-0.5 text-center">
                      {source}
                    </span>
                    <span className="text-neutral-300">{message}</span>
                  </div>
                ))}
              </div>
            </MockCard>
          </div>

          <div className="space-y-4">
            <MockCard title="Incident">
              <div className="grid grid-cols-4 gap-3 text-sm">
                <MockStat label="Kind" value="monitor_flag" />
                <MockStat label="Step" value="420" />
                <MockStat label="Confidence" value="0.42" />
                <MockStat label="Status" value="fixing" />
              </div>
              <p className="mt-4 text-sm leading-6 text-neutral-300">
                monitor reasoning: validation loss is rising while training loss
                keeps falling. dispatching hypothesis and coding agents.
              </p>
            </MockCard>

            <div className="grid gap-3 md:grid-cols-3">
              <AgentCard title="monitor" detail="scores metrics" active />
              <AgentCard title="hypothesis" detail="writes plan" active />
              <AgentCard title="coder x3" detail="opens prs" active />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <PrCard branch="fix/lr-warmup" pr="#12" />
              <PrCard branch="fix/grad-clip" pr="#13" />
            </div>
          </div>
        </div>
      </div>
    </SlideShell>
  )
}

function TerminalBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-hidden rounded-lg border border-white bg-black p-5 text-left font-mono text-sm leading-6 text-white md:text-base">
      <code>{children}</code>
    </pre>
  )
}

function MockCard({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-white bg-black p-4">
      <div className="mb-3 text-sm font-medium">{title}</div>
      {children}
    </div>
  )
}

function MockStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-neutral-400">{label}</div>
      <div className="font-mono text-sm text-white">{value}</div>
    </div>
  )
}

function AgentCard({
  title,
  detail,
  active = false,
}: {
  title: string
  detail: string
  active?: boolean
}) {
  return (
    <div className="rounded-lg border border-white bg-black p-4">
      <div className="mb-3 flex items-center gap-2">
        <span
          className={cn(
            "block size-2 rounded-full bg-white",
            active && "animate-pulse",
          )}
        />
        <span className="font-mono text-sm">{title}</span>
      </div>
      <p className="text-sm text-neutral-300">{detail}</p>
    </div>
  )
}

function PrCard({ branch, pr }: { branch: string; pr: string }) {
  return (
    <div className="rounded-lg border border-white bg-black p-4">
      <div className="font-mono text-sm text-neutral-300">{branch}</div>
      <div className="mt-3 text-3xl font-semibold tracking-tight">{pr}</div>
      <div className="mt-1 text-sm text-neutral-300">full report attached</div>
    </div>
  )
}

function SponsorStackSlide() {
  const rows = [
    {
      part: "training launch",
      tech: "Vercel Workflows + Vercel Sandbox -> W&B Sandbox",
      job: "GitHub merge starts a workflow; Vercel runs the Python launcher; W&B Sandbox runs training.",
    },
    {
      part: "monitoring agent",
      tech: "W&B Inference + AI SDK",
      job: "Phi-4-mini scores live metrics against the user's plain-English prompt.",
    },
    {
      part: "traceability",
      tech: "W&B Weave",
      job: "AI SDK telemetry exports every monitor, hypothesis, and coder decision as traces.",
    },
    {
      part: "hypothesis agent",
      tech: "OpenAI GPT-5.4 via Vercel AI Gateway",
      job: "Reads metrics, errors, and memory; produces diagnosis plus distinct fix hypotheses.",
    },
    {
      part: "coding agents",
      tech: "Vercel Sandbox + OpenAI GPT-5.4 + Octokit",
      job: "Each agent edits in an isolated repo checkout, pushes a branch, and opens a PR report.",
    },
    {
      part: "agent memory",
      tech: "Redis vector search",
      job: "Stores incident summaries as embeddings for semantic recall before proposing fixes.",
    },
    {
      part: "monitor cache",
      tech: "Redis LangCache",
      job: "Semantically caches monitor verdicts so repeated metric windows stay cheap.",
    },
    {
      part: "auth + repo access",
      tech: "Better Auth + GitHub OAuth",
      job: "Email/GitHub sign-in, ka_live API keys, repo scope, webhooks, and PR permissions.",
    },
  ]

  return (
    <SlideShell className="justify-center">
      <div className="space-y-8">
        <div className="space-y-3">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-neutral-300">
            what the judges should know
          </p>
          <h2 className="text-5xl font-semibold leading-none tracking-tight md:text-7xl">
            sponsor stack by job
          </h2>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <div
              key={row.part}
              className="grid gap-3 rounded-lg border border-white bg-black p-4 md:grid-cols-[0.52fr_1fr]"
            >
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-neutral-400">
                  {row.part}
                </p>
                <p className="mt-2 text-xl font-semibold leading-tight">
                  {row.tech}
                </p>
              </div>
              <p className="text-sm leading-6 text-neutral-300">{row.job}</p>
            </div>
          ))}
        </div>
      </div>
    </SlideShell>
  )
}

function RedCross() {
  return (
    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
      <div className="absolute h-1.5 w-[115%] rotate-45 bg-red-600" />
      <div className="absolute h-1.5 w-[115%] -rotate-45 bg-red-600" />
    </div>
  )
}
