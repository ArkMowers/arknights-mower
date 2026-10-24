import { readFileSync } from 'node:fs'
import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppSidebar from './AppSidebar.vue'
import MowerAIIcon from './MowerAIIcon.vue'
import MobileTabBar from './MobileTabBar.vue'
import {
  mobileTabItems,
  mobileTabs,
  navigationItems,
  navigationSections,
  sidebarNavigationItems
} from '@/navigation'
import { routes } from '@/routes'

vi.mock('@/composables/sidebarPreferences', async (original) => {
  const actual = await original()
  return {
    ...actual,
    useSidebarPreferences: () => actual.createSidebarPreferences({ storage: null })
  }
})

// Overlay followers mount their styles into document.head, which Node lacks.
// These stubs retain the closed trigger markup; popover interaction has its own tests.
vi.mock('naive-ui', async (original) => {
  const { defineComponent } = await import('vue')
  return {
    ...(await original()),
    NDropdown: defineComponent({
      inheritAttrs: false,
      setup:
        (_, { slots }) =>
        () =>
          slots.default?.()
    }),
    NPopover: defineComponent({
      inheritAttrs: false,
      props: { show: Boolean },
      setup:
        (props, { slots }) =>
        () => [slots.trigger?.(), ...(props.show ? slots.default() : [])]
    }),
    NTooltip: defineComponent({
      inheritAttrs: false,
      setup:
        (_, { slots }) =>
        () =>
          slots.trigger?.()
    })
  }
})

const Page = { render: () => null }

// The real nested route table with stub pages, so parent routes match as they do in the app.
function stubRoutes(records) {
  return records.map(({ component, children, ...record }) => ({
    ...record,
    ...(component && { component: Page }),
    ...(children && { children: stubRoutes(children) })
  }))
}

async function render(component, props = {}, path = '/', openTab) {
  const router = createRouter({ history: createMemoryHistory(), routes: stubRoutes(routes) })
  const renderedComponent = openTab
    ? {
        ...component,
        setup(props, context) {
          const state = component.setup(props, context)
          state.openTab.value = openTab
          return state
        }
      }
    : component
  const app = createSSRApp({ render: () => h(renderedComponent, props) })
  app.use(router)
  await router.push(path)
  return renderToString(app)
}

function links(html) {
  return [...html.matchAll(/<a\b[^>]*>/g)].map(([tag]) => ({
    tag,
    href: tag.match(/\bhref="([^"]*)"/)?.[1]
  }))
}

const isActive = (tag) => /\bclass="[^"]*\bis-active\b/.test(tag)
const moreButton = (html) =>
  html.match(/<button\b[^>]*\bclass="[^"]*\bmobile-tab-bar__more\b[^"]*"[^>]*>/)[0]
const internalPaths = sidebarNavigationItems.filter((item) => item.to).map((item) => item.to)

it.each([
  ['sidebar', AppSidebar, internalPaths],
  [
    'mobile tabs',
    MobileTabBar,
    mobileTabs.filter((item) => !item.tabGroup && !item.items).map((item) => item.to)
  ],
  [
    'mobile plan picker',
    MobileTabBar,
    ['/', '/task-settings', '/plan-editor', '/rescue-plan-editor', '/mastery-recommendation'],
    'plan'
  ],
  [
    'mobile report picker',
    MobileTabBar,
    [
      '/',
      '/task-settings',
      '/mastery-recommendation',
      '/record/line',
      '/record/pie',
      '/record/report',
      '/record/depot',
      '/record/trading_analysis',
      '/record/recycling',
      '/record/log-schedule'
    ],
    'reports'
  ]
])('retains session credentials in all %s page links', async (_name, component, paths, openTab) => {
  const rendered = links(
    await render(component, {}, '/?token=session-token&window_shell=1', openTab)
  )
  const internal = rendered.filter((link) => !/^https?:/.test(link.href))
  expect(
    internal.map((link) => new URL(link.href, 'http://localhost').pathname).toSorted()
  ).toEqual(paths.toSorted())
  for (const link of internal) {
    const destination = new URL(link.href.replaceAll('&amp;', '&'), 'http://localhost')
    expect(destination.searchParams.get('token')).toBe('session-token')
    expect(destination.searchParams.get('window_shell')).toBe('1')
  }
})

// Inner markup of each rendered n-icon; an icon that did not resolve to a component has no svg.
// Vitest unwraps CommonJS default imports, so the dev-server blank icon from a CommonJS
// @vicons file is caught by the no-restricted-imports rule in ui/.eslintrc.cjs instead.
function iconBodies(html) {
  return [...html.matchAll(/<i\b[^>]*\bclass="[^"]*\bn-icon\b[^"]*"[^>]*>([\s\S]*?)<\/i>/g)].map(
    ([, body]) => body
  )
}

describe('[INV-UI-04] AppSidebar', () => {
  it('renders one link per navigation entry', async () => {
    const html = await render(AppSidebar)
    expect(
      links(html)
        .map((link) => link.href)
        .toSorted()
    ).toEqual(
      sidebarNavigationItems
        .filter((item) => item.to || item.href)
        .map((item) => item.to ?? item.href)
        .toSorted()
    )
  })

  it('starts with logs and all settings and keeps only the assistant in the footer', async () => {
    const html = await render(AppSidebar)
    expect(
      links(html)
        .slice(0, 3)
        .map((link) => link.href)
    ).toEqual(['/', '/task-settings', '/plan-editor'])
    expect(html).toContain('排班编辑')
    expect(html).not.toContain('救急排班编辑')
    expect(html).not.toContain('Mower 设置')
    const footerStart = html.indexOf('class="app-sidebar__footer"')
    expect(footerStart).toBeGreaterThan(0)
    const scrolling = html.slice(0, footerStart)
    const footer = html.slice(footerStart)
    expect(links(scrolling).some((link) => link.href === '/maasettings')).toBe(false)
    expect(links(footer)).toEqual([])
    const assistant = footer.match(
      /<button\b[^>]*title="Mower AI 助手"[^>]*>[\s\S]*?<\/button>/
    )?.[0]
    const icon = await renderToString(createSSRApp(MowerAIIcon))
    expect(assistant).toContain(icon)
  })

  it('opens external entries in a new tab without opener access', async () => {
    const html = await render(AppSidebar)
    for (const item of navigationItems.filter((entry) => entry.href)) {
      const { tag } = links(html).find((link) => link.href === item.href)
      expect(tag).toContain('target="_blank"')
      expect(tag).toContain('rel="noopener noreferrer"')
    }
  })

  it.each(internalPaths)('marks only the link to %s as the current page', async (path) => {
    const rendered = links(await render(AppSidebar, {}, path))
    const current = rendered.filter((link) => link.tag.includes('aria-current="page"'))
    expect(current.map((link) => link.href)).toEqual([path])
    expect(rendered.filter((link) => isActive(link.tag)).map((link) => link.href)).toEqual([path])
  })

  it('labels each titled section by its heading', async () => {
    const html = await render(AppSidebar)
    const ids = [...html.matchAll(/aria-labelledby="([^"]+)"/g)].map(([, id]) => id)
    expect(ids).toHaveLength(
      navigationSections.filter(
        (section) =>
          section.title && section.items.some((item) => !item.footer && item.sidebar !== false)
      ).length
    )
    for (const id of ids) expect(html).toContain(`id="${id}"`)
  })

  it.each([false, true])(
    'keeps navigation and customization accessible with group controls: %s',
    async (collapsed) => {
      const html = await render(AppSidebar, { collapsed })
      const headings = [...html.matchAll(/<button\b[^>]*class="app-sidebar__heading"[^>]*>/g)]
      expect(headings).toHaveLength(3)
      for (const [heading] of headings) {
        expect(heading).toContain('aria-expanded="true"')
        expect(heading).toContain('aria-controls=')
        expect(heading.includes(' disabled')).toBe(collapsed)
      }
      expect(html).not.toContain('收起侧边栏')
      expect(html).not.toContain('展开侧边栏')
      expect(html).toContain('Mower AI 助手')
      expect(html).toContain('常用')
      if (!collapsed) {
        expect(html).toContain('管理常用分组')
        expect(html).not.toContain('app-sidebar__group-add')
      }
      expect(html).not.toContain('aria-haspopup="dialog"')
      for (const item of sidebarNavigationItems) expect(html).toContain(item.label)
    }
  )

  it('draws an svg for every icon', async () => {
    const bodies = iconBodies(await render(AppSidebar))
    expect(bodies.length).toBeGreaterThanOrEqual(sidebarNavigationItems.length)
    for (const body of bodies) expect(body).toMatch(/^<svg\b/)
  })
})

describe('[INV-UI-04] MobileTabBar', () => {
  it.each([
    ['plan', '/rescue-plan-editor', ['/plan-editor', '/rescue-plan-editor']],
    [
      'reports',
      '/record/depot',
      [
        '/record/line',
        '/record/pie',
        '/record/report',
        '/record/depot',
        '/record/trading_analysis',
        '/record/recycling',
        '/record/log-schedule'
      ]
    ]
  ])(
    'offers every %s destination and marks the current secondary page',
    async (tab, path, pages) => {
      const html = await render(MobileTabBar, {}, path, tab)
      const pickerLinks = links(html).filter((link) => link.tag.includes('mobile-tab-bar__page'))
      expect(pickerLinks.map((link) => link.href)).toEqual(pages)
      expect(pickerLinks.filter((link) => isActive(link.tag)).map((link) => link.href)).toEqual([
        path
      ])
      for (const { tag } of pickerLinks.filter((link) => link.href === path)) {
        expect(tag).toContain('aria-current="page"')
      }
    }
  )

  it('links direct tabs, exposes page pickers and opens the page drawer from more', async () => {
    const html = await render(MobileTabBar, { moreOpen: true })
    expect(links(html).map((link) => link.href)).toEqual(
      mobileTabs.filter((item) => !item.tabGroup && !item.items).map((item) => item.to)
    )
    for (const item of mobileTabs) expect(html).toContain(item.shortLabel)
    const pickers = [...html.matchAll(/<button\b[^>]*\baria-controls="([^"]+)"[^>]*>/g)]
    expect(pickers).toHaveLength(2)
    for (const [tag] of pickers) {
      expect(tag).toContain('aria-expanded="false"')
      expect(tag).toContain('aria-haspopup="dialog"')
      expect(tag).toContain('选择页面')
    }
    const more = moreButton(html)
    expect(more).toContain('aria-haspopup="dialog"')
    expect(more).toContain('aria-expanded="true"')
  })

  it('draws an svg for every icon', async () => {
    const bodies = iconBodies(await render(MobileTabBar))
    expect(bodies).toHaveLength(8)
    for (const body of bodies) expect(body).toMatch(/^<svg\b/)
  })

  // Pages outside the tab bar are reached through the drawer, so "more" stays highlighted there.
  it.each(internalPaths)('highlights more on %s exactly when it has no tab', async (path) => {
    const hasTab = mobileTabs.flatMap(mobileTabItems).some((page) => page.to === path)
    expect(isActive(moreButton(await render(MobileTabBar, {}, path)))).toBe(!hasTab)
  })

  it.each([
    ['/plan-editor', '排班'],
    ['/RESCUE-plan-editor/', '排班'],
    ['/RECORD/depot/', '报表']
  ])('highlights the %s page picker as %s', async (path, label) => {
    const html = await render(MobileTabBar, {}, path)
    const pickers = [...html.matchAll(/(<button\b[^>]*>)([\s\S]*?)<\/button>/g)]
    const active = pickers.filter(([, tag]) => isActive(tag))
    expect(active).toHaveLength(1)
    expect(active[0][2]).toContain(label)
  })

  it('links the settings tab straight to all settings', async () => {
    const html = await render(MobileTabBar, {}, '/task-settings')
    const current = links(html).filter((link) => isActive(link.tag))
    expect(current.map((link) => link.href)).toEqual(['/task-settings'])
    expect(current[0].tag).toContain('aria-current="page"')
    expect(html).not.toContain('设置，选择页面')
    expect(html).not.toContain('href="/maasettings"')
  })

  it('shows compact settings and report labels with complete accessible names', async () => {
    const html = await render(MobileTabBar, {}, '/task-settings')
    const task = links(html).find((link) => link.href === '/task-settings')
    expect(task.tag).toContain('aria-label="全部设置"')
    expect(task.tag).toContain('aria-current="page"')
    expect(html).toContain('aria-label="数据报表，选择页面"')
    expect(html).toMatch(/class="mobile-tab-bar__label"[^>]*>\s*设置\s*</)
    expect(html).toMatch(/class="mobile-tab-bar__label"[^>]*>\s*报表\s*</)
  })

  // Highlighting follows router matching: case and a trailing slash still reach the page,
  // while a path that falls through to the catch-all highlights nothing.
  it.each([
    ['/BASEMENTSkill/', true],
    ['/RECORD/depot/', false],
    ['/record/line//', false],
    ['/no-such-page', false]
  ])('highlights more on %s: %s', async (path, active) => {
    expect(isActive(moreButton(await render(MobileTabBar, {}, path)))).toBe(active)
  })
})

// App.vue hosts the shell components only; navigation entries live in src/navigation.js.
describe('[INV-UI-04] App.vue', () => {
  const source = readFileSync(new URL('../App.vue', import.meta.url), 'utf8')

  it.each([
    ['<n-menu>', /<n-menu[\s/>]/],
    ['<n-tabs> or <n-tab>', /<n-tabs?[\s/>]/],
    ['<router-link>', /<router-link[\s/>]/],
    ['RouterLink', /\bRouterLink\b/]
  ])('defines no navigation through %s', (_name, pattern) => {
    expect(source).not.toMatch(pattern)
  })
})
