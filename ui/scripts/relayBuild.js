import { Buffer } from 'node:buffer'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

// Hash the source inputs across Windows and POSIX checkouts. Packaged instances
// read this identifier even when their installation has no Git metadata.
export function relayBuildId(root) {
  const digest = createHash('sha256')
  function add(relative, entry) {
    const filename = path.join(root, relative)
    const type = entry && !entry.isSymbolicLink() ? entry : fs.statSync(filename)
    if (type.isDirectory()) {
      const children = fs.readdirSync(filename, { withFileTypes: true })
      children.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
      for (const child of children) add(relative + '/' + child.name, child)
      return
    }
    if (/\.test\.[cm]?[jt]s$/.test(relative)) return
    let bytes = fs.readFileSync(filename)
    if (/\.(js|mjs|jsx|ts|tsx|vue|css|html|json|md|svg|txt)$/.test(relative)) {
      bytes = Buffer.from(bytes.toString('utf8').replaceAll('\r\n', '\n'))
    }
    digest.update(relative + '\0').update(createHash('sha256').update(bytes).digest())
  }
  for (const name of [
    'ui/src',
    'ui/scripts',
    'ui/manager',
    'ui/public',
    'ui/index.html',
    'ui/copy.js',
    'ui/package-lock.json',
    'ui/vite.config.js',
    'ui/Mower入门指北.html',
    'arknights_mower/data/riic',
    'arknights_mower/data/building_skill.json',
    'arknights_mower/data/recycling_model.json',
    'CHANGELOG.md'
  ])
    add(name)
  return digest.digest('hex')
}

export function relayBuildMetadata(root) {
  let build
  return {
    name: 'mower-relay-build',
    apply: 'build',
    buildStart() {
      build = relayBuildId(root)
      this.emitFile({ type: 'asset', fileName: 'relay-ui.json', source: JSON.stringify({ build }) })
    },
    transformIndexHtml() {
      return [{ tag: 'meta', attrs: { name: 'mower-relay-build', content: build } }]
    }
  }
}
