import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRenderer, createSSRApp, nextTick, reactive, ref, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { routeLocationKey } from 'vue-router'
import SettingsLayout from './SettingsLayout.vue'
import SettingsSidebar from './SettingsSidebar.vue'
import { createSettingsNavigation, settingsNavigationKey } from '@/composables/settingsNavigation'

const sections = [
  { id: 'interface', title: '界面与窗口' },
  { id: 'notifications', title: '通知与助手' }
]
const layoutProps = { title: 'Mower 设置', navLabel: '设置分类', sections }
const mounted = []

function mountLayout(navigation, route) {
  const renderer = createRenderer({
    createElement: () => ({ children: [] }),
    createText: () => ({}),
    createComment: () => ({}),
    setText: () => {},
    setElementText: () => {},
    parentNode: (node) => node.parent,
    nextSibling: () => null,
    patchProp: () => {},
    insert(node, parent) {
      node.parent = parent
      parent.children.push(node)
    },
    remove: () => {}
  })
  const app = renderer.createApp({ ...SettingsLayout, render: () => null }, layoutProps)
  app.provide(ssrContextKey, { modules: new Set() })
  app.provide(settingsNavigationKey, navigation)
  if (route) app.provide(routeLocationKey, route)
  app.mount({ children: [] })
  mounted.push(app)
  return app
}

async function renderSidebar(navigation) {
  const app = createSSRApp(SettingsSidebar)
  app.provide(settingsNavigationKey, navigation)
  return renderToString(app)
}

function registerPage(navigation) {
  const page = {
    ...layoutProps,
    query: ref(''),
    results: ref([]),
    active: ref('interface'),
    jump: vi.fn(),
    reveal: vi.fn()
  }
  navigation.register(page)
  return page
}

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('settings sidebar', () => {
  it('shows the Mower categories without a second settings-page selector', async () => {
    const navigation = createSettingsNavigation()
    registerPage(navigation)
    const html = await renderSidebar(navigation)
    expect(html).toContain('返回')
    expect(html).toContain('搜索Mower 设置')
    expect(html).not.toContain('href="/mowersettings"')
    expect(html).not.toContain('href="/maasettings"')
    expect(html).not.toContain('aria-label="设置页面"')
    expect(html).toContain('href="#interface"')
    expect(html).toContain('界面与窗口')
  })

  it('keeps search and categories inside the settings dialog without a back button', async () => {
    const navigation = createSettingsNavigation()
    registerPage(navigation)
    const app = createSSRApp(SettingsSidebar, { embedded: true })
    app.provide(settingsNavigationKey, navigation)
    const html = await renderToString(app)
    expect(html).toContain('role="search"')
    expect(html).toContain('搜索Mower 设置')
    expect(html).toContain('href="#interface"')
    expect(html).toContain('界面与窗口')
    expect(html).toContain('href="#notifications"')
    expect(html).toContain('通知与助手')
    expect(html).not.toContain('settings-sidebar-back')
    expect(html).not.toContain('返回')
  })

  it('renders search results in place of the category list', async () => {
    const navigation = createSettingsNavigation()
    const page = registerPage(navigation)
    page.query.value = '邮件'
    page.results.value = [{ key: 'mail', label: '邮件提醒', path: '通知与助手' }]
    const html = await renderSidebar(navigation)
    expect(html).toContain('邮件提醒')
    expect(html).not.toContain('href="#interface"')
  })

  it('removes the inner sidebar when the outer shell owns navigation', async () => {
    const navigation = createSettingsNavigation()
    const app = createSSRApp(SettingsLayout, layoutProps)
    app.provide(settingsNavigationKey, navigation)
    const html = await renderToString(app)
    expect(html).not.toContain('class="settings-aside"')
    expect(html).toContain('<h1>界面与窗口</h1>')
    expect(navigation.current.value.sections).toEqual(sections)
    expect(navigation.current.value.query.value).toBe('')
  })

  it('keeps the standalone settings layout usable without the shell', async () => {
    const html = await renderToString(createSSRApp(SettingsLayout, layoutProps))
    expect(html).toContain('class="settings-aside"')
    expect(html).toContain('搜索Mower 设置')
  })

  it('finds update summaries and collapsed maintenance entries alongside form labels', async () => {
    const fields = [
      ['当前版本', '4.1.6-preview'],
      ['从本地安装包更新', '选择安装包'],
      [null, '自动更新']
    ].map(([label, textContent]) => ({
      textContent,
      getAttribute: () => label,
      querySelector: () => null,
      closest: () => null
    }))
    const card = {
      querySelector: () => ({ textContent: '软件更新', querySelector: () => null }),
      querySelectorAll: () => fields
    }
    const frame = { scrollTop: 0 }
    const section = { parentElement: frame, querySelectorAll: () => [card] }
    vi.stubGlobal('document', { getElementById: () => section })
    vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
    const navigation = createSettingsNavigation()
    mountLayout(navigation)
    await nextTick()
    const page = navigation.current.value
    for (const label of ['当前版本', '从本地安装包更新', '自动更新']) {
      page.query.value = ''
      await nextTick()
      page.query.value = label
      await nextTick()
      expect(
        page.results.value.some((entry) => entry.label === label && entry.path.includes('软件更新'))
      ).toBe(true)
    }
  })

  it('finds theme choices and conditional field metadata across categories', async () => {
    const theme = {
      textContent: '显示主题',
      getAttribute: () => null,
      querySelector: () => null,
      closest: () => theme,
      querySelectorAll: () => [
        { textContent: '亮色' },
        { textContent: '暗色' },
        { textContent: '跟随系统' }
      ]
    }
    const themeCard = {
      getAttribute: () => null,
      querySelector: () => ({ textContent: '常规', querySelector: () => null }),
      querySelectorAll: () => [theme]
    }
    const mailCard = {
      getAttribute: (name) =>
        name === 'data-settings-keywords' ? 'SMTP服务器 SSL/TLS STARTTLS 端口号 自定义邮箱' : null,
      querySelector: () => ({ textContent: '邮件提醒', querySelector: () => null }),
      querySelectorAll: () => []
    }
    const frame = { scrollTop: 0 }
    vi.stubGlobal('document', {
      getElementById: (id) => ({
        parentElement: frame,
        querySelectorAll: () => (id === 'interface' ? [themeCard] : [mailCard])
      })
    })
    vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
    const navigation = createSettingsNavigation()
    mountLayout(navigation)
    await nextTick()
    const page = navigation.current.value
    for (const [query, label] of [
      ['深色', '显示主题'],
      ['SMTP', '邮件提醒'],
      ['通知 smtp', '邮件提醒']
    ]) {
      page.query.value = query
      await nextTick()
      expect(page.results.value.some((entry) => entry.label === label)).toBe(true)
      expect(page.results.value[0].label).toBe(label)
    }
  })

  it('refreshes searchable labels when the query changes after conditional content renders', async () => {
    const fields = []
    const card = {
      getAttribute: () => null,
      querySelector: () => ({ textContent: '邮件提醒', querySelector: () => null }),
      querySelectorAll: () => fields
    }
    const frame = { scrollTop: 0 }
    vi.stubGlobal('document', {
      getElementById: () => ({ parentElement: frame, querySelectorAll: () => [card] })
    })
    vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
    const navigation = createSettingsNavigation()
    mountLayout(navigation)
    await nextTick()
    const page = navigation.current.value
    page.query.value = '邮件'
    await nextTick()
    fields.push({
      textContent: '端口号',
      getAttribute: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      closest: () => null
    })
    page.query.value = '端口号'
    await nextTick()
    expect(page.results.value.some((entry) => entry.label === '端口号')).toBe(true)
  })

  it('updates an active search after asynchronously mounted fields arrive and releases its observer', async () => {
    let changed
    const observe = vi.fn()
    const disconnect = vi.fn()
    vi.stubGlobal(
      'MutationObserver',
      class {
        constructor(callback) {
          changed = callback
        }
        observe = observe
        disconnect = disconnect
      }
    )
    const fields = []
    const card = {
      getAttribute: () => null,
      querySelector: () => ({ textContent: '邮件提醒', querySelector: () => null }),
      querySelectorAll: () => fields
    }
    const frame = { scrollTop: 0 }
    const section = { parentElement: frame, querySelectorAll: () => [card] }
    vi.stubGlobal('document', { getElementById: () => section })
    vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
    const navigation = createSettingsNavigation()
    const app = mountLayout(navigation)
    await nextTick()
    await nextTick()
    const page = navigation.current.value
    page.query.value = '端口号'
    await nextTick()
    expect(page.results.value).toEqual([])
    fields.push({
      textContent: '端口号',
      getAttribute: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      closest: () => null
    })
    changed()
    await nextTick()
    expect(page.results.value[0].label).toBe('端口号')
    expect(observe).toHaveBeenCalledTimes(sections.length)
    app.unmount()
    mounted.splice(mounted.indexOf(app), 1)
    expect(disconnect).toHaveBeenCalledOnce()
  })

  it('switches categories and resets scroll after the new category is rendered', async () => {
    const frame = { scrollTop: 300 }
    const target = { parentElement: frame }
    const getElementById = vi.fn(() => target)
    vi.stubGlobal('document', { getElementById })
    vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
    const navigation = createSettingsNavigation()
    const app = createSSRApp(SettingsLayout, layoutProps)
    app.provide(settingsNavigationKey, navigation)
    await renderToString(app)

    const switching = navigation.current.value.jump('notifications')
    expect(navigation.current.value.active.value).toBe('notifications')
    expect(frame.scrollTop).toBe(300)
    expect(getElementById).not.toHaveBeenCalled()
    await switching
    expect(frame.scrollTop).toBe(0)
    expect(getElementById).toHaveBeenCalledWith('notifications')

    frame.scrollTop = 200
    await navigation.current.value.jump('unknown-category')
    expect(navigation.current.value.active.value).toBe('notifications')
    expect(frame.scrollTop).toBe(200)
  })

  it.each([1, 1.5])(
    'reveals a result in another category below the header at zoom %s',
    async (scale) => {
      vi.useFakeTimers()
      const frame = {
        offsetHeight: 600,
        scrollTop: 100,
        getBoundingClientRect: () => ({ top: 0, height: 600 * scale }),
        scrollTo: vi.fn()
      }
      const section = { id: 'notifications', parentElement: frame }
      const target = {
        closest: () => section,
        getBoundingClientRect: vi.fn(() => ({ top: 300 * scale })),
        classList: { remove: vi.fn(), add: vi.fn() },
        offsetWidth: 100
      }
      vi.stubGlobal('document', {
        getElementById: () => target,
        querySelector: (selector) =>
          selector === '.mobile-settings-header' ? { offsetHeight: 56 } : null
      })
      vi.stubGlobal('window', { matchMedia: () => ({ matches: true }) })
      vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
      const navigation = createSettingsNavigation()
      const app = createSSRApp(SettingsLayout, layoutProps)
      app.provide(settingsNavigationKey, navigation)
      await renderToString(app)
      const page = navigation.current.value
      page.query.value = '邮件'
      const revealing = page.reveal({ element: target })
      expect(page.active.value).toBe('notifications')
      expect(page.query.value).toBe('')
      expect(target.getBoundingClientRect).not.toHaveBeenCalled()
      expect(frame.scrollTo).not.toHaveBeenCalled()
      await revealing
      expect(frame.scrollTo).toHaveBeenCalledWith({ top: 328, behavior: 'auto' })
      expect(target.classList.add).toHaveBeenCalledWith('settings-search-hit')
    }
  )

  it('reveals a same-page hash target in its hidden category', async () => {
    vi.useFakeTimers()
    const frame = {
      offsetHeight: 600,
      scrollTop: 0,
      getBoundingClientRect: () => ({ top: 0, height: 600 }),
      scrollTo: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn()
    }
    const first = { id: 'interface', parentElement: frame }
    const notifications = { id: 'notifications', parentElement: frame }
    const target = {
      closest: () => notifications,
      getBoundingClientRect: () => ({ top: 300 })
    }
    vi.stubGlobal('document', {
      getElementById: (id) => ({ interface: first, 'mail-settings': target })[id] ?? null,
      querySelector: () => null
    })
    vi.stubGlobal('window', { matchMedia: () => ({ matches: true }) })
    vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
    const navigation = createSettingsNavigation()
    const route = reactive({ hash: '' })
    mountLayout(navigation, route)
    await nextTick()
    await nextTick()
    route.hash = '#mail-settings'
    await nextTick()
    await nextTick()
    expect(navigation.current.value.active.value).toBe('notifications')
    expect(frame.scrollTo).toHaveBeenCalledWith({ top: 284, behavior: 'auto' })
    expect(frame.addEventListener).not.toHaveBeenCalled()
  })

  it.each(['category switch', 'unmount'])(
    'cancels pending WebView scroll fallback after %s',
    async (action) => {
      vi.useFakeTimers()
      const frame = {
        offsetHeight: 600,
        scrollTop: 0,
        getBoundingClientRect: () => ({ top: 0, height: 600 }),
        scrollTo: vi.fn()
      }
      const first = { id: 'interface', parentElement: frame }
      const notifications = { id: 'notifications', parentElement: frame }
      const target = {
        closest: () => notifications,
        getBoundingClientRect: () => ({ top: 300 }),
        classList: { remove: vi.fn(), add: vi.fn() },
        offsetWidth: 100
      }
      vi.stubGlobal('document', {
        getElementById: (id) => ({ interface: first, notifications })[id] ?? null,
        querySelector: () => null
      })
      vi.stubGlobal('window', { matchMedia: () => ({ matches: false }) })
      vi.stubGlobal('getComputedStyle', () => ({ overflowY: 'auto' }))
      const navigation = createSettingsNavigation()
      const app = mountLayout(navigation)
      await nextTick()
      await nextTick()
      await navigation.current.value.reveal({ element: target })
      expect(frame.scrollTo).toHaveBeenCalledWith({ top: 284, behavior: 'smooth' })
      expect(frame.scrollTop).toBe(0)

      if (action === 'category switch') {
        await navigation.current.value.jump('interface')
        expect(navigation.current.value.active.value).toBe('interface')
      } else {
        app.unmount()
        mounted.splice(mounted.indexOf(app), 1)
      }
      vi.runAllTimers()
      expect(frame.scrollTop).toBe(0)
    }
  )

  it('releases page state on unmount and preserves a newer registration', async () => {
    vi.stubGlobal('document', { getElementById: () => null })
    const navigation = createSettingsNavigation()
    const app = mountLayout(navigation)
    await nextTick()
    expect(navigation.current.value.title).toBe('Mower 设置')
    const newer = registerPage(navigation)
    app.unmount()
    expect(navigation.current.value).toBe(newer)
  })
})
