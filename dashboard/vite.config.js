import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import fs from "fs"
import path from "path"
import { fileURLToPath } from "url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const DOCS_DIR = path.resolve(__dirname, "../docs")

function titleFromFilename(filename) {
  return filename
    .replace(/\.md$/, "")
    .replace(/-concept-guide$/, "")
    .replace(/-/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase())
}

function categoryFromFilename(filename) {
  if (filename.startsWith("indicators") || filename.startsWith("backtest") || filename.startsWith("data") || filename.startsWith("execution")) return "Framework"
  if (filename.startsWith("strategies") || filename.startsWith("portfolio") || filename.startsWith("stat")) return "Strategies"
  if (filename.startsWith("risk")) return "Risk"
  if (filename.startsWith("market") || filename.startsWith("order") || filename.startsWith("vwap") || filename.startsWith("structure")) return "Foundation"
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
              .map(filename => ({
                filename,
                title: titleFromFilename(filename),
                category: categoryFromFilename(filename),
                content: fs.readFileSync(path.join(DOCS_DIR, filename), "utf-8"),
              }))
            res.setHeader("Content-Type", "application/json")
            res.end(JSON.stringify(files))
          } catch (e) {
            res.statusCode = 500
            res.end(JSON.stringify({ error: e.message }))
          }
        })
      },
    },
  ],
})
