import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { routes } from './routes'

describe('backend page fallback contract', () => {
  it('lists every concrete frontend route, including parent routes', () => {
    const paths = new Set()
    function visit(records, parent = '') {
      for (const route of records) {
        if (route.path === '/:pathMatch(.*)') continue
        const path = route.path.startsWith('/') ? route.path : `${parent}/${route.path}`
        const normalized = path.replace(/\/+/g, '/').replace(/\/$/, '') || '/'
        paths.add(normalized)
        if (route.children) visit(route.children, normalized)
      }
    }
    visit(routes)
    const manifest = JSON.parse(
      readFileSync(new URL('../public/frontend-routes.json', import.meta.url), 'utf8')
    )
    expect(manifest.toSorted()).toEqual([...paths].toSorted())
  })
})
