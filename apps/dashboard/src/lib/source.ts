import { loader } from "fumadocs-core/source"
import { docs } from "@/.source"

// fumadocs-mdx 11.x returns `files` as a thunk at runtime while fumadocs-core
// 15.x types (and loader) expect an array — normalize so the two majors
// interoperate. The cast is safe: we resolve the thunk before handing it over.
const mdxSource = docs.toFumadocsSource()
const rawFiles = mdxSource.files as unknown
const files = typeof rawFiles === "function" ? rawFiles() : rawFiles

export const source = loader({
  baseUrl: "/docs",
  source: { files } as unknown as typeof mdxSource,
})
