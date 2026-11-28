import { createRequire } from 'node:module'
import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import crypto from 'node:crypto'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(path.join(root, 'ui/package.json'))
const { build } = require('esbuild')
const output = path.join(root, 'arknights_mower/data/mood')
const catalogPath = path.join(root, 'arknights_mower/data/riic/operators.json')
const catalog = (await readFile(catalogPath, 'utf8')).replace(/\r\n/g, '\n')
const result = await build({
  absWorkingDir: root,
  entryPoints: ['ui/src/riic/runtimeMood.ts'],
  bundle: true,
  write: false,
  metafile: true,
  format: 'iife',
  target: 'es2020',
  legalComments: 'inline',
  charset: 'utf8',
  minify: true,
  plugins: [
    {
      name: 'bundled-operator-catalog',
      setup(build) {
        build.onLoad({ filter: /[/\\]riic[/\\]operators\.json$/ }, ({ path: input }) => {
          if (path.resolve(input) === catalogPath)
            return {
              contents: 'export default globalThis.__mowerOperatorCatalog',
              loader: 'js'
            }
        })
      }
    }
  ]
})
const files = {}
for (const name of Object.keys(result.metafile.inputs).sort()) {
  files[name] = crypto
    .createHash('sha256')
    .update((await readFile(path.join(root, name), 'utf8')).replace(/\r\n/g, '\n'))
    .digest('hex')
}
const code = result.outputFiles[0].text.replace(/\r\n/g, '\n').trimEnd() + '\n'
const license = (
  await readFile(path.join(root, 'ui/src/riic/vendor/THIRD_PARTY_MOWER_LICENSE'), 'utf8')
).replace(/\r\n/g, '\n')
const manifest =
  JSON.stringify(
    {
      runtime: 'quickjs-ng==0.17.0.2',
      sha256: crypto.createHash('sha256').update(code).digest('hex'),
      catalog_sha256: crypto.createHash('sha256').update(catalog).digest('hex'),
      rules_sha256: crypto.createHash('sha256').update(code).update(catalog).digest('hex'),
      files
    },
    null,
    2
  ) + '\n'
const artifacts = {
  'runtime.js': code,
  'source.json': manifest,
  THIRD_PARTY_MOWER_LICENSE: license
}
await mkdir(output, { recursive: true })
for (const [name, text] of Object.entries(artifacts)) {
  const destination = path.join(output, name)
  const existing = await readFile(destination).catch(() => null)
  if (process.argv.includes('--check')) {
    if (existing?.toString('utf8').replace(/\r\n/g, '\n') !== text)
      throw new Error(`Mood runtime is stale: ${name}; run node scripts/build_mood_runtime.mjs`)
  } else if (!existing?.equals(Buffer.from(text, 'utf8'))) await writeFile(destination, text)
}
console.log(`Verified mood runtime: ${Object.keys(files).length} shared sources`)
