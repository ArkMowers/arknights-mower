import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
let store
afterEach(() => {
  store?.$dispose()
  vi.resetAllMocks()
})

function setup() {
  const app = createApp({})
  const loaded = ref(false)
  app.use(createPinia())
  app.provide('loaded', loaded)
  store = app.runWithContext(() => useConfigStore())
  return loaded
}

describe('Independent MAA update preferences', () => {
  it('saves resource policies without changing core policies', async () => {
    const loaded = setup()
    for (const key of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[key] = []
    axios.patch.mockResolvedValue({ data: {} })
    loaded.value = true
    await nextTick()
    await store.flush_config_saves()
    store.maa_resource_auto_check_update = true
    store.maa_resource_auto_update = true
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
    expect(axios.patch.mock.calls[0][1]).toMatchObject({
      maa_resource_auto_check_update: true,
      maa_resource_auto_update: true
    })
    expect(axios.patch.mock.calls[0][1]).not.toHaveProperty('maa_auto_update')
    expect(store.maa_auto_update).toBe(false)
    expect(store.maa_auto_check_update).toBe(false)
    loaded.value = false
  })

  it('loads explicit independent preferences and migrates legacy combined checks', async () => {
    setup()
    const legacy = {
      free_blacklist: '',
      reload_room: '',
      maa_mall_buy: '',
      maa_mall_blacklist: '',
      maa_weekly_plan_active: '默认',
      favorite: '',
      reclamation_algorithm: {},
      secret_front: {},
      maa_auto_check_update: true
    }
    let config = { ...legacy, maa_resource_auto_check_update: false, maa_auto_update: true }
    axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/conf') ? config : { plans: ['默认'] }
    }))
    await store.load_config()
    expect(store.maa_auto_update).toBe(true)
    expect(store.maa_resource_auto_check_update).toBe(false)
    expect(store.maa_resource_auto_update).toBe(false)
    config = legacy
    await store.load_config()
    expect(store.maa_auto_check_update).toBe(true)
    expect(store.maa_resource_auto_check_update).toBe(true)
    expect(store.maa_auto_update).toBe(false)
    expect(store.maa_resource_auto_update).toBe(false)
    expect(axios.patch).not.toHaveBeenCalled()
  })
})
