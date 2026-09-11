import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { post: vi.fn() } }))
let pinia
let store
afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})

describe('workshop config autosave', () => {
  it('defaults T2 protection off and saves it without changing manual materials', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
    expect(store.workshop_protect_t2_device_rock).toBe(false)
    const manual = [{ operator: '空爆', items: [{ item_names: ['固源岩组', '异铁组'] }] }]
    store.workshop_manual_settings = manual
    axios.post.mockResolvedValue({ data: {} })
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    store.workshop_protect_t2_device_rock = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    expect(axios.post.mock.calls[1][1]).toMatchObject({
      workshop_protect_t2_device_rock: true,
      workshop_manual_settings: manual
    })
    loaded.value = false
  })

  it('saves turning off crafter recovery priority without changing workshop selections', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
    expect(store.workshop_low_priority_rest).toBe(true)
    store.fodder_operators = ['空爆']
    axios.post.mockResolvedValue({ data: {} })
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    store.workshop_low_priority_rest = false
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    expect(axios.post.mock.calls[1][1]).toMatchObject({
      workshop_low_priority_rest: false,
      fodder_operators: ['空爆']
    })
    loaded.value = false
  })

  it('tracks nested edits and sends the latest manual draft with the acknowledged revision', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
    store.workshop_settings = [{ operator: '赫拉格', source: 'mastery' }]
    const replies = []
    axios.post.mockImplementation(
      (url, sent) =>
        new Promise((resolve) => {
          replies.push(() =>
            resolve({
              data: {
                workshop_manual_settings: sent.workshop_manual_settings,
                workshop_manual_revision: sent.workshop_manual_settings_revision + 1,
                workshop_settings: [{ operator: '赫拉格', source: 'mastery' }],
                workshop_generation: 1
              }
            })
          )
        })
    )
    loaded.value = true
    await nextTick()
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    store.workshop_manual_settings.push({ operator: '空爆', items: [] })
    await nextTick()
    replies.shift()()
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    const sent = axios.post.mock.calls[1][1]
    expect(sent.workshop_manual_settings).toEqual([{ operator: '空爆', items: [] }])
    expect(sent.workshop_manual_settings_revision).toBe(1)
    expect(sent).not.toHaveProperty('workshop_settings')
    expect(sent).not.toHaveProperty('workshop_manual_backup')
    loaded.value = false
    axios.post.mockResolvedValue({ data: {} })
    replies.shift()()
  })
})

describe('weekly plan inventory config', () => {
  it('sends source rules before switching and replaces them with target rules', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())

    store.maa_weekly_plan_active = '活动'
    store.maa_weekly_plan_options = ['活动', '常规']
    store.maa_stage_inventory_enable = true
    store.maa_stage_limit_rules = [
      {
        stage: 'ACT-1',
        operator: 'and',
        enabled: true,
        items: [{ item_id: '30012', item_name: '固源岩', limit: 100 }]
      }
    ]
    const targetInventory = {
      enabled: false,
      limit_rules: [
        {
          stage: '1-7',
          operator: 'and',
          enabled: true,
          items: [{ item_id: '30011', item_name: '源岩', limit: 300 }]
        }
      ],
      ratio_rules: []
    }
    axios.post.mockResolvedValue({
      data: {
        active: '常规',
        plan: [],
        inventory_config: targetInventory,
        activity_fallbacks: {},
        activity_fallback_switch_times: {},
        activity_plan_end_times: {}
      }
    })

    await store.update_weekly_plan_active('常规')

    expect(axios.post).toHaveBeenCalledTimes(1)
    expect(axios.post.mock.calls[0][0]).toContain('/weekly-plans/active')
    expect(axios.post.mock.calls[0][1]).toMatchObject({
      active: '常规',
      source_inventory_config: {
        enabled: true,
        limit_rules: [
          {
            stage: 'ACT-1',
            items: [{ item_id: '30012', limit: 100 }]
          }
        ],
        ratio_rules: []
      }
    })
    expect(store.maa_weekly_plan_active).toBe('常规')
    expect(store.maa_stage_inventory_enable).toBe(false)
    expect(store.maa_stage_limit_rules).toEqual(targetInventory.limit_rules)
  })
})

describe('native Android setting ownership', () => {
  it('omits native idle, screenshot and theme fields only on Android', () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', ref(false))
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
    store.return_home_when_idle = true
    store.screenshot = 2.5
    store.theme = 'dark'
    store.runtime_platform = 'android'
    expect(store.build_config()).not.toHaveProperty('return_home_when_idle')
    expect(store.build_config()).not.toHaveProperty('exit_game_when_idle')
    expect(store.build_config()).not.toHaveProperty('close_simulator_when_idle')
    expect(store.build_config()).not.toHaveProperty('screenshot')
    expect(store.build_config()).not.toHaveProperty('theme')
    for (const platform of ['linux', 'windows', 'darwin']) {
      store.runtime_platform = platform
      expect(store.build_config()).toMatchObject({
        return_home_when_idle: true,
        exit_game_when_idle: false,
        close_simulator_when_idle: false,
        screenshot: 2.5,
        theme: 'dark'
      })
    }
  })
})
