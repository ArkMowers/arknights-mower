import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { routes } from './routes'

describe('backend page fallback contract', () => {
  it('reserves the settings page and directory for Mower settings', () => {
    const settings = routes[0].children.filter((route) => route.meta?.settings)
    expect(settings.map((route) => route.name)).toEqual(['mowersettings'])
    expect(
      settings.filter((route) => route.meta.settingsSidebar).map((route) => route.name)
    ).toEqual(['mowersettings'])
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
