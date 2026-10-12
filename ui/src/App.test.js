import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, reactive, ref } from 'vue'
import App from './App.vue'

const state = vi.hoisted(() => ({
  mounted: [],
  unmounted: [],
  client: { get: vi.fn(), post: vi.fn(), defaults: { headers: { common: {} } } },
  config: null,
  mower: null,
  plan: null,
  resource: null,
  loaded: null
}))
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
    notice: {},
    loadUpdateNotice: vi.fn(async () => ({ should_show: false })),
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

describe('desktop page startup', () => {
  let scope
  beforeEach(() => {
    vi.clearAllMocks()
    state.mounted = []
    state.unmounted = []
    state.loaded = ref(false)
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
    scope.run(() => App.setup({}, { expose: () => {} }))
    for (const callback of state.mounted) await callback()
  }

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

  it('preserves resource automation on non-desktop update restarts', async () => {
    state.mower.get_running.mockImplementation(async () => {
      state.mower.auto_start_handled = true
    })
    await mount()
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.resource.installResource).toHaveBeenCalledOnce()
  })
})
