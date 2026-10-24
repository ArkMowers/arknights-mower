import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, nextTick, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppSidebar from './AppSidebar.vue'
import { createSidebarPreferences } from '@/composables/sidebarPreferences'
import { navigationItems } from '@/navigation'

let preferences
const mounted = []

vi.mock('@/composables/sidebarPreferences', async (original) => ({
  ...(await original()),
  useSidebarPreferences: () => preferences
}))

vi.mock('naive-ui', async (original) => {
  const { defineComponent, h } = await import('vue')
  return {
    ...(await original()),
    NDropdown: defineComponent({
      inheritAttrs: false,
      setup:
        (_, { slots }) =>
        () =>
          slots.default?.()
    }),
    NScrollbar: defineComponent({
      inheritAttrs: false,
      setup:
        (_, { slots, attrs }) =>
        () =>
          h('scroll-region', attrs, slots.default?.())
    }),
    NSelect: defineComponent({
      props: ['options', 'value'],
      setup: (props) => () =>
        h(
          'select',
          props.options.map((option) => h('option', { value: option.value }, option.label))
        )
    }),
    NModal: defineComponent({
      props: ['show'],
      inheritAttrs: false,
      setup:
        (props, { slots }) =>
        () =>
          props.show
            ? h('section', { role: 'dialog' }, [slots.default?.(), slots.footer?.()])
            : null
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

beforeEach(() => {
  preferences = createSidebarPreferences({
    storage: { getItem: () => null, setItem: vi.fn() }
  })
})

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
})

async function render(props = {}, addingGroup = null, dragKey = null) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: navigationItems
      .filter((item) => item.to)
      .map((item) => ({
        path: item.to,
        component: { render: () => null }
      }))
  })
  await router.push('/')
  const component =
    addingGroup || dragKey
      ? {
          ...AppSidebar,
          setup(props, context) {
            const state = AppSidebar.setup(props, context)
            state.addingGroup.value = addingGroup
            state.dragKey.value = dragKey
            return state
          }
        }
      : AppSidebar
  const app = createSSRApp(component, props)
  app.use(router)
  return renderToString(app)
}

function mount(props = {}) {
  const renderer = createRenderer({
    createElement: () => ({}),
    createText: () => ({}),
    createComment: () => ({}),
    setText() {},
    setElementText() {},
    patchProp() {},
    insert() {},
    remove() {},
    parentNode: () => null,
    nextSibling: () => null
  })
  // Template bindings are checked through SSR; this renderer exercises their real handlers.
  const app = renderer.createApp({ ...AppSidebar, render: () => null }, props)
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount({})
  mounted.push(app)
  return app._instance.setupState
}

const pageSortStart = (id) => ({ item: { dataset: { sidebarPlacement: id } } })
const groupSortStart = (key) => ({ item: { dataset: { sidebarGroup: key } } })
const pageMove = (element, group) => ({
  draggedContext: { element },
  to: { dataset: { sidebarItemsGroup: group } }
})

const groupItems = (key) =>
  preferences.visibleSections.value.find((section) => section.key === key).items
const collapseTag = (html, group) =>
  html
    .split(`data-sidebar-group="${group}"`)[1]
    ?.split('data-sidebar-group="')[0]
    ?.match(/<div\b[^>]*class="app-sidebar__collapse"[^>]*>/)?.[0]

describe('自定义侧边栏', () => {
  it('marks the mobile drawer explicitly and keeps menus off the fixed footer', async () => {
    const desktop = await render()
    expect(desktop).not.toContain('app-sidebar--mobile')
    const mobile = await render({ mobile: true })
    expect(mobile).toMatch(/<nav\b[^>]*class="[^"]*app-sidebar--mobile/)
    const body = mobile.slice(0, mobile.indexOf('class="app-sidebar__footer"'))
    for (const item of navigationItems.filter((item) => !item.footer)) {
      expect(body).toContain(`aria-label="管理${item.label}"`)
    }
    expect(body).toContain('aria-label="管理常用分组"')
    const footer = mobile.slice(mobile.indexOf('class="app-sidebar__footer"'))
    expect(footer).not.toContain('app-sidebar__menu')
  })

  it('keeps navigation available after loading fails, blocks edits, and retries the saved layout', async () => {
    const transport = {
      get: vi
        .fn()
        .mockRejectedValueOnce(new Error('offline'))
        .mockResolvedValueOnce({ data: { sidebar: null } }),
      put: vi.fn().mockResolvedValue({})
    }
    preferences = createSidebarPreferences({
      transport,
      storage: { getItem: () => null, setItem: vi.fn() }
    })
    await preferences.initialize()
    const component = mount()
    const original = JSON.stringify(preferences.state.value)
    const log = groupItems('daily').find((item) => item.key === 'log')
    component.startPageSort(pageSortStart(log.id))
    component.selectItemAction('pin', log)
    component.selectGroupAction('dissolve', 'daily')
    expect(component.canMovePage(pageMove(log, 'reports'))).toBe(false)
    expect(component.dragKey).toBeNull()
    expect(JSON.stringify(preferences.state.value)).toBe(original)
    const html = await render()
    expect(html).toContain('布局加载失败')
    expect(html).toContain('aria-label="重新加载侧边栏布局"')
    expect(html).toContain('href="/"')
    expect(html).toMatch(/aria-label="管理运行日志"[^>]*disabled/)
    expect(await component.retryPreferences()).toBe(true)
    expect(transport.get).toHaveBeenCalledTimes(2)
    expect(preferences.initialized.value).toBe(true)
    expect(preferences.persistenceError.value).toBe(false)
    expect(await render()).not.toContain('布局加载失败')
  })

  it('renders group collapse controls and leaves rail destinations reachable', async () => {
    preferences.toggleGroup('reports')
    const expanded = await render()
    expect(expanded).toMatch(/id="[^"]+-reports"[^>]*aria-expanded="false"/)
    expect(collapseTag(expanded, 'reports')).toContain('style="display:none;"')
    expect(collapseTag(expanded, 'reports')).toContain(' inert')
    expect(collapseTag(expanded, 'reports')).toContain('aria-hidden="true"')
    expect(expanded).toContain('href="/record/line"')
    const rail = await render({ collapsed: true })
    expect(rail).toMatch(/id="[^"]+-reports"[^>]*aria-expanded="true"/)
    for (const section of preferences.visibleSections.value) {
      expect(collapseTag(rail, section.key)).not.toContain('display:none;')
      expect(collapseTag(rail, section.key)).not.toContain(' inert')
      expect(collapseTag(rail, section.key)).not.toContain('aria-hidden="true"')
      for (const item of section.items) {
        expect(rail).toContain(`href="${item.to ?? item.href}"`)
      }
    }
    expect(rail).not.toMatch(/\sdraggable="true"/)
    expect(rail).not.toContain('app-sidebar__group-add')
  })

  it('keeps customization reachable when all catalog entries are hidden', async () => {
    for (const item of preferences.catalog.value) preferences.setVisible(item.key, false)
    const html = await render()
    expect(html.slice(0, html.indexOf('class="app-sidebar__footer"'))).not.toContain('<a ')
    expect(html).not.toContain('aria-haspopup="dialog"')
    for (const title of ['常用', '数据报表', '资料']) {
      expect(html).toContain(`aria-label="管理${title}分组"`)
    }
    expect(html).not.toContain('app-sidebar__group-add')
    const component = mount()
    expect(component.groupOptions('daily')).toContainEqual({ key: 'add', label: '添加页面' })
  })

  it('keeps the two footer entries fixed without group controls, menus or dragging', async () => {
    for (const item of preferences.catalog.value) {
      expect(preferences.moveItem(item.key, 'footer')).toBe(false)
    }
    const html = await render()
    const footer = html.slice(html.indexOf('class="app-sidebar__footer"'))
    expect(footer.match(/data-sidebar-item=/g)).toHaveLength(2)
    expect(html).toContain('aria-label="管理常用分组"')
    expect(footer).not.toContain('app-sidebar__heading')
    expect(footer).not.toContain('app-sidebar__menu')
    expect(footer).not.toContain('draggable="true"')
    expect(footer).not.toContain('data-sidebar-group=')
    expect(footer.indexOf('data-sidebar-item="chat"')).toBeLessThan(
      footer.indexOf('data-sidebar-item="mower-settings"')
    )
    const component = mount()
    for (const key of ['chat', 'mower-settings']) {
      component.startPageSort(pageSortStart(key))
      expect(component.dragKey).toBeNull()
    }
  })

  it('fixes pinned entries above the scrolling groups and keeps the footer below them', async () => {
    preferences.setPinned('record-depot', true)
    preferences.setVisible('record-line', false)
    const html = await render()
    expect(html.indexOf('data-sidebar-group="pinned"')).toBeLessThan(html.indexOf('<scroll-region'))
    expect(html.indexOf('data-sidebar-group="pinned"')).toBeLessThan(
      html.indexOf('class="app-sidebar__footer"')
    )
    expect(html.match(/href="\/record\/depot"/g)).toHaveLength(1)
    expect(html).not.toContain('href="/record/line"')
  })

  it('opens both fixed external page copies safely in separate groups', async () => {
    const group = preferences.addGroup('常用工具')
    preferences.addEntry('arkntools', group)
    const html = await render()
    expect(html).toContain('常用工具')
    expect(html).toMatch(
      /<a[^>]*href="https:\/\/arkntools.app\/"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/
    )
    expect(html.match(/href="https:\/\/arkntools.app\/"/g)).toHaveLength(2)
  })

  it('drags entries directly without showing handles or repeated empty group hints', async () => {
    const html = await render()
    expect(html.match(/<a\b[^>]*href="\/"[^>]*>/)?.[0]).toContain('draggable="false"')
    expect(html).toMatch(/<button[^>]*draggable="false"[^>]*title="Mower AI 助手"/)
    expect(html).not.toContain('app-sidebar__drag')
    expect(html).not.toContain('拖动入口到这里')
    expect(html).not.toContain('data-sidebar-group="pinned"')
    expect(await render()).not.toContain('data-sidebar-group="pinned"')
    expect(html).toContain('aria-label="管理数据报表分组"')
    expect(html).toContain('aria-label="管理常用分组"')
    expect(html).not.toContain('app-sidebar__group-add')
    expect(html).not.toContain('app-sidebar__tools')
    expect(html).not.toContain('aria-label="新增分组"')
    expect(await render({ collapsed: true })).not.toContain('aria-label="管理常用分组"')
    expect(mount().dragOptions).toMatchObject({
      forceFallback: true,
      fallbackOnBody: true,
      animation: 180,
      fallbackTolerance: 8,
      preventOnFilter: false
    })
  })

  it('saves the completed report order and clears the active drag', () => {
    const component = mount()
    const element = groupItems('reports').find((item) => item.key === 'record-line')
    component.startPageSort(pageSortStart(element.id))
    expect(component.dragKey).toBe(element.id)
    component.onPageSort({ moved: { element, newIndex: 2 } }, 'reports')
    component.endDrag()
    expect(
      groupItems('reports')
        .slice(0, 4)
        .map((item) => item.key)
    ).toEqual(['record-pie', 'record-report', 'record-line', 'record-depot'])
    expect(component.dragKey).toBeNull()
  })

  it('moves entries across groups and pins while rejecting the fixed footer as a drop target', () => {
    const component = mount()
    const group = preferences.addGroup('我的分组')
    const element = groupItems('daily').find((item) => item.key === 'log')
    component.startPageSort(pageSortStart(element.id))
    component.onPageSort({ moved: { element, newIndex: 1 } }, 'daily')
    expect(
      groupItems('daily')
        .slice(0, 3)
        .map((item) => item.key)
    ).toEqual(['task-settings', 'log', 'plan'])
    expect(component.canMovePage(pageMove(element, group))).toBe(true)
    component.onPageSort({ added: { element, newIndex: 0 } }, group)
    const afterTargetAdded = JSON.stringify(preferences.state.value)
    component.onPageSort({ removed: { element, oldIndex: 1 } }, 'daily')
    expect(JSON.stringify(preferences.state.value)).toBe(afterTargetAdded)
    expect(groupItems(group).map((item) => item.key)).toEqual(['log'])
    preferences.setPinned('record-depot', true)
    expect(component.canMovePage(pageMove(element, 'pinned'))).toBe(true)
    component.onPageSort({ added: { element, newIndex: 0 } }, 'pinned')
    expect(preferences.pinnedItems.value.map((item) => item.key)).toEqual(['log', 'record-depot'])
    expect(groupItems(group)).toHaveLength(0)
    expect(component.canMovePage(pageMove(element, 'footer'))).toBe(false)
    component.onPageSort({ added: { element, newIndex: 0 } }, 'footer')
    expect(preferences.pinnedItems.value.map((item) => item.key)).toEqual(['log', 'record-depot'])
    expect(preferences.footerItems.value.map((item) => item.key)).toEqual([
      'chat',
      'mower-settings'
    ])
  })

  it('ignores unrelated drags and cancels a drag without changing preferences', () => {
    const component = mount()
    const initial = JSON.stringify(preferences.state.value)
    expect(component.canMovePage({})).toBe(false)
    component.startPageSort(pageSortStart('unknown'))
    expect(component.dragKey).toBeNull()
    component.startPageSort(pageSortStart('log'))
    component.endDrag()
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
    expect(component.dragKey).toBeNull()
  })

  it.each([
    {
      source: 'reference',
      newIndex: 0,
      expected: ['reference', 'daily', 'reports']
    },
    {
      source: 'daily',
      newIndex: 1,
      expected: ['reports', 'daily', 'reference']
    }
  ])(
    'drags the $source group to index $newIndex without moving entries',
    ({ source, newIndex, expected }) => {
      const component = mount()
      const originalPlacements = JSON.stringify(preferences.state.value.placements)
      const element = preferences.state.value.groups.find((group) => group.key === source)
      component.startGroupSort(groupSortStart(source))
      expect(component.dragGroupKey).toBe(source)
      component.onGroupSort({ moved: { element, newIndex } })
      component.endDrag()
      expect(preferences.state.value.groups.map((group) => group.key)).toEqual(expected)
      expect(JSON.stringify(preferences.state.value.placements)).toBe(originalPlacements)
      expect(component.dragGroupKey).toBeNull()
    }
  )

  it('cancels group dragging and suppresses its trailing click without navigating or changing entries', () => {
    const navigate = vi.fn()
    const openChat = vi.fn()
    const component = mount({ onNavigate: navigate, onOpenChat: openChat })
    const initial = JSON.stringify(preferences.state.value)
    component.startGroupSort(groupSortStart('daily'))
    component.endDrag()
    const click = { preventDefault: vi.fn(), stopPropagation: vi.fn() }
    expect(component.guardDragClick(click)).toBe(true)
    expect(click.preventDefault).toHaveBeenCalledOnce()
    expect(click.stopPropagation).toHaveBeenCalledOnce()
    component.activate(
      groupItems('daily').find((item) => item.key === 'log'),
      {
        defaultPrevented: true
      }
    )
    expect(navigate).not.toHaveBeenCalled()
    expect(openChat).not.toHaveBeenCalled()
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
    expect(component.dragGroupKey).toBeNull()
    component.prepareActivation()
    expect(component.guardDragClick(click)).toBe(false)
  })

  it('ignores group drags from the icon rail and the fixed pinned area', () => {
    const rail = mount({ collapsed: true })
    rail.startGroupSort(groupSortStart('daily'))
    expect(rail.dragGroupKey).toBeNull()
    const component = mount()
    component.startGroupSort(groupSortStart('pinned'))
    component.startGroupSort(groupSortStart('footer'))
    expect(component.dragGroupKey).toBeNull()
  })

  it('keeps pinned pages fixed after sorting ordinary groups', async () => {
    preferences.setPinned('record-depot', true)
    const component = mount()
    const pinned = component.pinnedSection
    const element = component.sidebarSections.find((section) => section.key === 'reference')
    expect(component.canMoveGroup({ draggedContext: { element: pinned } })).toBe(false)
    expect(
      component.canMoveGroup({ draggedContext: { element }, relatedContext: { element: pinned } })
    ).toBe(false)
    component.onGroupSort({ moved: { element: pinned, newIndex: 2 } })
    component.onGroupSort({ moved: { element, newIndex: 0 } })
    expect(preferences.state.value.groups.map((group) => group.key)).toEqual([
      'reference',
      'daily',
      'reports'
    ])
    const html = await render()
    expect(html.indexOf('data-sidebar-group="pinned"')).toBeLessThan(
      html.indexOf('data-sidebar-group="reference"')
    )
    expect(preferences.pinnedItems.value.map((item) => item.key)).toEqual(['record-depot'])
  })

  it('temporarily opens folded groups for a page drag without saving their collapse state', async () => {
    preferences.toggleGroup('reports')
    const initial = JSON.stringify(preferences.state.value)
    const component = mount()
    component.startPageSort(pageSortStart('log'))
    const duringDrag = await render({}, null, 'log')
    expect(duringDrag).toMatch(/id="[^"]+-reports"[^>]*aria-expanded="true"/)
    expect(collapseTag(duringDrag, 'reports')).not.toContain('display:none;')
    expect(collapseTag(duringDrag, 'reports')).not.toContain(' inert')
    expect(collapseTag(duringDrag, 'reports')).not.toContain('aria-hidden="true"')
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
    component.endDrag()
    expect(collapseTag(await render(), 'reports')).toContain('style="display:none;"')
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
  })

  it('rejects moving a page copy into an area that already contains that page', () => {
    preferences.addEntry('log', 'reports')
    const component = mount()
    const original = groupItems('daily').find((item) => item.key === 'log')
    const copy = groupItems('reports').find((item) => item.key === 'log')
    expect(component.canMovePage(pageMove(copy, 'reports'))).toBe(true)
    expect(component.canMovePage(pageMove(copy, 'daily'))).toBe(false)
    component.onPageSort({ added: { element: copy, newIndex: 0 } }, 'daily')
    expect(groupItems('daily')[0].id).toBe(original.id)
    expect(groupItems('reports').at(-1).id).toBe(copy.id)
    preferences.setVisible(original.id, false)
    expect(component.canMovePage(pageMove(copy, 'daily'))).toBe(false)
    preferences.setPinned(original.id, true)
    expect(component.canMovePage(pageMove(copy, 'pinned'))).toBe(false)
  })

  it('preserves the fixed assistant action alongside movable page entries', () => {
    const openChat = vi.fn()
    const navigate = vi.fn()
    const component = mount({ onOpenChat: openChat, onNavigate: navigate })
    expect(preferences.moveItem('chat', 'daily')).toBe(false)
    component.activate(preferences.footerItems.value.find((item) => item.key === 'chat'))
    component.activate(groupItems('daily').find((item) => item.key === 'log'))
    expect(openChat).toHaveBeenCalledOnce()
    expect(navigate).toHaveBeenCalledOnce()
  })

  it.each(['log', 'arkntools'])(
    'suppresses the click after dragging %s and allows the next deliberate click',
    (key) => {
      const navigate = vi.fn()
      const openChat = vi.fn()
      const component = mount({ onNavigate: navigate, onOpenChat: openChat })
      const item = preferences.visibleSections.value
        .flatMap((group) => group.items)
        .find((entry) => entry.key === key)
      expect(item).toBeDefined()
      component.startPageSort(pageSortStart(item.id))
      component.endDrag()
      const click = { preventDefault: vi.fn(), stopPropagation: vi.fn() }
      expect(component.guardDragClick(click)).toBe(true)
      expect(click.preventDefault).toHaveBeenCalledOnce()
      expect(click.stopPropagation).toHaveBeenCalledOnce()
      component.activate(item, { defaultPrevented: true })
      expect(navigate).not.toHaveBeenCalled()
      expect(openChat).not.toHaveBeenCalled()
      component.prepareActivation()
      component.activate(item, { defaultPrevented: false })
      expect(item.action === 'chat' ? openChat : navigate).toHaveBeenCalledOnce()
    }
  )

  it('does not swallow a fresh pointer or keyboard activation when a drag dispatched no click', () => {
    const navigate = vi.fn()
    const component = mount({ onNavigate: navigate })
    const item = groupItems('daily').find((entry) => entry.key === 'log')
    component.startPageSort(pageSortStart(item.id))
    component.endDrag()
    component.prepareActivation()
    const click = { preventDefault: vi.fn(), stopPropagation: vi.fn() }
    expect(component.guardDragClick(click)).toBe(false)
    component.activate(item, click)
    expect(click.preventDefault).not.toHaveBeenCalled()
    expect(navigate).toHaveBeenCalledOnce()
  })

  it('ignores drag starts on the icon rail', () => {
    const component = mount({ collapsed: true })
    const element = groupItems('daily').find((item) => item.key === 'log')
    component.startPageSort(pageSortStart(element.id))
    component.onPageSort({ moved: { element, newIndex: 1 } }, 'daily')
    expect(component.canMovePage(pageMove(element, 'reports'))).toBe(false)
    expect(component.dragKey).toBeNull()
    expect(component.draggedItem).toBeNull()
    expect(groupItems('daily')[0].id).toBe(element.id)
  })

  it('opens group creation and renaming in the shared editor without changing preferences', () => {
    const customize = vi.fn()
    const component = mount({ onCustomize: customize })
    const initial = JSON.stringify(preferences.state.value)
    component.selectGroupAction('new', 'daily')
    expect(customize).toHaveBeenLastCalledWith({ action: 'new-group', afterKey: 'daily' })
    component.selectGroupAction('rename', 'reports')
    expect(customize).toHaveBeenLastCalledWith({ action: 'rename-group', groupKey: 'reports' })
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
  })

  it('requests the shared editor while retaining ordinary sidebar collapse preferences', async () => {
    preferences.toggleGroup('reports')
    const customize = vi.fn()
    const component = mount({ onCustomize: customize })
    const initial = JSON.stringify(preferences.state.value)
    component.startEditing()
    expect(customize).toHaveBeenCalledOnce()
    const html = await render()
    expect(html).not.toContain('完成编辑')
    expect(html).not.toContain('app-sidebar__editing-bar')
    expect(html).not.toContain('role="dialog"')
    expect(collapseTag(html, 'reports')).toContain('display:none;')
    expect(JSON.stringify(preferences.state.value)).toBe(initial)
  })

  it('requests the editor from the icon rail without navigation', () => {
    const customize = vi.fn()
    const navigate = vi.fn()
    const openChat = vi.fn()
    const component = mount({
      collapsed: true,
      onCustomize: customize,
      onNavigate: navigate,
      onOpenChat: openChat
    })
    component.startEditing()
    expect(customize).toHaveBeenCalledOnce()
    expect(navigate).not.toHaveBeenCalled()
    expect(openChat).not.toHaveBeenCalled()
  })

  it('keeps only pinning and removing in page menus while sorting handles order and groups', () => {
    const navigate = vi.fn()
    const openChat = vi.fn()
    const component = mount({ onNavigate: navigate, onOpenChat: openChat })
    const item = groupItems('daily').find((entry) => entry.key === 'log')
    const act = (action) => component.selectItemAction(action, item)
    expect(component.itemOptions(item)).toEqual([
      { key: 'pin', label: '置顶', disabled: false },
      { type: 'divider', key: 'page-remove-divider' },
      { key: 'remove', label: '从此分组移除' }
    ])
    component.onPageSort({ moved: { element: item, newIndex: 1 } }, 'daily')
    expect(
      groupItems('daily')
        .slice(0, 2)
        .map((entry) => entry.key)
    ).toEqual(['task-settings', 'log'])
    component.onPageSort({ moved: { element: item, newIndex: 0 } }, 'daily')
    expect(groupItems('daily')[0].key).toBe('log')
    act('pin')
    expect(preferences.pinnedItems.value.map((entry) => entry.key)).toEqual(['log'])
    expect(component.itemOptions(item)[0].label).toBe('取消置顶')
    act('pin')
    expect(groupItems('daily')[0].key).toBe('log')
    component.onPageSort(
      { added: { element: item, newIndex: groupItems('reports').length } },
      'reports'
    )
    expect(groupItems('reports').at(-1).key).toBe('log')
    act('remove')
    expect(groupItems('reports').map((entry) => entry.key)).not.toContain('log')
    expect(navigate).not.toHaveBeenCalled()
    expect(openChat).not.toHaveBeenCalled()
  })

  it('removes only the current page copy while keeping the other group copy and catalog entry', () => {
    preferences.addEntry('log', 'reports')
    const component = mount()
    const copy = groupItems('reports').find((entry) => entry.key === 'log')
    expect(component.itemOptions(copy).find((option) => option.key === 'remove')).toEqual({
      key: 'remove',
      label: '从此分组移除'
    })
    component.selectItemAction('remove', copy)
    expect(groupItems('daily')[0].key).toBe('log')
    expect(groupItems('reports').some((item) => item.key === 'log')).toBe(false)
    expect(preferences.catalog.value.some((item) => item.key === 'log')).toBe(true)
  })

  it('drags, orders and pins a selected copy by id while leaving the original copy in place', () => {
    preferences.addEntry('log', 'reports')
    const component = mount()
    const copy = groupItems('reports').find((entry) => entry.key === 'log')
    const original = groupItems('daily').find((entry) => entry.key === 'log')
    component.startPageSort(pageSortStart(copy.id))
    expect(component.dragKey).toBe(copy.id)
    component.onPageSort({ moved: { element: copy, newIndex: 0 } }, 'reports')
    component.endDrag()
    expect(groupItems('reports')[0].id).toBe(copy.id)
    component.onPageSort({ moved: { element: copy, newIndex: 1 } }, 'reports')
    expect(
      groupItems('reports')
        .slice(0, 2)
        .map((item) => item.id)
    ).toEqual(['record-line', copy.id])
    component.selectItemAction('pin', copy)
    expect(preferences.pinnedItems.value.map((item) => item.id)).toEqual([copy.id])
    expect(component.itemOptions(original)[0].disabled).toBe(true)
    component.selectItemAction('pin', copy)
    component.onPageSort(
      { added: { element: copy, newIndex: groupItems('reference').length } },
      'reference'
    )
    expect(groupItems('reference').at(-1).id).toBe(copy.id)
    expect(groupItems('daily')[0].id).toBe(original.id)
    expect(preferences.state.value.placements.filter((item) => item.key === 'log')).toHaveLength(2)
  })

  it('opens the page dialog from a group menu and clears its target on close or group deletion', async () => {
    const navigate = vi.fn()
    const component = mount({ onNavigate: navigate })
    component.selectGroupAction('add', 'reports')
    expect(component.addingGroup).toBe('reports')
    expect(await render()).not.toContain('role="dialog"')
    const dialog = await render({}, 'reports')
    expect(dialog).toContain('role="dialog"')
    expect(dialog).toContain('aria-label="搜索页面"')
    expect(dialog).toContain('data-page-key="log"')
    component.finishEditing()
    expect(component.addingGroup).toBeNull()
    const group = preferences.addGroup('临时分组')
    component.selectGroupAction('add', group)
    preferences.removeGroup(group)
    await nextTick()
    expect(component.addingGroup).toBeNull()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('requires explicit dissolution confirmation and leaves every page independently visible', async () => {
    const component = mount()
    const options = component.groupOptions('daily')
    expect(
      options.filter((option) => option.type !== 'divider').map((option) => option.key)
    ).toEqual(['add', 'new', 'rename', 'dissolve-options'])
    expect(options.at(-1)).toEqual({
      key: 'dissolve-options',
      label: '取消分组',
      children: [{ key: 'dissolve', label: '确认取消分组，页面独立显示' }]
    })
    const oldKeys = groupItems('daily').map((item) => item.key)
    component.selectGroupAction('dissolve-options', 'daily')
    expect(preferences.state.value.groups.some((group) => group.key === 'daily')).toBe(true)
    component.selectGroupAction('dissolve', 'daily')
    expect(preferences.state.value.groups.some((group) => group.key === 'daily')).toBe(false)
    expect(preferences.standaloneItems.value.map((item) => item.key)).toEqual(oldKeys)
    for (const group of [...preferences.state.value.groups])
      component.selectGroupAction('dissolve', group.key)
    expect(preferences.state.value.groups).toEqual([])
    const html = await render()
    expect(html).toContain('data-sidebar-group="ungrouped"')
    expect(html).not.toContain('app-sidebar__heading-row')
    for (const item of preferences.catalog.value)
      expect(html).toContain('data-sidebar-item="' + item.key + '"')
  })

  it('distinguishes unpinning from removing the pinned copy when another copy already exists', () => {
    preferences.addEntry('log', 'pinned')
    const component = mount()
    const pinned = preferences.pinnedItems.value.find((item) => item.key === 'log')
    const options = component.itemOptions(pinned)
    expect(options[0]).toMatchObject({
      label: '取消置顶',
      disabled: true,
      description: '原位置已有此页面，可移除此处的入口。'
    })
    expect(options.at(-1).label).toBe('移除此入口')
    component.selectItemAction('remove', pinned)
    expect(preferences.pinnedItems.value.some((item) => item.key === 'log')).toBe(false)
    expect(groupItems('daily').some((item) => item.key === 'log')).toBe(true)
  })

  it('sorts independent pages and moves them into groups without moving other copies', () => {
    preferences.moveItem('log', 'ungrouped')
    preferences.addEntry('log', 'reports')
    const component = mount()
    const log = preferences.standaloneItems.value.find((item) => item.key === 'log')
    expect(component.itemOptions(log).at(-1).label).toBe('从侧边栏移除')
    expect(component.canMovePage(pageMove(log, 'ungrouped'))).toBe(true)
    expect(component.canMovePage(pageMove(log, 'reports'))).toBe(false)
    component.onPageSort({ added: { element: log, newIndex: 0 } }, 'reference')
    expect(groupItems('reference')[0].id).toBe(log.id)
    expect(groupItems('reports').some((item) => item.key === 'log')).toBe(true)
    component.startPageSort(pageSortStart(log.id))
    component.onPageSort({ added: { element: log, newIndex: 0 } }, 'ungrouped')
    expect(preferences.standaloneItems.value[0].id).toBe(log.id)
    component.endDrag()
    const reference = component.sidebarSections.find((section) => section.key === 'reference')
    expect(
      component.canMoveGroup({
        draggedContext: { element: reference },
        relatedContext: { element: component.sidebarSections[0] }
      })
    ).toBe(false)
    component.onGroupSort({ moved: { element: reference, newIndex: 1 } })
    expect(preferences.state.value.groups[0].key).toBe('reference')
  })
})
