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
  it('starts with an editable activity shop blacklist and optional switching disabled', () => {
    setup()
    expect(store.maa_event_shop.blacklist).toEqual(['数据增补条', '数据增补仪', '家具零件'])
    expect(store.maa_event_shop.switch_source).toBe('')
    store.maa_event_shop.blacklist = []
    expect(store.maa_event_shop.blacklist).toEqual([])
  })
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
    store.paradox = { scripts: [{ id: 'a'.repeat(64) }], run_id: 'new-round' }
    store.maa_event_shop = {
      enable: true,
      activity: '测试活动',
      custom_entry: true,
      x: 900,
      y: 400,
      confirm_text: '兑换处',
      blacklist: ['家具'],
      switch_source: '活动方案'
    }
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
    const saved = axios.patch.mock.calls[0][1]
    expect(saved).toMatchObject({
      maa_signinevent: true,
      rogue: store.rogue,
      rcl: store.rcl,
      paradox: store.paradox,
      maa_event_shop: store.maa_event_shop
    })
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
    expect(store.paradox.scripts).toEqual([{ id: 'a'.repeat(64) }])
    expect(store.maa_event_shop.switch_source).toBe('活动方案')
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
    expect(store.paradox).toEqual({ scripts: [], run_id: '' })
    expect(store.maa_event_shop.enable).toBe(false)
    expect(axios.patch).not.toHaveBeenCalled()
  })
})
