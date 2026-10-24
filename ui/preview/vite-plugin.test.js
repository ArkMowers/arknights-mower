import { fileURLToPath } from 'node:url'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import { flattenPreviewEntry, mockPreview } from './vite-plugin.js'

describe('mock preview entry', () => {
  it('moves the built preview entry to the static server root', async () => {
    const output = await mkdtemp(join(tmpdir(), 'mower-preview-build-'))
    try {
      await mkdir(join(output, 'preview'))
      await writeFile(
        join(output, 'preview/index.html'),
        '<script src="/assets/preview.js"></script>'
      )
      await flattenPreviewEntry(output)
      expect(await readFile(join(output, 'index.html'), 'utf8')).toContain('/assets/preview.js')
      await expect(readFile(join(output, 'preview/index.html'))).rejects.toMatchObject({
        code: 'ENOENT'
      })
    } finally {
      await rm(output, { recursive: true, force: true })
    }
  })
  it.each(['/', '/preview/', '/mowersettings', '/plan-editor'])(
    'keeps %s on the offline entry after reload',
    async (url) => {
      let middleware
      mockPreview().configureServer({
        config: { root: fileURLToPath(new URL('..', import.meta.url)) },
        middlewares: {
          use: (handler) => {
            middleware = handler
          }
        },
        transformIndexHtml: async (_url, html) => html
      })
      const response = { setHeader: vi.fn(), end: vi.fn() }
      const next = vi.fn()
      await middleware({ url, method: 'GET', headers: { accept: 'text/html' } }, response, next)
      expect(response.end.mock.calls[0][0]).toContain('/preview/main.js')
      expect(next).not.toHaveBeenCalled()
    }
  )
})
