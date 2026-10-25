import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  compile,
  computed,
  createRenderer,
  createSSRApp,
  defineComponent,
  effectScope,
  h,
  nextTick,
  provide,
  reactive,
  ref
} from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from './App.vue'
import { configProfilesKey } from '@/composables/configProfiles'
import { routes } from './routes'

const state = vi.hoisted(() => ({
  mounted: [],
  unmounted: [],
  client: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    defaults: { headers: { common: {} } },
    interceptors: { response: { use: vi.fn(), eject: vi.fn() } }
  },
  responseRejected: null,
  config: null,
  mower: null,
  plan: null,
  rescuePlan: null,
  resource: null,
  gui: null,
  loaded: null,
  loadUpdateNotice: vi.fn(),
  loadWatermark: vi.fn(async () => 'mower'),
  closeWindow: vi.fn(),
  route: null,
  router: null,
  shellMetadata: null,
  shellActive: false,
  shellConnected: null,
  sidebarInitialize: vi.fn(async () => true),
  sidebarFlush: vi.fn(async () => {}),
  settingsDialogClose: null,
  navigated: []
}))
vi.mock('axios', () => ({ default: state.client }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === 'axios' ? state.client : state.loaded),
  provide: vi.fn(),
  onMounted: (callback) => state.mounted.push(callback),
  onBeforeUnmount: (callback) => state.unmounted.push(callback)
}))
vi.mock('pinia', async (original) => {
  const { toRef } = await import('vue')
  return {
    ...(await original()),
    storeToRefs: (store) =>
      Object.fromEntries(Object.keys(store).map((key) => [key, toRef(store, key)]))
  }
})
vi.mock('vue-router', async (original) => ({
  ...(await original()),
  useRoute: () => state.route,
  useRouter: () => state.router
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('@/stores/plan', () => ({
  usePlanStore: () => state.plan,
  useRescuePlanStore: () => state.rescuePlan
}))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => state.resource }))
vi.mock('@/stores/gui', () => ({ useGuiStore: () => state.gui }))
vi.mock('@/stores/updateNotice', () => ({
  useUpdateNoticeStore: () => ({
    notice: { changelog: '' },
    loadUpdateNotice: state.loadUpdateNotice,
    ackUpdateNotice: vi.fn()
  })
}))
vi.mock('@/stores/watermark', () => ({
  usewatermarkStore: () => ({
    getwatermarkinfo: state.loadWatermark
  })
}))
vi.mock('@/composables/sidebarPreferences', () => ({
  useSidebarPreferences: () => ({
    initialize: state.sidebarInitialize,
    flush: state.sidebarFlush,
    initialized: { value: true },
    persistenceError: { value: false }
  })
}))
vi.mock('@/components/SidebarEditor.vue', () => ({
  default: defineComponent({
    props: ['show'],
    setup: (props) => () => (props.show ? h('section', { 'data-sidebar-editor': true }) : null)
  })
}))
vi.mock('@/window-shell/adapter.js', () => ({
  createWindowShellAdapter: () => ({
    close: state.closeWindow,
    metadata: state.shellMetadata,
    active: ref(state.shellActive),
    connected: state.shellConnected,
    capabilities: ref({ enabled: true, move: 'bridge', resize: 'native' }),
    state: { maximized: false },
    initialize: vi.fn(),
    dispose: vi.fn()
  }),
  formatWindowTitle: vi.fn(),
  formatEmulatorLabel: vi.fn()
}))
vi.mock('@/utils/modal-drag.js', () => ({ installModalDragging: () => vi.fn() }))
vi.mock('@/components/Feedback.vue', () => ({ default: {} }))
vi.mock('@/components/GlobalUpdateDrop.vue', () => ({ default: {} }))
vi.mock('@/components/WindowTitlebar.vue', () => ({
  default: defineComponent({
    props: ['theme'],
    setup: (props) => () =>
      h('header', {
        'data-window-theme': props.theme
      })
  })
}))
vi.mock('@/components/AppMenuBar.vue', () => ({
  default: defineComponent({
    props: {
      mode: String,
      active: { type: Boolean, default: true }
    },
    setup: (props) => () =>
      h('nav', {
        'data-app-menus': true,
        'data-menu-mode': props.mode,
        'data-menu-active': String(props.active)
      })
  })
}))
vi.mock('@/components/HelpDialog.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/ConfigProfilesController.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/AppSidebar.vue', () => ({
  default: defineComponent(() => () => h('nav', { 'data-sidebar': 'main' }))
}))
vi.mock('@/components/SettingsDialog.vue', () => ({
  default: defineComponent({
    props: ['show'],
    emits: ['close'],
    setup(props, { emit }) {
      state.settingsDialogClose = () => emit('close')
      return () => (props.show ? h('section', { 'data-settings-dialog': true }) : null)
    }
  })
}))
vi.mock('@/components/MobileTabBar.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/CrashRecoveryNotice.vue', () => ({ default: { render: () => null } }))
vi.mock('naive-ui', async (original) => {
  const wrapper = defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  })
  const overlay = defineComponent({
    props: ['show'],
    setup:
      (props, { slots }) =>
      () =>
        props.show ? h('aside', slots.default?.()) : null
  })
  return {
    ...(await original()),
    useMessage: () => ({ loading: vi.fn(), success: vi.fn(), info: vi.fn(), error: vi.fn() }),
    useNotification: () => ({ create: vi.fn(() => ({ destroy: vi.fn() })) }),
    ...Object.fromEntries(
      [
        'NConfigProvider',
        'NNotificationProvider',
        'NDialogProvider',
        'NMessageProvider',
        'NLoadingBarProvider',
        'NLayout',
        'NLayoutContent',
        'NLayoutFooter'
      ].map((name) => [name, wrapper])
    ),
    NConfigProvider: defineComponent({
      props: ['theme'],
      setup:
        (props, { slots }) =>
        () =>
          h('div', { 'data-page-theme': props.theme ? 'dark' : 'light' }, slots.default?.())
    }),
    NLayoutSider: defineComponent({
      props: ['width', 'collapsed'],
      setup:
        (props, { slots }) =>
        () =>
          h(
            'aside',
            { 'data-width': props.width, 'data-collapsed': String(props.collapsed) },
            slots.default?.()
          )
    }),
    NModal: overlay,
    NDrawer: overlay,
    NTooltip: defineComponent({
      inheritAttrs: false,
      setup:
        (_, { slots }) =>
        () =>
          slots.trigger?.()
    }),
    NGlobalStyle: { render: () => null },
    NWatermark: { render: () => null }
  }
})

function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('desktop page startup', () => {
  let scope
  let component
  beforeEach(() => {
    vi.clearAllMocks()
    state.mounted = []
    state.unmounted = []
    state.loaded = ref(false)
    state.loadUpdateNotice.mockResolvedValue({ should_show: false })
    state.loadWatermark.mockResolvedValue('mower')
    state.client.get.mockReset()
    state.client.patch.mockReset().mockResolvedValue({ data: {} })
    state.shellMetadata = { version: '', instanceName: '' }
    state.shellActive = false
    state.shellConnected = ref(false)
    state.route = reactive({ meta: {} })
    state.navigated = []
    state.settingsDialogClose = null
    state.router = {
      push: vi.fn(async () => {}),
      resolve: vi.fn((path) => ({
        path,
        fullPath: path,
        meta: {},
        matched: [{ components: { default: { render: () => null } } }]
      })),
      afterEach: (callback) => {
        state.navigated.push(callback)
        return () => state.navigated.splice(state.navigated.indexOf(callback), 1)
      }
    }
    state.client.post.mockResolvedValue({ data: {} })
    state.responseRejected = null
    state.client.interceptors.response.use.mockImplementation((_success, failure) => {
      state.responseRejected = failure
      return 17
    })
    state.client.get.mockResolvedValue({
      data: {
        ok: true,
        active_id: 'default',
        generation: '0',
        profiles: [{ id: 'default', name: '默认配置' }],
        groups: [],
        busy: false
      }
    })
    state.client.defaults.headers.common = {}
    state.config = reactive({
      start_automatically: true,
      resource_update_enable: true,
      resource_update_auto_update: true,
      theme: 'light',
      webview: { scale: 1 },
      simulator: {},
      adb: '',
      load_config: vi.fn(async () => {}),
      load_shop: vi.fn(async () => {}),
      load_item: vi.fn(async () => {}),
      build_advanced_settings: vi.fn()
    })
    state.plan = reactive({
      operators: [],
      set_advanced_settings_source: vi.fn(),
      load_plan: vi.fn(async () => {}),
      load_operators: vi.fn(async () => {})
    })
    state.rescuePlan = reactive({
      autosave_paused: false,
      wait_for_plan_save: vi.fn(async () => {})
    })
    state.mower = reactive({
      ws: null,
      running: false,
      log_lines: ['existing log'],
      auto_start_handled: false,
      desktop_startup_handled: false,
      updates_enabled: true,
      deployment: null,
      listen_ws: vi.fn(),
      get_running: vi.fn(async () => {
        state.mower.auto_start_handled = true
        state.mower.desktop_startup_handled = true
      })
    })
    state.resource = reactive({
      info: {},
      loadResourceJob: vi.fn(async () => false),
      loadResourceVersionLocal: vi.fn(async () => {}),
      loadResourceVersion: vi.fn(async () => ({ update_available: true })),
      installResource: vi.fn(async () => true)
    })
    state.gui = reactive({
      softwareVersionDisplay: 'version',
      watermarkVisible: true,
      loaded: true,
      loading: false,
      saving: false,
      error: '',
      displayDisabled: false,
      load: vi.fn(async () => true),
      setSoftwareVersionDisplay: vi.fn(async (value) => {
        state.gui.softwareVersionDisplay = value
        return true
      }),
      retry: vi.fn(async () => true)
    })
    vi.stubGlobal('window', {
      innerWidth: 1000,
      location: { search: '', port: '58100' },
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      scrollTo: vi.fn()
    })
    const rootClasses = new Set()
    vi.stubGlobal('document', {
      location: { search: '' },
      getAnimations: vi.fn(() => []),
      documentElement: {
        clientWidth: 1000,
        dataset: {},
        classList: {
          add: vi.fn((token) => rootClasses.add(token)),
          remove: vi.fn((token) => rootClasses.delete(token)),
          contains: (token) => rootClasses.has(token)
        },
        style: { setProperty: vi.fn() }
      }
    })
    vi.stubGlobal('sessionStorage', { getItem: vi.fn(() => null), removeItem: vi.fn() })
  })
  afterEach(() => {
    unmount()
    state.config.$dispose?.()
    state.plan.$dispose?.()
    vi.unstubAllGlobals()
  })
  function unmount() {
    state.unmounted.forEach((callback) => callback())
    state.unmounted = []
    scope?.stop()
  }
  async function mount() {
    state.mounted = []
    scope = effectScope()
    component = scope.run(() => App.setup({}, { expose: () => {} }))
    for (const callback of state.mounted) await callback()
    return component
  }

  it('shares the title-bar profile controller with settings actions', async () => {
    const component = await mount()
    expect(provide).toHaveBeenCalledWith(configProfilesKey, component.configProfiles)
  })

  it('closes a managed window directly without saving or applying a standalone exit choice', async () => {
    const savePreference = vi.fn()
    window.pywebview = {
      api: {
        get_close_preference: vi.fn(async () => ({
          managed: true,
          tray_enabled: false,
          choice: 'exit',
          remember: true
        })),
        set_close_preference: savePreference
      }
    }
    state.closeWindow.mockResolvedValue(true)
    await mount()
    state.client.post.mockClear()
    await expect(component.handleWindowControl('close')).resolves.toBe(true)
    expect(state.closeWindow).toHaveBeenCalledOnce()
    expect(component.closeModal.value).toBe(false)
    expect(savePreference).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  async function renderShell(component) {
    const app = createSSRApp({ ...App, setup: () => component })
    app.use(createPinia())
    app.config.globalProperties.$route = state.route
    app.component(
      'router-view',
      defineComponent({
        props: ['route'],
        setup: (props) => () => h('main', { 'data-content-route': props.route?.fullPath })
      })
    )
    const context = {}
    let html = await renderToString(app, context)
    for (const [target, content] of Object.entries(context.teleports || {})) {
      const host = new RegExp(`(<div id="${target.slice(1)}"[^>]*>)`)
      html = html.replace(host, (opening) => opening + content)
    }
    return html
  }

  it('toggles the mounted content watermark without reloading its version or application data', async () => {
    state.loadWatermark.mockResolvedValue('4.1.6-alpha.42')
    const component = await mount()
    const { descriptor } = parse(readFileSync(new URL('./App.vue', import.meta.url), 'utf8'))
    const findContent = (node) =>
      node.tag === 'n-layout-content' ? node : node.children?.map(findContent).find(Boolean)
    const content = findContent(descriptor.template.ast)
    expect(content).toBeTruthy()
    const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })
    const renderer = createRenderer({
      createElement: (tag) => node(tag),
      createText: (text) => node('#text', text),
      createComment: (text) => node('#comment', text),
      setText: (target, text) => (target.text = text),
      setElementText: (target, text) => (target.text = text),
      parentNode: (target) => target.parent,
      nextSibling: (target) => target.parent?.children[target.parent.children.indexOf(target) + 1],
      patchProp: (target, key, _previous, value) => (target.props[key] = value),
      insert(target, parent, anchor = null) {
        if (target.parent) target.parent.children.splice(target.parent.children.indexOf(target), 1)
        target.parent = parent
        const index = anchor ? parent.children.indexOf(anchor) : -1
        parent.children.splice(index < 0 ? parent.children.length : index, 0, target)
      },
      remove(target) {
        target.parent.children.splice(target.parent.children.indexOf(target), 1)
        target.parent = null
      }
    })
    const app = renderer.createApp({
      setup: () => ({ ...component }),
      render: compile(content.loc.source),
      components: {
        NLayoutContent: defineComponent(
          (_, { slots }) =>
            () =>
              h('div', slots.default?.())
        ),
        NWatermark: defineComponent({
          props: ['content'],
          setup: (props) => () => h('div', { 'data-version-watermark': props.content })
        }),
        RouterView: defineComponent(() => () => h('main', { 'data-current-page': true })),
        ...Object.fromEntries(
          [
            'ConfigSaveNotice',
            'CrashRecoveryNotice',
            'SettingsDialog',
            'ChatBot',
            'Feedback',
            'GlobalUpdateDrop',
            'NModal',
            'NButton'
          ].map((name) => [name, { render: () => null }])
        )
      }
    })
    const root = node('root')
    const all = (target = root) => [target, ...target.children.flatMap(all)]
    const watermark = () => all().find((target) => target.props['data-version-watermark'])
    const page = () => all().find((target) => target.props['data-current-page'])
    const requests = state.client.get.mock.calls.length
    window.location.reload = vi.fn()
    app.mount(root)
    try {
      const currentPage = page()
      expect(currentPage).toBeTruthy()
      expect(watermark()?.props['data-version-watermark']).toBe('4.1.6-alpha.42')

      state.gui.watermarkVisible = false
      await nextTick()
      expect(watermark()).toBeUndefined()
      expect(page()).toBe(currentPage)

      state.gui.watermarkVisible = true
      await nextTick()
      expect(watermark()?.props['data-version-watermark']).toBe('4.1.6-alpha.42')
      expect(page()).toBe(currentPage)
      expect(state.gui.load).toHaveBeenCalledOnce()
      expect(state.config.load_config).toHaveBeenCalledOnce()
      expect(state.loadWatermark).toHaveBeenCalledOnce()
      expect(state.client.get).toHaveBeenCalledTimes(requests)
      expect(window.location.reload).not.toHaveBeenCalled()
    } finally {
      app.unmount()
    }
  })

  async function useSettingsRouter(initial, logComponent = { render: () => null }) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'log', component: logComponent },
        { path: '/record/depot', component: { render: () => null } },
        {
          path: '/mowersettings',
          meta: { settings: true, settingsSidebar: true },
          component: { render: () => null }
        }
      ]
    })
    if (initial) await router.push(initial)
    state.router = router
    state.route = reactive({
      get meta() {
        return router.currentRoute.value.meta
      },
      get fullPath() {
        return router.currentRoute.value.fullPath
      }
    })
    return router
  }

  it('installs the configuration generation before loading stores and page data', async () => {
    state.config.load_config.mockImplementation(async () => {
      expect(state.client.defaults.headers.common['X-Mower-Config-Generation']).toBe('0')
      expect(state.client.get.mock.calls[0][0]).toContain('/config-profiles')
    })
    await mount()
    expect(state.config.load_config).toHaveBeenCalledOnce()
    expect(state.loaded.value).toBe(true)
  })

  it.each([false, true])(
    'changes settings, page and titlebar together without colour transitions (reduced motion %s)',
    async (reducedMotion) => {
      state.route.meta = { settings: true, settingsSidebar: true }
      window.matchMedia = vi.fn(() => ({ matches: reducedMotion }))
      const component = await mount()
      const root = document.documentElement
      const flushStyles = vi.fn(() => 1000)
      Object.defineProperty(root, 'offsetWidth', { get: flushStyles })

      state.config.theme = 'dark'
      expect(root.classList.add).toHaveBeenCalledWith('mower-theme-changing')
      expect(root.dataset.mowerTheme).toBe('dark')

      await nextTick()
      const html = await renderShell(component)
      expect(html).toContain('data-page-theme="dark"')
      expect(html).toContain('data-window-theme="dark"')
      expect(html).toContain('data-settings-dialog="true"')
      expect(flushStyles).toHaveBeenCalledOnce()
      expect(root.classList.remove).toHaveBeenCalledWith('mower-theme-changing')
      expect(flushStyles.mock.invocationCallOrder[0]).toBeLessThan(
        root.classList.remove.mock.invocationCallOrder[0]
      )
    }
  )

  it('follows the system in the page, menus and titlebar while retaining the system preference', async () => {
    let changed
    const media = {
      matches: true,
      addEventListener: vi.fn((_event, listener) => {
        changed = listener
      }),
      removeEventListener: vi.fn()
    }
    window.matchMedia = vi.fn((query) =>
      query === '(prefers-color-scheme: dark)' ? media : { matches: false }
    )
    state.config.theme = 'system'
    const component = await mount()
    expect(document.documentElement.dataset.mowerTheme).toBe('dark')
    let html = await renderShell(component)
    expect(html).toContain('data-page-theme="dark"')
    expect(html).toContain('data-window-theme="dark"')
    expect(component.appMenuProps.value.theme).toBe('dark')
    changed({ matches: false })
    await nextTick()
    html = await renderShell(component)
    expect(html).toContain('data-page-theme="light"')
    expect(html).toContain('data-window-theme="light"')
    expect(document.documentElement.dataset.mowerTheme).toBe('light')
    expect(state.config.theme).toBe('system')
    await component.setThemeWithTransition('dark')
    changed({ matches: false })
    expect(component.theme.value).toBe('dark')
    expect(state.config.theme).toBe('dark')
    await component.setThemeWithTransition('system')
    expect(component.theme.value).toBe('light')
    expect(state.config.theme).toBe('system')
    unmount()
    expect(media.removeEventListener).toHaveBeenCalledWith('change', changed)
  })

  it('keeps the latest requested theme during quick switches without fading the app', async () => {
    const component = await mount()
    let finishFade
    const provider = {
      animate: vi.fn(() => ({
        finished: new Promise((resolve) => (finishFade = resolve)),
        cancel: vi.fn()
      }))
    }
    document.querySelector = vi.fn(() => provider)

    const first = component.setThemeWithTransition('dark')
    const second = component.setThemeWithTransition('light')
    finishFade?.()
    await Promise.all([first, second])

    expect(state.config.theme).toBe('light')
    expect(provider.animate).not.toHaveBeenCalled()
  })

  it('switches atomically when reduced motion is requested', async () => {
    const component = await mount()
    window.matchMedia = vi.fn(() => ({ matches: true }))

    await component.setThemeWithTransition('dark')

    expect(state.config.theme).toBe('dark')
    expect(document.documentElement.classList.contains('mower-theme-changing')).toBe(false)
    expect(document.documentElement.classList.contains('mower-theme-colours')).toBe(false)
  })

  it('keeps colour transitions until their actual completion and ignores other animations', async () => {
    const component = await mount()
    let finishColours
    document.getAnimations.mockReturnValue([
      {
        transitionProperty: 'background-color',
        finished: new Promise((resolve) => (finishColours = resolve))
      },
      { animationName: 'busy-spinner', finished: new Promise(() => {}) }
    ])

    const changing = component.setThemeWithTransition('dark')
    await vi.waitFor(() => expect(document.getAnimations).toHaveBeenCalledOnce())
    expect(document.documentElement.classList.contains('mower-theme-colours')).toBe(true)
    expect(document.documentElement.classList.contains('mower-theme-changing')).toBe(false)
    finishColours()
    await changing
    expect(document.documentElement.classList.contains('mower-theme-colours')).toBe(false)
    expect(state.config.theme).toBe('dark')
  })

  it('keeps the latest colour transition active after an earlier transition completes', async () => {
    const component = await mount()
    let finishFirst
    let finishLast
    document.getAnimations
      .mockReturnValueOnce([
        {
          transitionProperty: 'background-color',
          finished: new Promise((resolve) => (finishFirst = resolve))
        }
      ])
      .mockReturnValueOnce([
        {
          transitionProperty: 'background-color',
          finished: new Promise((resolve) => (finishLast = resolve))
        }
      ])
    const first = component.setThemeWithTransition('dark')
    await vi.waitFor(() => expect(document.getAnimations).toHaveBeenCalledTimes(1))
    const last = component.setThemeWithTransition('light')
    await vi.waitFor(() => expect(document.getAnimations).toHaveBeenCalledTimes(2))

    finishFirst()
    await first
    expect(document.documentElement.classList.contains('mower-theme-colours')).toBe(true)
    finishLast()
    await last
    expect(document.documentElement.classList.contains('mower-theme-colours')).toBe(false)
    expect(state.config.theme).toBe('light')
  })

  it('cancels active colour motion when reduced motion is requested for the same theme', async () => {
    const component = await mount()
    let finishColours
    document.getAnimations.mockReturnValue([
      {
        transitionProperty: 'background-color',
        finished: new Promise((resolve) => (finishColours = resolve))
      }
    ])
    const first = component.setThemeWithTransition('dark')
    await vi.waitFor(() => expect(document.getAnimations).toHaveBeenCalledOnce())
    window.matchMedia = vi.fn(() => ({ matches: true }))
    await component.setThemeWithTransition('dark')
    expect(document.documentElement.classList.contains('mower-theme-colours')).toBe(false)
    expect(document.documentElement.classList.contains('mower-theme-changing')).toBe(false)
    finishColours()
    await first
  })

  it('keeps an external theme assignment atomic while a control transition is active', async () => {
    const component = await mount()
    let finishColours
    document.getAnimations.mockReturnValue([
      {
        transitionProperty: 'background-color',
        finished: new Promise((resolve) => (finishColours = resolve))
      }
    ])
    const first = component.setThemeWithTransition('dark')
    await vi.waitFor(() => expect(document.getAnimations).toHaveBeenCalledOnce())

    state.config.theme = 'light'
    expect(document.documentElement.classList.contains('mower-theme-colours')).toBe(false)
    expect(document.documentElement.classList.contains('mower-theme-changing')).toBe(true)
    await nextTick()
    expect(document.documentElement.classList.contains('mower-theme-changing')).toBe(false)
    finishColours()
    await first
    expect(state.config.theme).toBe('light')
  })

  it('finishes only the last update when theme bindings change repeatedly in one frame', async () => {
    await mount()
    const root = document.documentElement
    state.config.theme = 'dark'
    state.config.theme = 'light'
    state.config.theme = 'dark'
    expect(root.classList.remove).not.toHaveBeenCalled()

    await nextTick()
    expect(state.config.theme).toBe('dark')
    expect(root.dataset.mowerTheme).toBe('dark')
    expect(root.classList.remove).toHaveBeenCalledExactlyOnceWith('mower-theme-changing')
  })

  it('restores transitions after a same-frame switch back to the initial theme', async () => {
    await mount()
    const root = document.documentElement
    state.config.theme = 'dark'
    state.config.theme = 'light'
    expect(root.classList.contains('mower-theme-changing')).toBe(true)

    await nextTick()
    expect(root.classList.contains('mower-theme-changing')).toBe(false)
    expect(root.classList.remove).toHaveBeenCalledExactlyOnceWith('mower-theme-changing')
  })

  it('commits component colours before restoring CSS transitions', async () => {
    let renderedTheme
    let themeAtStyleCommit
    const renderer = createRenderer({
      createElement: () => ({}),
      createText: () => ({}),
      createComment: () => ({}),
      setText: () => {},
      setElementText: () => {},
      parentNode: () => null,
      nextSibling: () => null,
      patchProp(_element, key, _previous, value) {
        if (key === 'data-theme') renderedTheme = value
      },
      insert: () => {},
      remove: () => {}
    })
    const app = renderer.createApp({
      setup() {
        const component = App.setup({}, { expose: () => {} })
        return () => h('main', { 'data-theme': component.theme.value })
      }
    })
    app.mount({})
    await nextTick()
    Object.defineProperty(document.documentElement, 'offsetWidth', {
      get() {
        themeAtStyleCommit = renderedTheme
        return 1000
      }
    })

    state.config.theme = 'dark'
    await nextTick()
    expect(renderedTheme).toBe('dark')
    expect(themeAtStyleCommit).toBe('dark')
    app.unmount()
  })

  it.each([false, true])(
    'provides the Mower menu outside the native shell: %s',
    async (nativeShell) => {
      state.shellActive = nativeShell
      const component = await mount()
      const html = await renderShell(component)
      if (nativeShell) expect(html).not.toContain('class="app-menu-header"')
      else expect(html).toMatch(/<header[^>]*class="app-menu-header"[^>]*style="display:none;"/)
      expect(html.includes('data-app-menus')).toBe(!nativeShell)
      if (!nativeShell) {
        expect(html).toContain('data-menu-mode="brand"')
        expect(html.indexOf('class="sidebar-brand')).toBeLessThan(html.indexOf('data-app-menus'))
      }
    }
  )

  it('hides the Mower menu in the icon rail and restores it when expanded, hidden or mobile', async () => {
    const component = await mount()
    component.sidebarCollapsed.value = true
    let html = await renderShell(component)
    expect(html).toMatch(/<header[^>]*class="app-menu-header"[^>]*style="display:none;"/)
    expect(html).toContain('data-menu-active="false"')
    expect(html).not.toContain('data-menu-active="true"')
    component.sidebarCollapsed.value = false
    html = await renderShell(component)
    expect(html.match(/data-menu-active="true"/g)).toHaveLength(1)
    await component.handleViewAction('toggle-sidebar')
    html = await renderShell(component)
    expect(html).toContain('class="app-menu-header"')
    expect(html.match(/data-menu-active="true"/g)).toHaveLength(1)
    expect(html).not.toContain('data-menu-active="false"')
    await component.handleViewAction('toggle-sidebar')
    html = await renderShell(component)
    expect(html).toMatch(/<header[^>]*class="app-menu-header"[^>]*style="display:none;"/)
    expect(html.match(/data-menu-active="true"/g)).toHaveLength(1)
    component.isMobileNav.value = true
    html = await renderShell(component)
    expect(html).toContain('class="app-menu-header"')
    expect(html.match(/data-menu-active="true"/g)).toHaveLength(1)
    expect(html).toContain('data-menu-mode="brand"')
  })

  it('keeps instance management out of instance windows even with a native bridge', async () => {
    const getInstances = vi.fn()
    window.pywebview = { api: { get_instances: getInstances } }
    const component = await mount()
    expect(component.appMenuProps.value).not.toHaveProperty('showInstanceMenu')
    expect(getInstances).not.toHaveBeenCalled()
    expect(state.client.get.mock.calls.some(([url]) => /\/instances(?:\/|$)/.test(url))).toBe(false)
  })

  it('opens shared help actions without changing task execution', async () => {
    const component = await mount()
    const requests = state.client.get.mock.calls.length
    component.openHelp('feedback')
    expect(component.showFeedback.value).toBe(true)
    component.openHelp('documentation')
    expect(state.router.push).toHaveBeenCalledWith({ name: 'doc' })
    component.openHelp('about')
    expect(component.helpSection.value).toBe('about')
    component.openHelp('changelog')
    expect(component.helpSection.value).toBe('changelog')
    expect(state.client.get.mock.calls.length).toBe(requests)
    expect(state.mower.running).toBe(false)
  })

  it('expands the sidebar when editing starts in the icon rail', async () => {
    const component = await mount()
    component.sidebarCollapsed.value = true
    component.expandSidebar()
    expect(component.sidebarCollapsed.value).toBe(false)
    expect(component.userToggledSidebar.value).toBe(true)
  })

  async function useAllSettingsRouter(initial = '/') {
    const stubRoutes = (records) =>
      records.map(({ component, children, ...record }) => ({
        ...record,
        ...(component && { component: { render: () => null } }),
        ...(children && { children: stubRoutes(children) })
      }))
    const router = createRouter({ history: createMemoryHistory(), routes: stubRoutes(routes) })
    await router.push(initial)
    state.router = router
    state.route = reactive({
      get name() {
        return router.currentRoute.value.name
      },
      get meta() {
        return router.currentRoute.value.meta
      },
      get fullPath() {
        return router.currentRoute.value.fullPath
      }
    })
    return router
  }

  it.each(['/task-settings', '/mowersettings?token=existing#interface'])(
    'collapses the main sidebar for a direct visit to %s and expands it when space allows',
    async (path) => {
      const router = await useAllSettingsRouter(path)
      const component = await mount()
      expect(router.currentRoute.value.name).toBe('task-settings')
      expect(component.sidebarCollapsed.value).toBe(true)
      expect(component.sidebarHidden.value).toBe(false)
      expect(component.mobileMenuOpen.value).toBe(false)
      window.innerWidth = 1440
      component.actions_on_resize()
      expect(component.sidebarCollapsed.value).toBe(false)
      const html = await renderShell(component)
      expect(html).toContain('data-collapsed="false"')
      expect(html).toContain('data-sidebar="main"')
    }
  )

  it.each([
    [1600, 1, false],
    [1600, 1.25, true],
    [1399, 1, true],
    [1400, 1, false]
  ])(
    'uses available width when opening settings at %spx and zoom %s',
    async (width, zoom, collapsed) => {
      window.innerWidth = width
      const router = await useAllSettingsRouter()
      const component = await mount()
      document.documentElement.style.zoom = String(zoom)
      component.expandSidebar()
      await router.push('/task-settings')
      expect(component.sidebarCollapsed.value).toBe(collapsed)
      window.innerWidth = 1800
      document.documentElement.style.zoom = '1'
      component.actions_on_resize()
      expect(component.sidebarCollapsed.value).toBe(false)
      await router.push('/')
      expect(component.sidebarCollapsed.value).toBe(false)
      expect(component.userToggledSidebar.value).toBe(true)
    }
  )

  it('collapses on entering all settings and preserves manual expansion until the next visit', async () => {
    const router = await useAllSettingsRouter()
    const component = await mount()
    component.expandSidebar()
    await router.push('/task-settings')
    expect(component.sidebarCollapsed.value).toBe(true)

    component.toggleSidebar()
    expect(component.sidebarCollapsed.value).toBe(false)
    await router.push('/task-settings?search=maa#task-maa')
    expect(component.sidebarCollapsed.value).toBe(false)
    component.actions_on_resize()
    expect(component.sidebarCollapsed.value).toBe(false)

    await router.push('/')
    expect(component.sidebarCollapsed.value).toBe(false)
    await router.push('/mowersettings#interface')
    expect(component.sidebarCollapsed.value).toBe(true)
    expect(component.sidebarHidden.value).toBe(false)
    expect(component.mobileMenuOpen.value).toBe(false)
  })

  it.each([false, true])(
    'restores the previous sidebar collapse state after leaving settings (%s)',
    async (collapsed) => {
      const router = await useAllSettingsRouter()
      const component = await mount()
      component.sidebarCollapsed.value = collapsed
      component.userToggledSidebar.value = true
      await router.push('/task-settings')
      expect(component.sidebarCollapsed.value).toBe(true)
      component.toggleSidebar()
      expect(component.sidebarCollapsed.value).toBe(false)
      await router.push('/plan-editor')
      expect(component.sidebarCollapsed.value).toBe(collapsed)
      expect(component.userToggledSidebar.value).toBe(true)
    }
  )

  it('restores automatic responsive collapsing after leaving settings', async () => {
    const router = await useAllSettingsRouter()
    const component = await mount()
    expect(component.userToggledSidebar.value).toBe(false)
    await router.push('/task-settings')
    component.toggleSidebar()
    await router.push('/')
    expect(component.userToggledSidebar.value).toBe(false)
    window.innerWidth = 720
    component.actions_on_resize()
    expect(component.sidebarCollapsed.value).toBe(true)
  })

  it.each([false, true])(
    'keeps the mobile drawer state when entering all settings (open %s)',
    async (open) => {
      window.innerWidth = 600
      const router = await useAllSettingsRouter()
      const component = await mount()
      expect(component.isMobileNav.value).toBe(true)
      component.mobileMenuOpen.value = open
      const collapsed = component.sidebarCollapsed.value
      await router.push('/task-settings')
      expect(component.mobileMenuOpen.value).toBe(open)
      expect(component.sidebarCollapsed.value).toBe(collapsed)
      expect(component.sidebarHidden.value).toBe(false)
    }
  )

  it('hides and restores the desktop sidebar without changing its collapse or task state', async () => {
    const component = await mount()
    component.sidebarCollapsed.value = true
    const requests = state.client.get.mock.calls.length
    await component.handleViewAction('toggle-sidebar')
    expect(component.sidebarVisible.value).toBe(false)
    expect(component.sidebarHidden.value).toBe(true)
    expect(component.sidebarCollapsed.value).toBe(true)
    await component.handleViewAction('toggle-sidebar')
    expect(component.sidebarVisible.value).toBe(true)
    expect(component.sidebarCollapsed.value).toBe(true)
    expect(state.client.get.mock.calls.length).toBe(requests)
    expect(state.mower.running).toBe(false)
  })

  it('opens sidebar editing while preserving the settings dialog and hidden sidebar', async () => {
    const component = await mount()
    state.route.meta.settingsSidebar = true
    component.sidebarHidden.value = true
    component.sidebarCollapsed.value = true
    await component.handleViewAction('edit-sidebar')
    expect(component.sidebarHidden.value).toBe(true)
    expect(component.sidebarCollapsed.value).toBe(true)
    expect(component.sidebarEditorOpen.value).toBe(true)
    const html = await renderShell(component)
    expect(html).toContain('data-sidebar-editor="true"')
    expect(html).toContain('data-settings-dialog="true"')
    expect(state.router.push).not.toHaveBeenCalled()
  })

  it('uses the mobile drawer for toggling and an independent window for editing', async () => {
    const component = await mount()
    component.isMobileNav.value = true
    await component.handleViewAction('toggle-sidebar')
    expect(component.mobileMenuOpen.value).toBe(true)
    expect(component.sidebarVisible.value).toBe(true)
    await component.handleViewAction('toggle-sidebar')
    expect(component.mobileMenuOpen.value).toBe(false)
    await component.handleViewAction('edit-sidebar')
    expect(component.mobileMenuOpen.value).toBe(false)
    expect(component.sidebarEditorOpen.value).toBe(true)
  })

  it('initializes sidebar storage after installing authentication and forwards group requests', async () => {
    state.sidebarInitialize.mockImplementation(async () => {
      expect(state.client.defaults.headers.common).toHaveProperty('token')
      expect(state.client.defaults.headers.common['X-Mower-Config-Generation']).toBe('0')
      return true
    })
    const component = await mount()
    expect(state.sidebarInitialize).toHaveBeenCalled()
    const request = { action: 'rename-group', groupKey: 'daily' }
    component.openSidebarEditor(request)
    expect(component.sidebarEditorRequest.value).toEqual(request)
    expect(component.sidebarEditorOpen.value).toBe(true)
  })

  it('restores a fully expanded sidebar using the native control after hiding it', async () => {
    const component = await mount()
    component.sidebarCollapsed.value = true
    component.sidebarHidden.value = true
    component.toggleSidebar()
    expect(component.sidebarHidden.value).toBe(false)
    expect(component.sidebarCollapsed.value).toBe(false)
  })

  it('leaves the application unloaded when profile bootstrap fails', async () => {
    state.client.get.mockRejectedValueOnce(new Error('配置服务不可用'))
    const component = await mount()
    expect(state.loaded.value).toBe(false)
    expect(state.config.load_config).not.toHaveBeenCalled()
    expect(state.plan.load_plan).not.toHaveBeenCalled()
    expect(state.mower.get_running).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
    expect(component.configProfiles.error.value).toBe('配置服务不可用')
    expect(state.client.defaults.headers.common['X-Mower-Config-Generation']).toBeUndefined()
  })

  it.each(['code', 'error'])(
    'freezes ordinary autosave conflicts using %s and ejects the handler',
    async (field) => {
      const component = await mount()
      const failure = {
        response: {
          status: 409,
          data: { [field]: 'configuration_changed', message: '配置已在其他页面切换' }
        }
      }
      await expect(state.responseRejected(failure)).rejects.toBe(failure)
      expect(component.configProfiles.stale.value).toBe(true)
      for (const store of [state.config, state.plan, state.rescuePlan])
        expect(store.autosave_paused).toBe(true)
      expect(state.client.defaults.headers.common['X-Mower-Config-Generation']).toBe('0')
      unmount()
      expect(state.client.interceptors.response.eject).toHaveBeenCalledWith(17)
    }
  )

  it('never restarts a stopped desktop task on mount, refresh or reopening', async () => {
    for (let i = 0; i < 3; i++) {
      await mount()
      expect(state.loaded.value).toBe(true)
      expect(state.mower.running).toBe(false)
      expect(state.mower.log_lines).toEqual(['existing log'])
      expect(state.client.get.mock.calls.every(([url]) => url.endsWith('/config-profiles'))).toBe(
        true
      )
      expect(state.resource.installResource).not.toHaveBeenCalled()
      unmount()
    }
    expect(state.mower.get_running).toHaveBeenCalledTimes(3)
  })

  it('retains the page startup fallback for hosts without desktop startup ownership', async () => {
    state.mower.get_running.mockImplementation(async () => {})
    await mount()
    expect(state.client.get).toHaveBeenCalledWith(expect.stringContaining('/start/0'))
    expect(state.resource.installResource).toHaveBeenCalledOnce()
  })

  it('still opens the existing update-completion modal automatically', async () => {
    state.loadUpdateNotice.mockResolvedValue({ should_show: true })
    await mount()
    expect(component.showUpdateNoticeModal.value).toBe(true)
  })

  it('loads the schedule in parallel and retains the complete initialization barrier', async () => {
    const config = deferred()
    const plan = deferred()
    const operators = deferred()
    const status = deferred()
    state.config.load_config.mockReturnValue(config.promise)
    state.plan.load_plan.mockReturnValue(plan.promise)
    state.plan.load_operators.mockReturnValue(operators.promise)
    state.mower.get_running.mockReturnValue(status.promise)
    const mounting = mount()
    try {
      await vi.waitFor(() => expect(state.plan.load_plan).toHaveBeenCalledOnce())
      expect(state.config.load_config).toHaveBeenCalledOnce()
      expect(state.plan.load_operators).toHaveBeenCalledOnce()
      expect(state.mower.get_running).toHaveBeenCalledOnce()
      expect(state.loaded.value).toBe(false)
      config.resolve()
      plan.resolve()
      operators.resolve()
      await nextTick()
      expect(state.loaded.value).toBe(false)
      expect(state.mower.listen_ws).not.toHaveBeenCalled()
      status.resolve()
      await mounting
      expect(state.loaded.value).toBe(true)
      expect(state.mower.listen_ws).toHaveBeenCalledOnce()
    } finally {
      config.resolve()
      plan.resolve()
      operators.resolve()
      status.resolve()
      await mounting
    }
  })

  it('shows the page while setting options and the update notice are still loading', async () => {
    const shop = deferred()
    const items = deferred()
    const notice = deferred()
    state.config.load_shop.mockReturnValue(shop.promise)
    state.config.load_item.mockReturnValue(items.promise)
    state.loadUpdateNotice.mockReturnValue(notice.promise)
    const mounting = mount()
    try {
      await vi.waitFor(() => expect(state.loaded.value).toBe(true))
      expect(state.mower.listen_ws).toHaveBeenCalledOnce()
      expect(component.showUpdateNoticeModal.value).toBe(false)
      notice.resolve({ should_show: true })
      await vi.waitFor(() => expect(component.showUpdateNoticeModal.value).toBe(true))
    } finally {
      shop.resolve()
      items.resolve()
      notice.resolve({ should_show: false })
      await mounting
    }
  })

  it.each(['load_shop', 'load_item'])('keeps the page usable when %s fails', async (load) => {
    const error = new Error('options unavailable')
    const report = vi.spyOn(console, 'error').mockImplementation(() => {})
    state.config[load].mockRejectedValue(error)
    try {
      await mount()
      expect(state.loaded.value).toBe(true)
      expect(state.mower.listen_ws).toHaveBeenCalledOnce()
      expect(report).toHaveBeenCalledWith('failed to load setting options', error)
    } finally {
      report.mockRestore()
    }
  })

  it('keeps update-notice failures separate from page initialization', async () => {
    const error = new Error('notice unavailable')
    const report = vi.spyOn(console, 'error').mockImplementation(() => {})
    state.loadUpdateNotice.mockRejectedValue(error)
    try {
      await mount()
      expect(state.loaded.value).toBe(true)
      expect(state.mower.listen_ws).toHaveBeenCalledOnce()
      expect(component.showUpdateNoticeModal.value).toBe(false)
      expect(report).toHaveBeenCalledWith('failed to load update notice', error)
    } finally {
      report.mockRestore()
    }
  })

  it('keeps host fallback startup behind resource installation and refreshed data', async () => {
    const installation = deferred()
    const refreshedItems = deferred()
    const notice = deferred()
    state.mower.get_running.mockImplementation(async () => {})
    state.resource.installResource.mockReturnValue(installation.promise)
    state.config.load_item.mockResolvedValueOnce().mockReturnValueOnce(refreshedItems.promise)
    state.loadUpdateNotice.mockReturnValue(notice.promise)
    const mounting = mount()
    try {
      await vi.waitFor(() => expect(state.resource.installResource).toHaveBeenCalledOnce())
      expect(state.loaded.value).toBe(true)
      expect(state.client.get).not.toHaveBeenCalledWith(expect.stringContaining('/start/0'))
      installation.resolve(true)
      await vi.waitFor(() => expect(state.config.load_item).toHaveBeenCalledTimes(2))
      expect(state.client.get).not.toHaveBeenCalledWith(expect.stringContaining('/start/0'))
      refreshedItems.resolve()
      await mounting
      expect(state.client.get.mock.calls.filter(([url]) => url.endsWith('/start/0'))).toHaveLength(
        1
      )
    } finally {
      installation.resolve(true)
      refreshedItems.resolve()
      notice.resolve({ should_show: false })
      await mounting
    }
  })

  it('preserves saved configuration and complete schedule data during concurrent initialization', async () => {
    const [{ useConfigStore }, { usePlanStore }] = await Promise.all([
      vi.importActual('@/stores/config'),
      vi.importActual('@/stores/plan')
    ])
    setActivePinia(createPinia())
    state.config = useConfigStore()
    state.plan = usePlanStore()
    state.mower.updates_enabled = false
    const config = deferred()
    const plan = deferred()
    const weeklyPlan = deferred()
    const shop = deferred()
    const items = deferred()
    const configData = {
      account: 'saved account',
      free_blacklist: '',
      reload_room: '',
      maa_mall_buy: '招聘许可',
      maa_mall_blacklist: '家具零件',
      favorite: '',
      reclamation_algorithm: {},
      secret_front: {},
      maa_weekly_plan: [],
      maa_weekly_plan_active: '默认',
      dorm_isolation: [['红', '砾']],
      resource_update: { enable: false, auto_update: false }
    }
    const planData = {
      conf: {},
      plan1: { central: { plans: [{ agent: '阿米娅', group: '主班', replacement: ['红'] }] } },
      backup_plans: []
    }
    const profileResponse = state.client.get.getMockImplementation()
    state.client.get.mockImplementation((url) => {
      if (url.endsWith('/config-profiles')) return profileResponse(url)
      if (url.endsWith('/conf')) return config.promise
      if (url.endsWith('/plan')) return plan.promise
      if (url.endsWith('/weekly-plans')) return weeklyPlan.promise
      if (url.endsWith('/shop')) return shop.promise
      if (url.endsWith('/item')) return items.promise
      if (url.endsWith('/operator')) return Promise.resolve({ data: ['阿米娅', '红'] })
      throw new Error(`Unexpected request: ${url}`)
    })
    const mounting = mount()
    try {
      plan.resolve({ data: planData })
      await nextTick()
      expect(state.loaded.value).toBe(false)
      expect(state.client.post).not.toHaveBeenCalled()
      expect(state.client.patch).not.toHaveBeenCalled()
      config.resolve({ data: configData })
      await vi.waitFor(() =>
        expect(state.client.get).toHaveBeenCalledWith(expect.stringContaining('/weekly-plans'))
      )
      expect(state.loaded.value).toBe(false)
      expect(state.client.post).not.toHaveBeenCalled()
      expect(state.client.patch).not.toHaveBeenCalled()
      weeklyPlan.resolve({ data: { plans: ['默认'] } })
      await vi.waitFor(() => expect(state.loaded.value).toBe(true))
      await state.config.flush_config_saves()
      await state.plan.wait_for_plan_save()
      expect(state.client.patch).not.toHaveBeenCalled()
      expect(state.client.post).toHaveBeenCalledExactlyOnceWith(
        expect.stringContaining('/plan'),
        expect.objectContaining({
          plan1: expect.objectContaining({
            central: expect.objectContaining({
              plans: expect.arrayContaining([
                expect.objectContaining({ agent: '阿米娅', group: '主班', replacement: ['红'] })
              ])
            })
          }),
          advanced_settings: expect.objectContaining({ dorm_isolation: [['红', '砾']] })
        })
      )
      expect(state.config.maa_mall_buy).toEqual(['招聘许可'])
      expect(state.config.maa_mall_blacklist).toEqual(['家具零件'])
      expect(state.config.shop_list).toEqual([])
      expect(state.config.item_list).toEqual([])
    } finally {
      config.resolve({ data: configData })
      plan.resolve({ data: planData })
      weeklyPlan.resolve({ data: { plans: ['默认'] } })
      shop.resolve({ data: ['招聘许可', '家具零件'] })
      items.resolve({ data: ['固源岩'] })
      await mounting
    }
    await state.config.flush_config_saves()
    expect(state.config.shop_list).toEqual([
      { value: '招聘许可', label: '招聘许可' },
      { value: '家具零件', label: '家具零件' }
    ])
    expect(state.config.item_list).toEqual([{ value: '固源岩', label: '固源岩' }])
    expect(state.client.patch).not.toHaveBeenCalled()
  })

  it('preserves resource automation on non-desktop update restarts', async () => {
    state.mower.get_running.mockImplementation(async () => {
      state.mower.auto_start_handled = true
    })
    await mount()
    expect(state.client.get.mock.calls.every(([url]) => url.endsWith('/config-profiles'))).toBe(
      true
    )
    expect(state.resource.installResource).toHaveBeenCalledOnce()
  })

  it.each([false, null])('suppresses all automatic updates with permission %s', async (enabled) => {
    state.mower.updates_enabled = enabled
    await mount()
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.resource.loadResourceJob).not.toHaveBeenCalled()
    expect(state.resource.loadResourceVersion).not.toHaveBeenCalled()
    expect(state.resource.installResource).not.toHaveBeenCalled()
    expect(state.resource.loadResourceVersionLocal).toHaveBeenCalledOnce()
    expect(state.config.resource_update_enable).toBe(true)
    expect(state.config.resource_update_auto_update).toBe(true)
    expect(state.loaded.value).toBe(true)
  })

  it('keeps the originating page behind settings and restores its query and hash on close', async () => {
    const origin = '/record/depot?tab=history#stock'
    const router = await useSettingsRouter(origin)
    const component = await mount()
    await router.push('/mowersettings')
    let html = await renderShell(component)
    expect(html).toContain('data-settings-dialog="true"')
    expect(html).toContain(`data-content-route="${origin}"`)

    await router.push('/mowersettings#mower-data')
    html = await renderShell(component)
    expect(html).toContain(`data-content-route="${origin}"`)
    expect(html).toContain('data-settings-dialog="true"')
    expect(router.currentRoute.value.hash).toBe('#mower-data')

    const push = vi.spyOn(router, 'push')
    state.settingsDialogClose()
    await push.mock.results.at(-1).value
    expect(router.currentRoute.value.fullPath).toBe(origin)
    html = await renderShell(component)
    expect(html).toContain(`data-content-route="${origin}"`)
    expect(html).not.toContain('data-settings-dialog="true"')
  })

  it('navigates before requesting a device action and reopens the same editor', async () => {
    const component = await mount()
    state.client.post.mockClear()
    let finishNavigation
    state.router.push.mockImplementationOnce(
      () => new Promise((resolve) => (finishNavigation = resolve))
    )
    const opening = component.openDeviceConnection('settings')
    expect(state.router.push).toHaveBeenCalledWith({ name: 'task-settings', hash: '#task-devices' })
    expect(component.deviceConnectionNavigation.request.value).toBeNull()
    finishNavigation()
    await opening
    const first = component.deviceConnectionNavigation.request.value
    expect(first).toEqual({ action: 'settings' })

    await component.openDeviceConnection('settings')
    expect(component.deviceConnectionNavigation.request.value).toEqual({ action: 'settings' })
    expect(component.deviceConnectionNavigation.request.value).not.toBe(first)
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it.each(['running', 'deviceLocked'])(
    'rejects titlebar connection tests while %s and still opens settings',
    async (lock) => {
      const component = await mount()
      state.client.post.mockClear()
      if (lock === 'running') state.mower.running = true
      else component.deviceConnectionNavigation.locked.value = true

      await component.openDeviceConnection('test')
      expect(state.router.push).not.toHaveBeenCalled()
      expect(component.deviceConnectionNavigation.request.value).toBeNull()

      await component.openDeviceConnection('settings')
      expect(component.deviceConnectionNavigation.request.value).toEqual({ action: 'settings' })
      expect(state.client.post).not.toHaveBeenCalled()
    }
  )

  it('does not dispatch a device action when navigation is aborted', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'log', component: { render: () => null } },
        { path: '/task-settings', name: 'task-settings', component: { render: () => null } },
        { path: '/other', component: { render: () => null } }
      ]
    })
    await router.push('/other')
    router.beforeEach(() => false)
    state.router = router
    const component = await mount()

    await component.openDeviceConnection('test')

    expect(component.deviceConnectionNavigation.request.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/other')
  })

  it('dispatches again after a duplicate device-settings navigation', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', name: 'log', component: { render: () => null } },
        { path: '/task-settings', name: 'task-settings', component: { render: () => null } }
      ]
    })
    await router.push({ name: 'task-settings', hash: '#task-devices' })
    state.router = router
    const component = await mount()

    await component.openDeviceConnection('select')

    expect(component.deviceConnectionNavigation.request.value).toEqual({ action: 'select' })
  })

  it('retains task configuration drafts and selection while ordinary pages remount', async () => {
    const { descriptor } = parse(readFileSync(new URL('./App.vue', import.meta.url), 'utf8'))
    const findView = (node) =>
      node.tag === 'router-view' ? node : node.children?.map(findView).find(Boolean)
    const contentView = findView(descriptor.template.ast)
    expect(contentView).toBeTruthy()
    const drafts = []
    let ordinaryMounts = 0
    const taskPage = defineComponent({
      name: 'TaskSettings',
      setup() {
        const draft = reactive({ address: '', selectedId: 'devices' })
        drafts.push(draft)
        return () =>
          h('section', { 'data-task-settings': true }, [
            h('input', { 'data-device-draft': true, value: draft.address }),
            h('span', { 'data-selected-entry': draft.selectedId }, draft.selectedId)
          ])
      }
    })
    const ordinaryPage = defineComponent({
      name: 'OrdinaryPage',
      setup() {
        ordinaryMounts += 1
        return () => h('section', { 'data-ordinary-page': true })
      }
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/task-settings', name: 'task-settings', component: taskPage },
        { path: '/', name: 'log', component: ordinaryPage }
      ]
    })
    await router.push('/task-settings')
    const node = (tag, text = '') => ({
      tag,
      text,
      props: {},
      children: [],
      parent: null,
      getRootNode() {
        let root = this
        while (root.parent) root = root.parent
        return root
      }
    })
    const renderer = createRenderer({
      createElement: (tag) => node(tag),
      createText: (text) => node('#text', text),
      createComment: (text) => node('#comment', text),
      setText: (target, text) => (target.text = text),
      setElementText: (target, text) => (target.text = text),
      parentNode: (target) => target.parent,
      nextSibling: (target) => target.parent?.children[target.parent.children.indexOf(target) + 1],
      patchProp: (target, key, _previous, value) => (target.props[key] = value),
      insert(target, parent, anchor = null) {
        if (target.parent) target.parent.children.splice(target.parent.children.indexOf(target), 1)
        target.parent = parent
        const index = anchor ? parent.children.indexOf(anchor) : -1
        parent.children.splice(index < 0 ? parent.children.length : index, 0, target)
      },
      remove(target) {
        target.parent.children.splice(target.parent.children.indexOf(target), 1)
        target.parent = null
      }
    })
    const app = renderer.createApp({
      setup: () => ({ loaded: true, contentRoute: computed(() => router.currentRoute.value) }),
      render: compile(contentView.loc.source)
    })
    app.use(router)
    const root = node('root')
    const all = (target = root) => [target, ...target.children.flatMap(all)]
    const find = (key) => all().find((target) => target.props[key])
    app.mount(root)
    try {
      expect(drafts).toHaveLength(1)
      const taskElement = find('data-task-settings')
      drafts[0].address = '127.0.0.1:16384'
      drafts[0].selectedId = 'recruit'
      await nextTick()
      expect(find('data-device-draft').props.value).toBe('127.0.0.1:16384')

      await router.push('/')
      await nextTick()
      expect(find('data-task-settings')).toBeUndefined()
      expect(ordinaryMounts).toBe(1)
      const ordinaryElement = find('data-ordinary-page')

      await router.push('/task-settings#task-daily')
      await nextTick()
      expect(drafts).toHaveLength(1)
      expect(find('data-task-settings')).toBe(taskElement)
      expect(find('data-device-draft').props.value).toBe('127.0.0.1:16384')
      expect(find('data-selected-entry').props['data-selected-entry']).toBe('recruit')

      await router.push('/')
      await nextTick()
      expect(ordinaryMounts).toBe(2)
      expect(find('data-ordinary-page')).not.toBe(ordinaryElement)
    } finally {
      app.unmount()
    }
  })

  it('falls back to the log page for a direct settings visit and removes the route hook', async () => {
    const logPage = { render: () => null }
    const loadLog = vi.fn(async () => logPage)
    const router = await useSettingsRouter('/mowersettings#mower-updates', loadLog)
    const removeHook = vi.fn()
    const afterEach = router.afterEach.bind(router)
    vi.spyOn(router, 'afterEach').mockImplementation((callback) => {
      const remove = afterEach(callback)
      return () => {
        removeHook()
        remove()
      }
    })
    const component = await mount()
    await vi.waitFor(() => {
      expect(loadLog).toHaveBeenCalledOnce()
      expect(component.contentRoute.value?.matched[0].components.default).toBe(logPage)
    })
    let html = await renderShell(component)
    expect(html).toContain('data-content-route="/"')
    expect(html).toContain('data-settings-dialog="true"')
    const push = vi.spyOn(router, 'push')
    state.settingsDialogClose()
    await push.mock.results.at(-1).value
    expect(router.currentRoute.value.name).toBe('log')
    html = await renderShell(component)
    expect(html).toContain('data-content-route="/"')
    expect(html).not.toContain('data-settings-dialog="true"')
    unmount()
    expect(removeHook).toHaveBeenCalledOnce()
  })

  it('resolves the log background when a cold-start settings route arrives after App mounts', async () => {
    const logPage = { render: () => null }
    let finishLoading
    const loadLog = vi.fn(() => new Promise((resolve) => (finishLoading = resolve)))
    const router = await useSettingsRouter(undefined, loadLog)
    const component = await mount()
    expect(loadLog).not.toHaveBeenCalled()

    await router.push('/mowersettings#mower-data')
    await vi.waitFor(() => expect(loadLog).toHaveBeenCalledOnce())
    let html = await renderShell(component)
    expect(html).toContain('data-settings-dialog="true"')
    expect(html).not.toContain('data-content-route=')

    finishLoading(logPage)
    await vi.waitFor(() => {
      expect(component.contentRoute.value?.fullPath).toBe('/')
      expect(component.contentRoute.value?.matched[0].components.default).toBe(logPage)
    })
    html = await renderShell(component)
    expect(html).toContain('data-content-route="/"')
    expect(html).toContain('data-settings-dialog="true"')
  })

  it.each([
    [false, false],
    [true, false],
    [false, true],
    [true, true]
  ])(
    'preserves the main sidebar when settings opens (collapsed %s, hidden %s)',
    async (collapsed, hidden) => {
      const router = await useSettingsRouter('/')
      const component = await mount()
      component.sidebarCollapsed.value = collapsed
      component.sidebarHidden.value = hidden
      await router.push('/mowersettings')
      expect(component.sidebarCollapsed.value).toBe(collapsed)
      expect(component.sidebarHidden.value).toBe(hidden)
      const html = await renderShell(component)
      expect(html).toContain('data-sidebar="main"')
      expect(html).toContain('data-settings-dialog="true"')
      expect(html).toContain(`data-collapsed="${collapsed}"`)
    }
  )

  it.each([
    [{}, false],
    [{ settings: true, settingsSidebar: true }, false],
    [{}, true],
    [{ settings: true, settingsSidebar: true }, true]
  ])('keeps the same sidebar width and brand for %s, collapsed %s', async (meta, collapsed) => {
    state.route.meta = meta
    const component = await mount()
    component.sidebarCollapsed.value = collapsed
    const html = await renderShell(component)
    expect(html).toContain('data-sidebar="main"')
    expect(html).toContain('data-width="210"')
    expect(html).toContain(`data-collapsed="${collapsed}"`)
    expect(html).toContain('class="sidebar-brand')
    expect(html).toContain(`aria-expanded="${!collapsed}" aria-controls="sidebar-navigation"`)
    expect(html.indexOf('class="sidebar-brand')).toBeLessThan(html.indexOf('data-sidebar="main"'))
  })

  it('keeps the native sidebar text without repeating the titlebar logo or leaving a collapsed header', async () => {
    state.shellActive = true
    state.shellMetadata.version = '4.1.6-alpha.12'
    state.resource.info.current_display = '昨日海#1009'
    const component = await mount()
    const expanded = await renderShell(component)
    expect(expanded).toContain('sidebar-brand--text-only')
    expect(expanded).toContain('软件版本 4.1.6-alpha.12')
    expect(expanded).toContain('资源版本 昨日海#1009')
    expect(expanded).not.toContain('<img')
    component.toggleSidebar()
    const collapsed = await renderShell(component)
    expect(collapsed).not.toContain('class="sidebar-brand')
    expect(collapsed).toContain('data-sidebar="main"')
  })

  it('keeps live resource and software versions in the pinned sidebar brand', async () => {
    state.shellMetadata.version = '4.1.6-alpha.12 - 昨日海#1009'
    state.resource.info.current_display = '昨日海#1009'
    const component = await mount()
    expect(component.softwareVersion.value).toBe('4.1.6-alpha.12')
    expect(component.resourceVersion.value).toBe('昨日海#1009')
    const html = await renderShell(component)
    expect(html).toContain('软件版本 4.1.6-alpha.12')
    expect(html).toContain('资源版本 昨日海#1009')
    state.resource.info.current_display = '海渊巡游#1017'
    expect(component.resourceVersion.value).toBe('海渊巡游#1017')
    expect(component.windowTitleVersion.value).toBe('4.1.6-alpha.12 - 海渊巡游#1017')
    state.resource.info.current_display = ''
    expect(component.resourceVersion.value).toBe('')
    expect(component.windowTitleVersion.value).toBe('4.1.6-alpha.12')
    const withoutResource = await renderShell(component)
    expect(withoutResource).not.toContain('资源版本 昨日海#1009')
    expect(withoutResource).not.toContain('资源版本 海渊巡游#1017')
    component.toggleSidebar()
    expect(component.sidebarCollapsed.value).toBe(true)
    expect(component.userToggledSidebar.value).toBe(true)
  })

  it.each([false, true])(
    'uses actual deployment for the sidebar badge (mobile %s)',
    async (mobile) => {
      state.shellMetadata.version = '4.1.6-alpha.12.gdeadbeef+deadbee'
      state.mower.deployment = 'source'
      const component = await mount()
      component.isMobileNav.value = mobile
      component.mobileMenuOpen.value = mobile
      const source = await renderShell(component)
      expect(source).toContain('sidebar-brand-channel--source')
      expect(source).toContain('源码启动')
      expect(source).toContain('软件版本 4.1.6-alpha.12.gdeadbeef+deadbee')
      expect(source).not.toContain('sidebar-brand-channel--nightly')
      state.mower.deployment = 'release'
      const release = await renderShell(component)
      expect(release).toContain('sidebar-brand-channel--nightly')
      expect(release).not.toContain('sidebar-brand-channel--source')
      state.mower.deployment = null
      const unknown = await renderShell(component)
      expect(unknown).toContain('sidebar-brand-channel--nightly')
      expect(unknown).not.toContain('sidebar-brand-channel--source')
    }
  )

  it.each([false, true])(
    'uses the shared software version display preference (mobile %s)',
    async (mobile) => {
      state.shellMetadata.version = '4.1.6-alpha.12.gdeadbeef+deadbee'
      state.mower.deployment = 'source'
      state.gui.softwareVersionDisplay = 'channel'
      const component = await mount()
      component.isMobileNav.value = mobile
      component.mobileMenuOpen.value = mobile
      const channel = await renderShell(component)
      expect(channel).toMatch(/<button\b[^>]*class="sidebar-brand-channel[^>]*>source<\/button>/)
      expect(channel).toContain('点击检查软件更新')
      expect(channel).not.toContain('aria-pressed=')
      state.gui.softwareVersionDisplay = 'version'
      const version = await renderShell(component)
      expect(version).toMatch(
        /<button\b[^>]*class="sidebar-brand-channel[^>]*>4\.1\.6-alpha\.12\.gdeadbeef\+deadbee<\/button>/
      )
      expect(version).toContain('点击检查软件更新')
      expect(state.gui.setSoftwareVersionDisplay).not.toHaveBeenCalled()
      expect(state.gui.load).toHaveBeenCalledOnce()
    }
  )

  it.each([false, true])(
    'uses current installed resource dates in the brand (mobile %s)',
    async (mobile) => {
      const now = Date.now() / 1000
      state.resource.info.current_display = '当前资源'
      state.resource.info.current_metadata = {
        activity: { name: '昨日海', time: now + 86400, endTime: now + 172800 }
      }
      const component = await mount()
      component.isMobileNav.value = mobile
      component.mobileMenuOpen.value = mobile
      const upcoming = await renderShell(component)
      expect(upcoming).toContain('--resource-badge-hue:140')
      state.resource.info.current_metadata = {
        activity: { name: '昨日海', time: now - 172800, endTime: now - 86400 }
      }
      const ended = await renderShell(component)
      expect(ended).toContain('--resource-badge-hue:0')
      expect(ended).toContain('活动已结束')
    }
  )

  it.each([
    [{ settings: true, settingsSidebar: true }, true],
    [{ settings: true }, false]
  ])('uses the same settings dialog on mobile for %s: %s', async (meta, dialogAvailable) => {
    state.route.meta = meta
    const component = await mount()
    component.isMobileNav.value = true
    const html = await renderShell(component)
    expect(html.includes('data-settings-dialog="true"')).toBe(dialogAvailable)
    expect(html).not.toContain('mobile-settings-header')
    expect(html).not.toContain('← 返回')
    expect(html).not.toContain('aria-label="设置目录"')
  })

  it('closes the mobile settings dialog when returning to logs', async () => {
    const router = await useSettingsRouter('/')
    const component = await mount()
    component.isMobileNav.value = true
    await router.push('/mowersettings')
    expect(await renderShell(component)).toContain('data-settings-dialog="true"')
    const push = vi.spyOn(router, 'push')
    state.settingsDialogClose()
    await push.mock.results.at(-1).value
    expect(router.currentRoute.value.name).toBe('log')
    expect(await renderShell(component)).not.toContain('data-settings-dialog="true"')
  })

  it.each([
    [892, 1.5, true],
    [1440, 1.5, false]
  ])(
    'uses the available layout width for a %spx window at zoom %s',
    async (width, zoom, narrow) => {
      const component = await mount()
      window.innerWidth = width
      document.documentElement.clientWidth = width
      document.documentElement.style.zoom = String(zoom)
      component.actions_on_resize()
      expect(component.isMobileNav.value).toBe(narrow)
    }
  )
})
