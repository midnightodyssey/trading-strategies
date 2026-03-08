import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import fs from "fs"
import path from "path"
import { fileURLToPath } from "url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const DOCS_DIR = path.resolve(__dirname, "../docs")

// Read title from the first # heading in the doc, fall back to filename
function titleFromContent(content, filename) {
  const match = content.match(/^#\s+(.+?)(?:\s*—.*)?$/m)
  if (match) return match[1].trim()
  return filename
    .replace(/\.md$/, "")
    .replace(/-concept-guide$/, "")
    .replace(/-/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase())
}

// Read *Category: X* from doc metadata line — written by concept-explainer skill.
// Fall back to deriving from *Source: path* line, then from filename.
function categoryFromContent(content, filename) {
  // 1. Explicit *Category: X* metadata line (written by skill)
  const catMatch = content.match(/^\*Category:\s*(.+?)\*$/m)
  if (catMatch) return catMatch[1].trim()

  // 2. Derive from *Source: path* line
  const srcMatch = content.match(/^\*Source:\s*`?(.+?)`?\*$/m)
  if (srcMatch) {
    const src = srcMatch[1].toLowerCase()
    if (src.includes("strategies/"))    return "Strategies"
    if (src.includes("execution/"))     return "Execution"
    if (src.includes("broker/"))        return "Execution"
    if (src.includes("risk"))           return "Risk"
    if (src.includes("stat_edge"))      return "Analysis"
    if (src.includes("portfolio"))      return "Analysis"
    if (src.includes("backtest"))       return "Framework"
    if (src.includes("data"))           return "Framework"
    if (src.includes("indicators"))     return "Framework"
  }

  // 3. Filename fallback
  if (filename.startsWith("strategies") || filename.startsWith("portfolio") || filename.startsWith("stat")) return "Strategies"
  if (filename.startsWith("execution") || filename.startsWith("broker"))  return "Execution"
  if (filename.startsWith("risk"))        return "Risk"
  if (filename.startsWith("indicators") || filename.startsWith("backtest") || filename.startsWith("data")) return "Framework"
  return "Reference"
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: "docs-api",
      configureServer(server) {
        server.middlewares.use("/api/docs", (req, res) => {
          try {
            if (!fs.existsSync(DOCS_DIR)) {
              res.setHeader("Content-Type", "application/json")
              res.end(JSON.stringify([]))
              return
            }
            const files = fs.readdirSync(DOCS_DIR)
              .filter(f => f.endsWith(".md"))
              .sort()
              .map(filename => {
                const content = fs.readFileSync(path.join(DOCS_DIR, filename), "utf-8")
                return {
                  filename,
                  title:    titleFromContent(content, filename),
                  category: categoryFromContent(content, filename),
                  content,
                }
              })
            res.setHeader("Content-Type", "application/json")
            res.end(JSON.stringify(files))
          } catch (e) {
            res.statusCode = 500
            res.end(JSON.stringify({ error: e.message }))
          }
        })
      },
      generateBundle() {
        try {
          if (!fs.existsSync(DOCS_DIR)) {
            this.emitFile({
              type: "asset",
              fileName: "docs_index.json",
              source: JSON.stringify([], null, 2),
            })
            return
          }

          const docs = fs.readdirSync(DOCS_DIR)
            .filter(f => f.endsWith(".md"))
            .sort()
            .map(filename => {
              const content = fs.readFileSync(path.join(DOCS_DIR, filename), "utf-8")
              return {
                filename,
                title: titleFromContent(content, filename),
                category: categoryFromContent(content, filename),
                content,
              }
            })

          this.emitFile({
            type: "asset",
            fileName: "docs_index.json",
            source: JSON.stringify(docs, null, 2),
          })
        } catch (e) {
          this.warn(`[docs-api] Failed to generate docs_index.json: ${e.message}`)
        }
      },
    },
  ],
})
