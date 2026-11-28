import { readFile, rename } from 'node:fs/promises'
import { resolve } from 'node:path'

export function mockPreview() {
  return {
    name: 'mower-offline-preview',
    async writeBundle(options) {
      await flattenPreviewEntry(options.dir)
    },
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        const path = new URL(request.url, 'http://mower-preview.invalid').pathname
        if (
          request.method !== 'GET' ||
          (!request.headers.accept?.includes('text/html') &&
            path !== '/' &&
            path !== '/preview/' &&
            !path.endsWith('.html'))
        )
          return next()
        try {
          const source = await readFile(resolve(server.config.root, 'preview/index.html'), 'utf8')
          const html = await server.transformIndexHtml(request.url, source)
          response.setHeader('Content-Type', 'text/html; charset=utf-8')
          response.end(html)
        } catch (error) {
          next(error)
        }
      })
    }
  }
}

export async function flattenPreviewEntry(outputDirectory) {
  await rename(
    resolve(outputDirectory, 'preview/index.html'),
    resolve(outputDirectory, 'index.html')
  )
}
