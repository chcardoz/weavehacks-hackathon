import type { NextConfig } from "next"
import { createMDX } from "fumadocs-mdx/next"
import { withWorkflow } from "workflow/next"

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // weave is a node-only package (fs/os/path/crypto/readline via cli-progress);
  // keep it out of the webpack bundle so it's required at runtime instead.
  serverExternalPackages: ["weave"],
}

const withMDX = createMDX()

// Compose: fumadocs MDX wraps the base config, Workflow DevKit wraps that so the
// "use workflow"/"use step" directives are transformed at build time.
export default withWorkflow(withMDX(nextConfig))
