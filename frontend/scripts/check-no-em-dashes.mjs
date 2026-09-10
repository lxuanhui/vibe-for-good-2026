import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'

const roots = process.argv.slice(2)
const sourceRoots = roots.length > 0 ? roots : ['src']
const extensions = new Set(['.ts', '.tsx'])
const failures = []

async function scan(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) {
      await scan(path)
      continue
    }
    if (!extensions.has(entry.name.slice(entry.name.lastIndexOf('.')))) continue

    const content = await readFile(path, 'utf8')
    const lines = content.split('\n')
    lines.forEach((line, index) => {
      if (line.includes('\u2014')) failures.push(`${path}:${index + 1}`)
    })
  }
}

for (const root of sourceRoots) await scan(root)

if (failures.length > 0) {
  console.error(`Em-dash (U+2014) found in frontend source:\n${failures.join('\n')}`)
  process.exitCode = 1
}
