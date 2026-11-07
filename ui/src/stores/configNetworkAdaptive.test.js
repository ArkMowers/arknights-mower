import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia, disposePinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))

let store
let loaded
let pinia

const response = {
  free_blacklist: '',
  reload_room: '',
  maa_mall_buy: '',
  maa_mall_blacklist: '',
  favorite: '',
  reclamation_algorithm: {},
  secret_front: {},
  maa_weekly_plan: [],
  maa_weekly_plan_active: '默认',
  run_order_delay: 3.75,
  run_order_grandet_mode: { enable: true, buffer_time: 22, back_to_index: false },
  waiting_scene: { CONNECTING: [3, 10], LOADING: [2, 30] }
}

function mockConfig(overrides = {}) {
  axios.get.mockImplementation(async (url) => ({
    data: url.endsWith('/weekly-plans')
      ? { plans: ['默认'], active: '默认' }
      : { ...response, ...overrides }
  }))
}

async function setup(overrides = {}) {
  loaded = ref(false)
  pinia = createPinia()
  const app = createApp({})
  app.use(pinia)
  app.provide('loaded', loaded)
  store = app.runWithContext(() => useConfigStore())
  mockConfig(overrides)
  axios.patch.mockResolvedValue({ data: {} })
  await store.load_config()
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()
}

afterEach(() => {
  if (loaded) loaded.value = false
  store?.$dispose()
  if (pinia) disposePinia(pinia)
  vi.clearAllMocks()
})

describe('network adaptive configuration', () => {
  it.each([
    {},
    { run_order_network_adaptive: false, waiting_scene_network_adaptive: false },
    { run_order_network_adaptive: true, waiting_scene_network_adaptive: false },
    { run_order_network_adaptive: false, waiting_scene_network_adaptive: true },
    { run_order_network_adaptive: true, waiting_scene_network_adaptive: true }
  ])('loads and exports independent switches from %j', async (saved) => {
    await setup(saved)
    expect(store.run_order_network_adaptive).toBe(saved.run_order_network_adaptive ?? false)
    expect(store.waiting_scene_network_adaptive).toBe(saved.waiting_scene_network_adaptive ?? false)
    expect(store.build_config()).toMatchObject({
      run_order_network_adaptive: saved.run_order_network_adaptive ?? false,
      waiting_scene_network_adaptive: saved.waiting_scene_network_adaptive ?? false
    })
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it.each(['run_order_network_adaptive', 'waiting_scene_network_adaptive'])(
    'saves only %s and retains the original timing settings',
    async (key) => {
      await setup()
      store[key] = true
      await nextTick()
      await store.flush_config_saves()
      expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
        [key]: true
      })
      expect(store.build_config()).toMatchObject({
        run_order_delay: response.run_order_delay,
        run_order_grandet_mode: response.run_order_grandet_mode,
        waiting_scene: response.waiting_scene
      })
      const other =
        key === 'run_order_network_adaptive'
          ? 'waiting_scene_network_adaptive'
          : 'run_order_network_adaptive'
      expect(store[other]).toBe(false)
    }
  )

  it('clears a previous enabled state when loading an older configuration', async () => {
    await setup({ run_order_network_adaptive: true, waiting_scene_network_adaptive: true })
    mockConfig()
    await store.load_config()
    expect(store.run_order_network_adaptive).toBe(false)
    expect(store.waiting_scene_network_adaptive).toBe(false)
    expect(axios.patch).not.toHaveBeenCalled()
  })
})
