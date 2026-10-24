import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'
import { afterEach, expect, it, vi } from 'vitest'
import { build, createLogger } from 'vite'
import { incrementalPublicAssets, preparePublicOutput } from '../scripts/publicAssets.js'

const copyScript = fileURLToPath(new URL('../copy.js', import.meta.url))
const temporary = []
afterEach(() => {
  for (const directory of temporary.splice(0))
    fs.rmSync(directory, { recursive: true, force: true })
})

function fixture() {
  const directory = fs.mkdtempSync(
    path.join(fs.realpathSync(os.tmpdir()), 'mower-public-copy-test-')
  )
  temporary.push(directory)
  const root = path.join(directory, 'project')
  const publicDir = path.join(root, 'public')
  const outDir = path.join(root, 'dist')
  fs.mkdirSync(publicDir, { recursive: true })
  function write(name, data) {
    const target = path.join(root, name)
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(target, data)
  }
  write('index.html', '<script type="module" src="/entry.js"></script>')
  write(
    'entry.js',
    'console.log("first"); new Worker(new URL("./worker.js", import.meta.url), { type: "module" })'
  )
  write('worker.js', 'self.onmessage = () => self.postMessage("ready")')
  write('public/avatar/unchanged.webp', 'image bytes')
  write('public/settings.json', '{"state":1}')
  write('public/removed.svg', '<svg/>')
  write('Mower入门指北.html', '<p>guide one</p>')
  write('src/pages/basement_skill/buffer.json', '{"buffer":1}')
  return { directory, root, publicDir, outDir, write }
}

async function runBuild(root, options = {}) {
  const logger = createLogger('silent')
  const info = vi.spyOn(logger, 'info')
  await build({
    configFile: false,
    root,
    resolve: options.resolve,
    customLogger: logger,
    plugins: [incrementalPublicAssets(), ...(options.plugins ?? [])],
    build: { minify: false, reportCompressedSize: false, ...options.build }
  })
  execFileSync(process.execPath, [copyScript], { cwd: root })
  return info.mock.calls.map(([message]) => message)
}

function text(root, name) {
  return fs.readFileSync(path.join(root, name), 'utf8')
}

function expectGzip(root, name, content) {
  expect(text(root, name)).toBe(content)
  expect(gunzipSync(fs.readFileSync(path.join(root, name + '.gz'))).toString()).toBe(content)
}

it('builds complete cold and repeated outputs while copying only changed public bytes', async () => {
  const { root, outDir, write } = fixture()
  expect(await runBuild(root)).toContainEqual(expect.stringContaining('3 copied, 0 unchanged'))
  const firstEntry = text(outDir, 'index.html')
    .match(/\/assets\/[^" ]+\.js/)[0]
    .slice(1)
  const image = path.join(outDir, 'avatar/unchanged.webp')
  fs.utimesSync(image, new Date(2000, 0, 1), new Date(2000, 0, 1))
  const imageTime = fs.statSync(image).mtimeMs
  expect(await runBuild(root)).toContainEqual(expect.stringContaining('0 copied, 3 unchanged'))
  expect(fs.statSync(image).mtimeMs).toBe(imageTime)

  const source = path.join(root, 'public/settings.json')
  const originalTime = fs.statSync(source)
  write('public/settings.json', '{"state":2}')
  fs.utimesSync(source, originalTime.atime, originalTime.mtime)
  write('public/new.json', '{"added":true}')
  fs.unlinkSync(path.join(root, 'public/removed.svg'))
  write('dist/assets/entry-fixed.js', 'stale chunk')
  write('dist/assets/entry-fixed.js.gz', 'stale compressed chunk')
  write('dist/obsolete/deep/stale.json', 'stale output')
  write('entry.js', 'console.log("second")')
  expect(await runBuild(root)).toContainEqual(expect.stringContaining('2 copied, 1 unchanged'))
  expect(fs.statSync(image).mtimeMs).toBe(imageTime)
  expectGzip(outDir, 'settings.json', '{"state":2}')
  expectGzip(outDir, 'new.json', '{"added":true}')
  for (const name of [
    'removed.svg',
    'removed.svg.gz',
    firstEntry,
    firstEntry + '.gz',
    'assets/entry-fixed.js',
    'assets/entry-fixed.js.gz',
    'obsolete'
  ]) {
    expect(fs.existsSync(path.join(outDir, name))).toBe(false)
  }
  expectGzip(outDir, 'docs/Mower入门指北.html', '<p>guide one</p>')
  expectGzip(outDir, 'pages/basement_skill/buffer.json', '{"buffer":1}')
  write('Mower入门指北.html', '<p>guide two</p>')
  write('src/pages/basement_skill/buffer.json', '{"buffer":2}')
  execFileSync(process.execPath, [copyScript], { cwd: root })
  expectGzip(outDir, 'docs/Mower入门指北.html', '<p>guide two</p>')
  expectGzip(outDir, 'pages/basement_skill/buffer.json', '{"buffer":2}')
  expect(fs.existsSync(path.join(outDir, '.cache'))).toBe(false)
  expect(text(outDir, 'index.html')).not.toContain(root)
})

it('recovers complete output after a build fails following public preparation', async () => {
  const { root, outDir, write } = fixture()
  write('dist/avatar/unchanged.webp', 'incomplete copy')
  const failure = {
    name: 'fixture-failure',
    renderStart: {
      order: 'post',
      handler() {
        throw new Error('fixture failure')
      }
    }
  }
  await expect(runBuild(root, { plugins: [failure] })).rejects.toThrow('fixture failure')
  await runBuild(root)
  expect(text(outDir, 'avatar/unchanged.webp')).toBe('image bytes')
  expectGzip(outDir, 'settings.json', '{"state":1}')
  expectGzip(outDir, 'docs/Mower入门指北.html', '<p>guide one</p>')
  expectGzip(outDir, 'pages/basement_skill/buffer.json', '{"buffer":1}')
  expect(text(outDir, 'index.html')).toContain('/assets/')
})

it.each(['output', 'parent', 'root', 'ancestor', 'missing-target'])(
  'refuses a linked %s before touching its target',
  (kind) => {
    const { root, publicDir, outDir, directory } = fixture()
    const outside = path.join(directory, 'outside')
    fs.mkdirSync(outside)
    fs.writeFileSync(path.join(outside, 'sentinel'), 'keep')
    let actualRoot = root
    let actualOutput = outDir
    if (kind === 'output') fs.symlinkSync(outside, outDir, 'junction')
    else if (kind === 'missing-target')
      fs.symlinkSync(path.join(outside, 'missing'), outDir, 'junction')
    else if (kind === 'parent') {
      fs.symlinkSync(outside, path.join(root, 'linked'), 'junction')
      actualOutput = path.join(root, 'linked/dist')
    } else if (kind === 'root') {
      actualRoot = path.join(directory, 'linked-project')
      fs.symlinkSync(root, actualRoot, 'junction')
      actualOutput = path.join(actualRoot, 'dist')
    } else {
      const parent = path.join(directory, 'linked-parent')
      fs.symlinkSync(directory, parent, 'junction')
      actualRoot = path.join(parent, 'project')
      actualOutput = path.join(actualRoot, 'dist')
    }
    expect(() =>
      preparePublicOutput({
        root: actualRoot,
        publicDir:
          kind === 'root' || kind === 'ancestor' ? path.join(actualRoot, 'public') : publicDir,
        outDir: actualOutput
      })
    ).toThrow('directory link')
    expect(text(outside, 'sentinel')).toBe('keep')
  }
)

it('removes output links without traversing the linked directory', () => {
  const { root, publicDir, outDir, directory } = fixture()
  const outside = path.join(directory, 'outside')
  fs.mkdirSync(outside)
  fs.writeFileSync(path.join(outside, 'sentinel'), 'keep')
  fs.mkdirSync(outDir)
  fs.symlinkSync(outside, path.join(outDir, 'avatar'), 'junction')
  preparePublicOutput({ root, publicDir, outDir })
  expect(text(outside, 'sentinel')).toBe('keep')
  expect(text(outDir, 'avatar/unchanged.webp')).toBe('image bytes')
  expect(fs.lstatSync(path.join(outDir, 'avatar')).isSymbolicLink()).toBe(false)
})

it.each(['file', 'directory'])('preserves a root .git %s like Vite output cleanup', (kind) => {
  const { root, publicDir, outDir, write } = fixture()
  const name = kind === 'file' ? '.git' : '.git/HEAD'
  write(`dist/${name}`, 'keep git metadata')
  preparePublicOutput({ root, publicDir, outDir })
  expect(text(outDir, name)).toBe('keep git metadata')
})

it('retains Vite public copying for a custom output directory', async () => {
  const { root } = fixture()
  await runBuild(root, { build: { outDir: 'custom-dist' } })
  expect(text(path.join(root, 'custom-dist'), 'avatar/unchanged.webp')).toBe('image bytes')
})

it.each(['root', 'nested'])('builds linked public %s assets like Vite', async (kind) => {
  const { root, directory, publicDir, outDir } = fixture()
  const shared = path.join(directory, 'shared-assets')
  if (kind === 'root') fs.renameSync(publicDir, shared)
  else fs.mkdirSync(shared)
  fs.writeFileSync(path.join(shared, 'shared.json'), '{"shared":1}')
  fs.symlinkSync(shared, kind === 'root' ? publicDir : path.join(publicDir, 'shared'), 'junction')
  const name = kind === 'root' ? 'shared.json' : 'shared/shared.json'

  await runBuild(root, { build: { emptyOutDir: true } })
  expectGzip(outDir, name, '{"shared":1}')
  await runBuild(root)
  expectGzip(outDir, name, '{"shared":1}')
  fs.writeFileSync(path.join(shared, 'shared.json'), '{"shared":2}')
  await runBuild(root)
  expectGzip(outDir, name, '{"shared":2}')
})

it.each([false, true])(
  'builds a linked project with preserveSymlinks=%s',
  async (preserveSymlinks) => {
    const { root, directory, outDir } = fixture()
    const linkedRoot = path.join(directory, 'linked-project')
    fs.symlinkSync(root, linkedRoot, 'junction')
    let resolvedRoot
    const messages = await runBuild(linkedRoot, {
      resolve: { preserveSymlinks },
      plugins: [
        {
          name: 'fixture-root',
          configResolved(config) {
            resolvedRoot = config.root
          }
        }
      ]
    })
    expect(path.relative(preserveSymlinks ? linkedRoot : fs.realpathSync(root), resolvedRoot)).toBe(
      ''
    )
    if (preserveSymlinks)
      expect(messages).not.toContainEqual(expect.stringContaining('Public assets:'))
    else expect(messages).toContainEqual(expect.stringContaining('3 copied, 0 unchanged'))
    expect(text(outDir, 'avatar/unchanged.webp')).toBe('image bytes')
    expect(text(outDir, 'index.html')).toContain('/assets/')
    expectGzip(outDir, 'pages/basement_skill/buffer.json', '{"buffer":1}')
  }
)
