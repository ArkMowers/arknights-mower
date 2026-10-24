import { describe, expect, it } from 'vitest'
import { mobileTabItems, mobileTabs, navigationItems, navigationSections } from './navigation'
import { routes } from './routes'

// Production page paths exclude the catch-all and the development-only taskflow prototype.
function pagePaths(records, parent = '') {
  const paths = []
  for (const route of records) {
    if (route.path.includes(':')) continue
    const path = route.path.startsWith('/') ? route.path : `${parent}/${route.path}`
    const normalized = path.replace(/\/+/g, '/').replace(/\/$/, '') || '/'
    if (route.component && normalized !== '/taskflow-prototype') paths.push(normalized)
    if (route.children) paths.push(...pagePaths(route.children, normalized))
  }
  return paths
}

const internalItems = navigationItems.filter((item) => item.to)
const externalItems = navigationItems.filter((item) => item.href)

describe('[INV-UI-04] Single Navigation Definition', () => {
  it('lists every production page route exactly once', () => {
    expect(internalItems.map((item) => item.to).toSorted()).toEqual(pagePaths(routes).toSorted())
    expect(internalItems.some((item) => item.to === '/taskflow-prototype')).toBe(false)
  })

  it('gives every entry a unique key, a label, an icon and exactly one target', () => {
    const keys = navigationItems.map((item) => item.key)
    expect(new Set(keys).size).toBe(keys.length)
    for (const item of navigationItems) {
      expect(item.label, item.key).toBeTruthy()
      expect(item.icon, item.key).toBeTruthy()
      expect(Boolean(item.to) !== Boolean(item.href), item.key).toBe(true)
    }
  })

  it('titles every section, including the daily task pages', () => {
    expect(navigationSections.length).toBeGreaterThan(1)
    for (const section of navigationSections) {
      expect(section.title, section.key).toBeTruthy()
      expect(section.items.length, section.key).toBeGreaterThan(0)
    }
    expect(navigationSections.find((section) => section.key === 'daily')).toMatchObject({
      title: '常用',
      items: [
        { key: 'log' },
        { key: 'task-settings', label: '任务配置', to: '/task-settings' },
        { key: 'plan' },
        { key: 'rescue-plan' },
        { key: 'mastery' }
      ]
    })
  })

  it('opens external entries over canonical https URLs only', () => {
    expect(externalItems.length).toBeGreaterThan(0)
    for (const item of externalItems) {
      const url = new URL(item.href)
      expect(url.protocol, item.key).toBe('https:')
      expect(url.href, item.key).toBe(item.href)
    }
  })

  it('builds direct tabs and section pickers from the shared navigation definition', () => {
    expect(mobileTabs).toHaveLength(6)
    for (const tab of mobileTabs) {
      expect([...internalItems, ...navigationSections], tab.key).toContain(tab)
      expect(tab.shortLabel, tab.key).toBeTruthy()
    }
    expect(mobileTabs.map((tab) => tab.shortLabel)).toEqual([
      '任务',
      '排班',
      '养成',
      '日志',
      '报表',
      '设置'
    ])
    expect(mobileTabs.find((tab) => tab.key === 'task-settings')).toMatchObject({
      label: '任务配置',
      to: '/task-settings'
    })
  })

  it('offers both scheduling pages while settings links only to Mower settings', () => {
    const plan = mobileTabs.find((tab) => tab.key === 'plan')
    const settings = mobileTabs.find((tab) => tab.key === 'mower-settings')
    expect(mobileTabItems(plan).map((item) => item.to)).toEqual([
      '/plan-editor',
      '/rescue-plan-editor'
    ])
    expect(mobileTabItems(settings).map((item) => item.to)).toEqual(['/mowersettings'])
    expect(internalItems.some((item) => item.to === '/maasettings')).toBe(false)
    const pages = mobileTabs.flatMap(mobileTabItems)
    expect(new Set(pages).size).toBe(pages.length)
  })

  it('opens every report from a section picker without assigning the group a page route', () => {
    const tab = mobileTabs.find((item) => item.key === 'reports')
    expect(tab).toBe(navigationSections.find((section) => section.key === 'reports'))
    expect(tab.to).toBeUndefined()
    expect(mobileTabItems(tab).map((item) => item.to)).toEqual([
      '/record/line',
      '/record/pie',
      '/record/report',
      '/record/depot',
      '/record/trading_analysis',
      '/record/recycling',
      '/record/log-schedule'
    ])
  })

  it('keeps every data page together under 数据报表', () => {
    const reports = navigationSections.find((section) => section.title === '数据报表')
    expect(reports.items.map((item) => item.to)).toEqual([
      '/record/line',
      '/record/pie',
      '/record/report',
      '/record/depot',
      '/record/trading_analysis',
      '/record/recycling',
      '/record/log-schedule'
    ])
    expect(navigationSections.some((section) => section.title === '数据工具')).toBe(false)
  })
})
