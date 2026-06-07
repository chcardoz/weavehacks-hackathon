import type { NextConfig } from "next"
import { createMDX } from "fumadocs-mdx/next"
import { withWorkflow } from "workflow/next"

const nextConfig: NextConfig = {
  reactStrictMode: true,
}

const withMDX = createMDX()

// Compose: fumadocs MDX wraps the base config, Workflow DevKit wraps that so the
// "use workflow"/"use step" directives are transformed at build time.
export default withWorkflow(withMDX(nextConfig))
