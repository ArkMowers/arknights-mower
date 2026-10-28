import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, defineComponent, h, nextTick, ssrContextKey } from 'vue'
import { createMemoryHistory, createRouter, RouterLink } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'
import MobileTabBar from '@/components/MobileTabBar.vue'
import SessionLink from '@/components/SessionLink.vue'
import { createSidebarPreferences } from '@/composables/sidebarPreferences'
import { navigationItems, navigationSections, sidebarNavigationItems } from '@/navigation'
import { i18n } from '@/i18n'
import { navigationGroupTitle, navigationLabel } from './navigation'

let preferences
let storage
const mounted = []

vi.mock('@/composables/sidebarPreferences', async (original) => ({
  ...(await original()),
  useSidebarPreferences: () => preferences
}))

const Dropdown = defineComponent({
  props: ['options'],
  setup:
    (props, { slots }) =>
    () =>
      h('dropdown', { options: props.options }, slots.default?.())
})
const Popover = defineComponent({
  props: ['show'],
  setup:
    (props, { slots }) =>
    () =>
      h('popover', [slots.trigger?.(), ...(props.show ? slots.default() : [])])
})
const Tooltip = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      slots.trigger?.()
})
const Scroll = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      h('scroll-region', slots.default?.())
})
const Sortable = defineComponent({
  props: ['modelValue'],
  setup:
    (props, { slots }) =>
    () =>
      h(
        'sortable',
        props.modelValue.map((element, index) => slots.item({ element, index }))
      )
})
const HiddenEditor = { render: () => null }
const Icon = { render: () => h('icon') }

function clientComponent(component, name, components = {}, bindings = {}) {
  const { descriptor } = parse(
    readFileSync(new URL(`../components/${name}.vue`, import.meta.url), 'utf8')
  )
  return {
    ...component,
    ssrRender: undefined,
    components,
    render: compile(descriptor.template.content, { hoistStatic: false }),
    setup: (props, context) => ({ ...component.setup(props, context), ...bindings })
  }
}

const ClientLink = clientComponent(SessionLink, 'SessionLink', { RouterLink })
const sharedComponents = { SessionLink: ClientLink, NIcon: Icon }
const ClientSidebar = clientComponent(
  AppSidebar,
  'AppSidebar',
  { ...sharedComponents, draggable: Sortable, NDropdown: Dropdown, NTooltip: Tooltip },
  { SessionLink: ClientLink, SidebarScroll: Scroll, SidebarCustomize: HiddenEditor }
)
const ClientTabBar = clientComponent(MobileTabBar, 'MobileTabBar', {
  ...sharedComponents,
  NPopover: Popover
})

const node = (tag) => ({ tag, props: {}, style: {}, children: [], parent: null, text: '' })
function remove(element) {
  if (!element.parent) return
  const siblings = element.parent.children
  siblings.splice(siblings.indexOf(element), 1)
  element.parent = null
}
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => (element.text = text),
  setElementText(element, text) {
    element.text = text
    element.children = []
  },
  parentNode: (element) => element.parent,
  nextSibling: (element) => {
    const siblings = element.parent?.children || []
    return siblings[siblings.indexOf(element) + 1] || null
  },
  patchProp: (element, key, _oldValue, value) => (element.props[key] = value),
  insert(element, parent, anchor) {
    remove(element)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
  },
  remove
})
const all = (element) => [element, ...element.children.flatMap(all)]
const textContent = (element) => element.text + element.children.map(textContent).join('')
const links = (root) => all(root).filter((element) => element.tag === 'a')

beforeEach(() => {
  i18n.global.locale.value = 'zh-CN'
  storage = { getItem: () => null, setItem: vi.fn() }
  preferences = createSidebarPreferences({ storage })
})

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  i18n.global.locale.value = 'zh-CN'
})

async function mount(component, props = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: navigationItems
      .filter((item) => item.to)
      .map((item) => ({ path: item.to, component: { render: () => null } }))
  })
  await router.push('/?token=localization-test')
  const root = node('root')
  const app = renderer.createApp(component, props)
  app.use(router)
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)
  mounted.push(app)
  return { root, component: app._instance.setupState, router }
}

describe('navigation display language', () => {
  it('translates built-in labels while retaining source labels, keys and destinations', () => {
    const source = JSON.stringify(sidebarNavigationItems)
    const log = navigationItems.find((item) => item.key === 'log')
    const settings = navigationItems.find((item) => item.key === 'task-settings')
    expect(navigationLabel(log)).toBe('运行日志')
    expect(navigationLabel(log, true)).toBe('日志')
    i18n.global.locale.value = 'en-US'
    expect(navigationLabel(log)).toBe('Logs')
    expect(navigationLabel(settings, true)).toBe('Settings')
    expect(navigationLabel({ key: 'custom', label: '自己的页面' })).toBe('自己的页面')
    expect(JSON.stringify(sidebarNavigationItems)).toBe(source)
    expect(log).toMatchObject({ key: 'log', label: '运行日志', shortLabel: '日志', to: '/' })
    expect(settings.to).toBe('/settings')
  })

  it('translates only unchanged built-in group titles', () => {
    i18n.global.locale.value = 'en-US'
    expect(navigationGroupTitle(navigationSections[0])).toBe('Favorites')
    expect(navigationGroupTitle({ key: 'pinned', title: '置顶' })).toBe('Pinned')
    expect(navigationGroupTitle({ key: 'daily', title: '自己常用的页面' })).toBe('自己常用的页面')
    expect(navigationGroupTitle({ key: 'custom', title: '数据报表' })).toBe('数据报表')
    expect(navigationGroupTitle({ key: 'reports', title: 'Reports' })).toBe('Reports')
  })

  it('falls back to Chinese when an English navigation translation is missing', () => {
    const english = i18n.global.getLocaleMessage('en-US')
    const fallbackWarn = i18n.global.fallbackWarn
    const missingWarn = i18n.global.missingWarn
    i18n.global.setLocaleMessage('en-US', { ...english, navigation: {} })
    i18n.global.locale.value = 'en-US'
    i18n.global.fallbackWarn = false
    i18n.global.missingWarn = false
    try {
      const log = navigationItems.find((item) => item.key === 'log')
      expect(navigationLabel(log)).toBe('运行日志')
      expect(navigationLabel(log, true)).toBe('日志')
      expect(navigationGroupTitle(navigationSections[0])).toBe('常用')
    } finally {
      i18n.global.setLocaleMessage('en-US', english)
      i18n.global.fallbackWarn = fallbackWarn
      i18n.global.missingWarn = missingWarn
    }
  })

  it('updates mounted sidebar labels, menus and accessible names without saving preferences', async () => {
    preferences.renameGroup('daily', '我的常用页面')
    preferences.addGroup('资料')
    preferences.setPinned('record-depot', true)
    const stateBefore = JSON.stringify(preferences.state.value)
    storage.setItem.mockClear()
    const { root } = await mount(ClientSidebar)
    const sidebar = all(root).find((element) => element.tag === 'nav')
    const logLink = links(root).find((element) => element.props.title === '运行日志')
    const destinations = links(root).map((element) => element.props.href)
    expect(textContent(root)).toContain('我的常用页面')
    expect(sidebar.props['aria-label']).toBe('主导航')
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(logLink.props.title).toBe('Logs')
    expect(textContent(logLink)).toBe('Logs')
    expect(sidebar.props['aria-label']).toBe('Main navigation')
    expect(textContent(root)).toContain('我的常用页面')
    expect(textContent(root)).toContain('资料')
    expect(textContent(root)).toContain('Reference')
    expect(textContent(root)).toContain('Pinned')
    expect(all(root).some((element) => element.props['aria-label'] === 'Manage Logs')).toBe(true)
    expect(
      all(root).some((element) => element.props['aria-label'] === 'Manage 我的常用页面 group')
    ).toBe(true)
    const pinOption = all(root)
      .flatMap((element) => element.props.options || [])
      .find((option) => option.key === 'pin')
    expect(['Pin', 'Unpin']).toContain(pinOption.label)
    expect(links(root).map((element) => element.props.href)).toEqual(destinations)
    expect(JSON.stringify(preferences.state.value)).toBe(stateBefore)
    expect(storage.setItem).not.toHaveBeenCalled()
    i18n.global.locale.value = 'zh-CN'
    await nextTick()
    expect(logLink.props.title).toBe('运行日志')
    expect(textContent(root)).toContain('我的常用页面')
    expect(storage.setItem).not.toHaveBeenCalled()
  })

  it('updates mounted mobile tabs and an open page picker while retaining route selection', async () => {
    const stateBefore = JSON.stringify(preferences.state.value)
    const { root, component, router } = await mount(ClientTabBar)
    component.setTabOpen('reports', true)
    await nextTick()
    const tab = links(root).find((element) => element.props.title === '全部设置')
    const destinations = links(root).map((element) => element.props.href)
    expect(textContent(tab)).toBe('设置')
    expect(all(root).some((element) => element.props['aria-label'] === '数据报表页面')).toBe(true)
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(tab.props.title).toBe('All Settings')
    expect(tab.props['aria-label']).toBe('All Settings')
    expect(textContent(tab)).toBe('Settings')
    expect(all(root).some((element) => element.props['aria-label'] === 'Quick navigation')).toBe(
      true
    )
    expect(
      all(root).some((element) => element.props['aria-label'] === 'Reports, choose a page')
    ).toBe(true)
    expect(all(root).some((element) => element.props['aria-label'] === 'Reports pages')).toBe(true)
    expect(textContent(root)).toContain('Operator Morale')
    expect(textContent(root)).toContain('Depot')
    expect(textContent(root)).toContain('More')
    expect(component.openTab).toBe('reports')
    expect(component.activeTab).toBe('log')
    expect(router.currentRoute.value.fullPath).toBe('/?token=localization-test')
    expect(links(root).map((element) => element.props.href)).toEqual(destinations)
    expect(JSON.stringify(preferences.state.value)).toBe(stateBefore)
    expect(storage.setItem).not.toHaveBeenCalled()
  })
})
