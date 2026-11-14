import { Buffer } from 'node:buffer'
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { build, createServer } from 'vite'
import viteConfig from './vite.config.js'

// 这两个用例要启动真实的 Vite 服务器/构建，启动耗时受并行测试的 CPU 争用影响；
// 显式放宽超时，避免全量运行时按默认 5 秒误判失败。
const VITE_TIMEOUT = 30000

let server
afterEach(async () => {
  await server?.close()
  server = null
})

function changelogPlugin() {
  const config = viteConfig({ command: 'serve', mode: 'test' })
  const plugin = config.plugins.find((item) => item?.name === 'mower-changelog')
  expect(plugin).toBeTruthy()
  return plugin
}

describe('changelog module', () => {
  it(
    'transforms the root changelog into JavaScript without exposing its directory',
    { timeout: VITE_TIMEOUT },
    async () => {
      // 只加载 changelog 插件即可验证虚拟模块转换，避免为一次转换启动整套应用插件。
      server = await createServer({
        configFile: false,
        root: fileURLToPath(new URL('.', import.meta.url)),
        cacheDir: fileURLToPath(
          new URL('./node_modules/.cache/changelog-test-vite', import.meta.url)
        ),
        plugins: [changelogPlugin()],
        server: { middlewareMode: true, hmr: false, watch: null },
        optimizeDeps: { noDiscovery: true, include: [] }
      })

      const transformed = await server.transformRequest('virtual:mower-changelog')
      const module = await import(
        `data:text/javascript;base64,${Buffer.from(transformed.code).toString('base64')}`
      )

      expect(module.default).toBe(
        await readFile(new URL('../CHANGELOG.md', import.meta.url), 'utf8')
      )
      expect(server.config.server.fs.allow).not.toContain(
        fileURLToPath(new URL('..', import.meta.url))
          .replace(/\\/g, '/')
          .replace(/\/$/, '')
      )
    }
  )

  it(
    'includes the same authoritative content in the built module',
    { timeout: VITE_TIMEOUT },
    async () => {
      const result = await build({
        configFile: false,
        plugins: [changelogPlugin()],
        logLevel: 'silent',
        build: {
          write: false,
          minify: false,
          rollupOptions: {
            input: 'virtual:mower-changelog',
            preserveEntrySignatures: 'strict'
          }
        }
      })
      const entry = result.output.find((item) => item.type === 'chunk' && item.isEntry)
      const module = await import(
        `data:text/javascript;base64,${Buffer.from(entry.code).toString('base64')}`
      )
      expect(module.default).toBe(
        await readFile(new URL('../CHANGELOG.md', import.meta.url), 'utf8')
      )
    }
  )
})
