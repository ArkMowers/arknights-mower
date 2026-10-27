import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { routes } from './routes'

describe('backend page fallback contract', () => {
  it('uses the unified settings page and keeps old addresses as redirects', () => {
    const children = routes[0].children
    const page = children.find((route) => route.name === 'settings')
    expect(page.component).toBeTruthy()
    expect(page.meta.settings).not.toBe(true)
    for (const path of ['task-settings', 'mowersettings', 'maasettings']) {
      const legacy = children.find((route) => route.path === path)
      expect(legacy.component).toBeUndefined()
      expect(legacy.redirect({ query: { token: 'demo' }, hash: '#mower-data' })).toEqual({
        name: 'settings',
        query: { token: 'demo' },
        hash: '#mower-data'
      })
    }
  })

  it('lists every production frontend route, including parent routes', () => {
    const paths = new Set()
    function visit(records, parent = '') {
      for (const route of records) {
        if (route.path === '/:pathMatch(.*)') continue
        const path = route.path.startsWith('/') ? route.path : `${parent}/${route.path}`
        const normalized = path.replace(/\/+/g, '/').replace(/\/$/, '') || '/'
        if (normalized === '/taskflow-prototype') continue
        paths.add(normalized)
        if (route.children) visit(route.children, normalized)
      }
    }
    visit(routes)
    const manifest = JSON.parse(
      readFileSync(new URL('../public/frontend-routes.json', import.meta.url), 'utf8')
    )
    expect(manifest.toSorted()).toEqual([...paths].toSorted())
    expect(manifest).not.toContain('/taskflow-prototype')
  })
})
