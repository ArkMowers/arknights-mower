import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, nextTick, ssrContextKey } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import MobileTabBar from './MobileTabBar.vue'
import { routes } from '@/routes'

const mounted = []
afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
})

function stubRoutes(records) {
  return records.map(({ component, children, ...record }) => ({
    ...record,
    ...(component && { component: { render: () => null } }),
    ...(children && { children: stubRoutes(children) })
  }))
}

async function mount(path = '/') {
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
  const router = createRouter({ history: createMemoryHistory(), routes: stubRoutes(routes) })
  await router.push(path)
  const more = vi.fn()
  // Templates compile for SSR in Vitest; render checks live in NavigationShell.test.js.
  const app = renderer.createApp({ ...MobileTabBar, render: () => null }, { onMore: more })
  app.use(router)
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount({})
  mounted.push(app)
  return { component: app._instance.setupState, router, more }
}

describe('移动底栏页面选择', () => {
  it('opens the plan picker and ignores a stale dismissal from another key', async () => {
    const { component } = await mount()
    component.setTabOpen('plan', true)
    expect(component.openTab).toBe('plan')
    component.setTabOpen('stale-picker', false)
    expect(component.openTab).toBe('plan')
    component.setTabOpen('plan', false)
    expect(component.openTab).toBeNull()
  })

  it('closes the picker on page navigation and highlights secondary routes as their group', async () => {
    const { component, router } = await mount('/plan-editor')
    component.setTabOpen('plan', true)
    await router.push('/rescue-plan-editor')
    await nextTick()
    expect(component.openTab).toBeNull()
    expect(component.activeTab).toBe('plan')
    expect(component.moreActive).toBe(false)
    component.setTabOpen('plan', true)
    await router.push('/mowersettings')
    await nextTick()
    expect(component.openTab).toBeNull()
    expect(component.activeTab).toBe('mower-settings')
    expect(component.moreActive).toBe(false)
    await router.push('/maasettings')
    expect(router.currentRoute.value.path).toBe('/task-settings')
    expect(component.activeTab).toBe('task-settings')
    expect(component.moreActive).toBe(false)
  })

  it('closes the picker before opening More and keeps report navigation in its own group', async () => {
    const { component, router, more } = await mount()
    component.setTabOpen('plan', true)
    component.openMore()
    expect(more).toHaveBeenCalledOnce()
    expect(component.openTab).toBeNull()
    component.setTabOpen('plan', true)
    await router.push('/record/depot')
    await nextTick()
    expect(component.openTab).toBeNull()
    expect(component.activeTab).toBe('reports')
    expect(component.moreActive).toBe(false)
    component.setTabOpen('reports', true)
    await router.push('/record/log-schedule')
    expect(component.openTab).toBeNull()
    expect(component.activeTab).toBe('reports')
    await router.push('/doc')
    expect(component.activeTab).toBeUndefined()
    expect(component.moreActive).toBe(true)
  })
})
