import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import App from './App.vue'
import SessionLink from './components/SessionLink.vue'

const state = vi.hoisted(() => ({
  mounted: [],
  unmounted: [],
  client: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), defaults: { headers: { common: {} } } },
  config: null,
  mower: null,
  plan: null,
  resource: null,
  loaded: null,
  loadUpdateNotice: vi.fn(),
  closeWindow: vi.fn()
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
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => state.plan }))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => state.resource }))
vi.mock('@/stores/updateNotice', () => ({
  useUpdateNoticeStore: () => ({
    notice: { changelog: '' },
    loadUpdateNotice: state.loadUpdateNotice,
    ackUpdateNotice: vi.fn()
  })
}))
vi.mock('@/stores/watermark', () => ({
  usewatermarkStore: () => ({
    getwatermarkinfo: vi.fn(async () => 'mower')
  })
}))
vi.mock('@/window-shell/adapter.js', () => ({
  createWindowShellAdapter: () => ({
    metadata: { version: '' },
    active: ref(false),
    close: state.closeWindow,
    initialize: vi.fn(),
    dispose: vi.fn()
  }),
  formatWindowTitle: vi.fn(),
  formatEmulatorLabel: vi.fn()
}))
vi.mock('@/utils/modal-drag.js', () => ({ installModalDragging: () => vi.fn() }))
vi.mock('@/components/Feedback.vue', () => ({ default: {} }))
vi.mock('@/components/GlobalUpdateDrop.vue', () => ({ default: {} }))
vi.mock('@/components/WindowTitlebar.vue', () => ({ default: {} }))

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
    state.client.get.mockReset()
    state.client.patch.mockReset().mockResolvedValue({ data: {} })
    state.client.post.mockResolvedValue({ data: {} })
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
    state.mower = reactive({
      ws: null,
      running: false,
      log_lines: ['existing log'],
      auto_start_handled: false,
      desktop_startup_handled: false,
      updates_enabled: true,
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
    vi.stubGlobal('window', {
      innerWidth: 1000,
      location: { search: '', port: '58100' },
      addEventListener: vi.fn(),
      scrollTo: vi.fn()
    })
    vi.stubGlobal('document', {
      location: { search: '' },
      documentElement: {
        clientWidth: 1000,
        dataset: {},
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
  }

  it('uses session navigation for all sidebar page links', async () => {
    await mount()
    function pageLinks(options) {
      return options.flatMap((option) => {
        if (option.children) return pageLinks(option.children)
        const label = option.label()
        return label?.props?.to ? [label] : []
      })
    }
    const links = pageLinks(component.menuOptions)
    expect(links.map((link) => link.props.to.path)).toEqual(
      expect.arrayContaining(['/mowersettings', '/maasettings', '/plan-editor', '/record/report'])
    )
    expect(links.every((link) => link.type === SessionLink)).toBe(true)
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

  it('never restarts a stopped desktop task on mount, refresh or reopening', async () => {
    for (let i = 0; i < 3; i++) {
      await mount()
      expect(state.loaded.value).toBe(true)
      expect(state.mower.running).toBe(false)
      expect(state.mower.log_lines).toEqual(['existing log'])
      expect(state.client.get).not.toHaveBeenCalled()
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
      expect(state.plan.load_plan).toHaveBeenCalledOnce()
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
      expect(state.client.get).not.toHaveBeenCalled()
      installation.resolve(true)
      await vi.waitFor(() => expect(state.config.load_item).toHaveBeenCalledTimes(2))
      expect(state.client.get).not.toHaveBeenCalled()
      refreshedItems.resolve()
      await mounting
      expect(state.client.get).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/start/0'))
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
    state.client.get.mockImplementation((url) => {
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
    expect(state.client.get).not.toHaveBeenCalled()
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
})
