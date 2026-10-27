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

describe('MAA reward and long task config', () => {
  it('saves signin, ordered recruits, BlackFlow preparation and reclamation options', async () => {
    const loaded = setup()
    for (const key of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[key] = []
    expect(store.maa_signinevent).toBe(false)
    axios.patch.mockResolvedValue({ data: {} })
    loaded.value = true
    await nextTick()
    await store.flush_config_saves()
    store.maa_signinevent = true
    store.rogue = {
      core_char_list: [{ name: '机械师', use_support: true }],
      mode: 30003,
      blackflow_start_animals: ['swaddled_cat', 'swaddled_cat'],
      blackflow_start_rewards: 3,
      collectible_mode_roles: '坚不可摧',
      collectible_mode_core_char_list: [{ name: '机械师', use_support: false }]
    }
    store.rcl = { mode: 0, clear_store: true }
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
    const saved = axios.patch.mock.calls[0][1]
    expect(saved).toMatchObject({ maa_signinevent: true, rogue: store.rogue, rcl: store.rcl })
    loaded.value = false
    axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/conf')
        ? {
            ...saved,
            free_blacklist: '',
            reload_room: '',
            maa_mall_buy: '',
            maa_mall_blacklist: '',
            favorite: '',
            maa_weekly_plan_active: '默认',
            reclamation_algorithm: {},
            secret_front: {}
          }
        : { plans: ['默认'] }
    }))
    await store.load_config()
    expect(store.maa_signinevent).toBe(true)
    expect(store.rogue.blackflow_start_animals).toEqual(['swaddled_cat', 'swaddled_cat'])
    expect(store.rcl.clear_store).toBe(true)
  })
  it('defaults missing signin switch to off when loading old config', async () => {
    setup()
    store.maa_signinevent = true
    axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/conf')
        ? {
            free_blacklist: '',
            reload_room: '',
            maa_mall_buy: '',
            maa_mall_blacklist: '',
            favorite: '',
            maa_weekly_plan_active: '默认',
            reclamation_algorithm: {},
            secret_front: {}
          }
        : { plans: ['默认'] }
    }))
    await store.load_config()
    expect(store.maa_signinevent).toBe(false)
    expect(axios.patch).not.toHaveBeenCalled()
  })
})
