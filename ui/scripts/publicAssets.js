import fs from 'node:fs'
import path from 'node:path'
import { performance } from 'node:perf_hooks'

function inside(parent, child) {
  const relative = path.relative(parent, child)
  return (
    relative !== '' &&
    !relative.startsWith(`..${path.sep}`) &&
    relative !== '..' &&
    !path.isAbsolute(relative)
  )
}

function checkOutput(root, publicDir, outDir) {
  if (
    !inside(root, publicDir) ||
    !inside(root, outDir) ||
    publicDir === outDir ||
    inside(publicDir, outDir) ||
    inside(outDir, publicDir)
  ) {
    throw new Error(
      'Public assets require separate source and output directories inside the project'
    )
  }
  if (path.relative(root, fs.realpathSync(root)) !== '') {
    throw new Error('Public asset output must not follow a directory link')
  }
  let current = root
  for (const segment of path.relative(root, outDir).split(path.sep)) {
    current = path.join(current, segment)
    if (fs.lstatSync(current, { throwIfNoEntry: false })?.isSymbolicLink()) {
      throw new Error('Public asset output must not follow a directory link')
    }
  }
}

export function preparePublicOutput({ root, publicDir, outDir }) {
  root = path.resolve(root)
  publicDir = path.resolve(publicDir)
  outDir = path.resolve(outDir)
  checkOutput(root, publicDir, outDir)
  const files = new Map()
  const directories = new Set([''])
  function readPublic(directory, relative = '') {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const name = path.join(relative, entry.name)
      const full = path.join(directory, entry.name)
      const source = entry.isSymbolicLink() ? fs.statSync(full) : entry
      if (source.isDirectory()) {
        directories.add(name)
        readPublic(full, name)
      } else if (source.isFile()) files.set(name, fs.readFileSync(full))
      else throw new Error('Public assets must contain regular files and directories')
    }
  }
  if (fs.existsSync(publicDir)) readPublic(publicDir)

  let copied = 0
  let unchanged = 0
  let removed = 0
  function clean(directory, relative = '') {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (relative === '' && entry.name === '.git') continue
      const name = path.join(relative, entry.name)
      const full = path.join(directory, entry.name)
      if (entry.isDirectory() && !entry.isSymbolicLink()) {
        clean(full, name)
        if (!directories.has(name)) fs.rmdirSync(full)
      } else if (entry.isSymbolicLink() || !files.has(name)) {
        fs.unlinkSync(full)
        removed += 1
      }
    }
  }
  if (fs.existsSync(outDir)) clean(outDir)
  for (const directory of directories)
    fs.mkdirSync(path.join(outDir, directory), { recursive: true })
  for (const [name, data] of files) {
    const target = path.join(outDir, name)
    if (fs.existsSync(target) && fs.readFileSync(target).equals(data)) unchanged += 1
    else {
      fs.writeFileSync(target, data)
      copied += 1
    }
  }
  return { copied, unchanged, removed }
}

export function incrementalPublicAssets() {
  let enabled = false
  return {
    name: 'mower:incremental-public-assets',
    apply: 'build',
    applyToEnvironment: (environment) => environment.name === 'client',
    config(config) {
      enabled = false
      const build = config.build ?? {}
      const output = build.rolldownOptions?.output ?? build.rollupOptions?.output
      if (
        config.publicDir !== undefined ||
        build.outDir !== undefined ||
        build.emptyOutDir !== undefined ||
        build.copyPublicDir === false ||
        build.write === false ||
        build.ssr ||
        config.resolve?.preserveSymlinks ||
        output
      )
        return
      enabled = true
      return { build: { emptyOutDir: false, copyPublicDir: false } }
    },
    renderStart: {
      order: 'pre',
      handler() {
        if (!enabled) return
        const { root, publicDir, build, logger } = this.environment.config
        const start = performance.now()
        const result = preparePublicOutput({
          root,
          publicDir,
          outDir: path.resolve(root, build.outDir)
        })
        logger.info(
          `Public assets: ${result.copied} copied, ${result.unchanged} unchanged, ${result.removed} removed (${Math.round(performance.now() - start)} ms)`
        )
      }
    }
  }
}
