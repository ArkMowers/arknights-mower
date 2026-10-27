import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { afterEach, expect, it } from 'vitest'

const builder = fileURLToPath(new URL('../../scripts/build_mood_runtime.mjs', import.meta.url))
const attributes = fileURLToPath(new URL('../../.gitattributes', import.meta.url))
const dependencies = fileURLToPath(new URL('../node_modules', import.meta.url))
const output = 'arknights_mower/data/mood'
const artifacts = ['runtime.js', 'source.json', 'THIRD_PARTY_MOWER_LICENSE']
const entry = 'ui/src/riic/runtimeMood.ts'
const temporary = []

afterEach(() => {
  for (const directory of temporary.splice(0))
    fs.rmSync(directory, { recursive: true, force: true })
})

function fixture(ending = '\n') {
  const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'mower-mood-build-'))
  temporary.push(root)
  function write(name, content) {
    const target = path.join(root, name)
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(target, content)
  }
  write('scripts/build_mood_runtime.mjs', fs.readFileSync(builder))
  write('ui/package.json', '{}\n')
  write(entry, 'globalThis.mowerMoodRates = () => 1\n')
  write('ui/src/riic/vendor/THIRD_PARTY_MOWER_LICENSE', `Fixture license${ending}`)
  if (fs.existsSync(attributes)) write('.gitattributes', fs.readFileSync(attributes))

  const env = {
    ...process.env,
    NODE_PATH: [dependencies, process.env.NODE_PATH].filter(Boolean).join(path.delimiter),
    GIT_CONFIG_NOSYSTEM: '1',
    GIT_CONFIG_GLOBAL: path.join(root, 'missing-git-config')
  }
  for (const name of ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'])
    delete env[name]
  function run(command, args) {
    return spawnSync(command, args, {
      cwd: root,
      env,
      encoding: 'utf8',
      windowsHide: true,
      timeout: 20000
    })
  }
  function git(...args) {
    const result = run('git', ['--no-optional-locks', ...args])
    expect(result.status, result.stderr).toBe(0)
    return result.stdout
  }
  function build(...args) {
    return run(process.execPath, ['scripts/build_mood_runtime.mjs', ...args])
  }
  function generate() {
    const result = build()
    expect(result.status, result.stderr).toBe(0)
  }
  function read(name) {
    return fs.readFileSync(path.join(root, output, name), 'utf8')
  }
  return { root, write, git, build, generate, read }
}

it('keeps generated artifacts tracked and clean after an autocrlf checkout and rebuilds', () => {
  const project = fixture()
  project.generate()
  project.git('init', '-q')
  for (const [name, value] of [
    ['core.autocrlf', 'true'],
    ['core.safecrlf', 'false'],
    ['core.hooksPath', path.join(project.root, '.git/hooks')],
    ['commit.gpgsign', 'false'],
    ['user.name', 'Mower build test'],
    ['user.email', 'mower-build-test@example.invalid']
  ])
    project.git('config', name, value)
  project.git('add', '.')
  project.git('commit', '-qm', 'fixture')
  const paths = artifacts.map((name) => `${output}/${name}`)
  for (const name of paths) fs.unlinkSync(path.join(project.root, name))
  project.git('checkout-index', '--force', '--all', '--index')
  expect(project.git('status', '--porcelain', '--', ...paths)).toBe('')
  project.generate()
  expect(project.git('status', '--porcelain', '--', ...paths)).toBe('')
  project.generate()
  expect(project.git('status', '--porcelain', '--', ...paths)).toBe('')
  expect(
    project
      .git('ls-files', '--', ...paths)
      .trim()
      .split('\n')
  ).toHaveLength(3)
})

it('preserves bytes and modification times when generated content is unchanged', () => {
  const project = fixture()
  project.generate()
  const previous = artifacts.map((name) => {
    const target = path.join(project.root, output, name)
    fs.utimesSync(target, new Date(2000, 0, 1), new Date(2000, 0, 1))
    return { name, target, content: project.read(name), mtime: fs.statSync(target).mtimeMs }
  })
  project.generate()
  for (const { name, target, content, mtime } of previous) {
    expect(project.read(name)).toBe(content)
    expect(fs.statSync(target).mtimeMs).toBe(mtime)
  }
})

it.each(['\n', '\r\n'])('checks artifacts generated from license line ending %j', (ending) => {
  const project = fixture(ending)
  project.generate()
  const result = project.build('--check')
  expect(result.status, result.stderr).toBe(0)
  expect(project.read('THIRD_PARTY_MOWER_LICENSE')).toBe('Fixture license\n')
  for (const outputEnding of ['\n', '\r\n']) {
    const name = `${output}/THIRD_PARTY_MOWER_LICENSE`
    project.write(name, `Fixture license${outputEnding}`)
    const target = path.join(project.root, name)
    fs.utimesSync(target, new Date(2000, 0, 1), new Date(2000, 0, 1))
    const mtime = fs.statSync(target).mtimeMs
    const checked = project.build('--check')
    expect(checked.status, checked.stderr).toBe(0)
    expect(project.read('THIRD_PARTY_MOWER_LICENSE')).toBe(`Fixture license${outputEnding}`)
    expect(fs.statSync(target).mtimeMs).toBe(mtime)
  }
})

it('normalizes old CRLF artifacts once without changing their source hashes', () => {
  const project = fixture()
  project.generate()
  const expected = Object.fromEntries(artifacts.map((name) => [name, project.read(name)]))
  for (const name of artifacts)
    project.write(`${output}/${name}`, expected[name].replace(/\n/g, '\r\n'))
  project.generate()
  for (const name of artifacts) expect(project.read(name)).toBe(expected[name])
  const mtimes = artifacts.map((name) => fs.statSync(path.join(project.root, output, name)).mtimeMs)
  project.generate()
  expect(
    artifacts.map((name) => fs.statSync(path.join(project.root, output, name)).mtimeMs)
  ).toEqual(mtimes)
})

it('rejects stale artifacts without writing and regenerates actual source changes', () => {
  const project = fixture()
  project.generate()
  const before = Object.fromEntries(artifacts.map((name) => [name, project.read(name)]))
  project.write(entry, 'globalThis.mowerMoodRates = () => 2\n')
  const stale = project.build('--check')
  expect(stale.status).not.toBe(0)
  expect(stale.stderr).toContain('Mood runtime is stale: runtime.js')
  for (const name of artifacts) expect(project.read(name)).toBe(before[name])

  project.generate()
  expect(project.read('runtime.js')).not.toBe(before['runtime.js'])
  const manifest = JSON.parse(project.read('source.json'))
  expect(manifest.sha256).toBe(
    crypto.createHash('sha256').update(project.read('runtime.js')).digest('hex')
  )
  expect(manifest.files[entry]).toBe(
    crypto.createHash('sha256').update('globalThis.mowerMoodRates = () => 2\n').digest('hex')
  )
  const checked = project.build('--check')
  expect(checked.status, checked.stderr).toBe(0)
})
