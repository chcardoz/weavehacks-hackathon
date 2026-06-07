import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"

const pnpmStore = join(process.cwd(), "node_modules", ".pnpm")
let changed = 0

if (existsSync(pnpmStore)) {
  for (const entry of readdirSync(pnpmStore)) {
    if (!entry.startsWith("@vercel+sandbox@")) continue

    const dist = join(
      pnpmStore,
      entry,
      "node_modules",
      "@vercel",
      "sandbox",
      "dist",
    )
    if (!existsSync(dist)) continue

    for (const file of readdirSync(dist)) {
      if (!file.endsWith(".js")) continue

      const path = join(dist, file)
      const before = readFileSync(path, "utf8")
      const after = before.replace(/\n?\/\/# sourceMappingURL=.*\.map\s*$/u, "\n")
      if (after === before) continue

      writeFileSync(path, after, "utf8")
      changed += 1
    }
  }
}

if (changed > 0) {
  console.log(`Patched @vercel/sandbox source map trailers in ${changed} files.`)
}
