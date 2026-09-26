import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
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

  it('saves stable crafter recovery priority without changing workshop selections', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
    expect(store.experimental_dorm_logic).toBe(false)
    expect(store.workshop_low_priority_rest).toBe(true)
    store.fodder_operators = ['空爆']
    axios.post.mockResolvedValue({ data: {} })
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    store.workshop_low_priority_rest = false
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    expect(axios.post.mock.calls[1][1]).toMatchObject({
      experimental_dorm_logic: false,
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
    store.screenshot_archive_limit_mb = 256
    store.theme = 'dark'
    store.runtime_platform = 'android'
    expect(store.build_config()).not.toHaveProperty('return_home_when_idle')
    expect(store.build_config()).not.toHaveProperty('exit_game_when_idle')
    expect(store.build_config()).not.toHaveProperty('close_simulator_when_idle')
    expect(store.build_config()).not.toHaveProperty('screenshot')
    expect(store.build_config().screenshot_archive_limit_mb).toBe(256)
    expect(store.build_config()).not.toHaveProperty('theme')
    for (const platform of ['linux', 'windows', 'darwin']) {
      store.runtime_platform = platform
      expect(store.build_config()).toMatchObject({
        return_home_when_idle: true,
        exit_game_when_idle: false,
        close_simulator_when_idle: false,
        screenshot: 2.5,
        screenshot_archive_limit_mb: 256,
        theme: 'dark'
      })
    }
  })
})

describe('low frame rate adaptation', () => {
  it.each([
    ['android', undefined, true],
    ['android', false, false],
    ['android', true, true],
    ['darwin', undefined, false],
    ['windows', undefined, false],
    ['linux', undefined, false],
    ['darwin', true, true]
  ])('loads %s with setting %s as %s and saves user changes', async (platform, value, expected) => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())
    // Minimal /conf response containing the fields that require string/object operations.
    const response = {
      runtime_platform: platform,
      low_frame_rate_mode: value,
      free_blacklist: '',
      reload_room: '',
      maa_mall_buy: '',
      maa_mall_blacklist: '',
      favorite: '',
      reclamation_algorithm: {},
      secret_front: {},
      maa_weekly_plan: []
    }
    axios.get.mockResolvedValue({ data: response })
    axios.post.mockResolvedValue({ data: {} })
    await store.load_config()
    expect(store.low_frame_rate_mode).toBe(expected)
    expect(store.build_config().low_frame_rate_mode).toBe(expected)
    loaded.value = true
    await nextTick()
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalled())
    store.low_frame_rate_mode = !expected
    await nextTick()
    const savedValue = store.performance_mode === 'auto' ? expected : !expected
    await vi.waitFor(() => expect(axios.post.mock.lastCall[1].low_frame_rate_mode).toBe(savedValue))
    loaded.value = false
    response.low_frame_rate_mode = axios.post.mock.lastCall[1].low_frame_rate_mode
    await store.load_config()
    expect(store.low_frame_rate_mode).toBe(savedValue)
  })

  it('loads and saves stage plan and mall settings with backward-compatible defaults', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())

    // 1. Old response with only maa_enable: 1
    const legacyResponse = {
      maa_enable: 1,
      free_blacklist: '',
      reload_room: '',
      maa_mall_buy: '',
      maa_mall_blacklist: '',
      favorite: '',
      reclamation_algorithm: {},
      secret_front: {},
      maa_weekly_plan: []
    }
    axios.get.mockResolvedValue({ data: legacyResponse })
    await store.load_config()
    expect(store.stage_plan_enable).toBe(true)
    expect(store.stage_plan_runner).toBe('maa')
    expect(store.maa_mall_enable).toBe(true)
    expect(store.maa_mall_mode).toBe('maa')

    // 2. Modify values and check build_config output
    store.stage_plan_enable = false
    store.stage_plan_runner = 'mower'
    store.maa_mall_enable = false
    store.maa_mall_mode = 'mower'
    store.maa_adb_path = '/custom/adb'
    let payload = store.build_config()
    expect(payload.maa_adb_path).toBe('/custom/adb')
    expect(payload.stage_plan_enable).toBe(false)
    expect(payload.stage_plan_runner).toBe('mower')
    expect(payload.maa_mall_enable).toBe(false)
    expect(payload.maa_mall_mode).toBe('mower')
    expect(payload.maa_enable).toBe(0)

    // 2b. stage_plan disabled but maa_mall executed by maa -> maa_enable must be 1
    store.stage_plan_enable = false
    store.stage_plan_runner = 'mower'
    store.maa_mall_enable = true
    store.maa_mall_mode = 'maa'
    payload = store.build_config()
    expect(payload.maa_enable).toBe(1)

    // 2c. stage_plan enabled with maa but maa_mall executed by mower -> maa_enable must be 1
    store.stage_plan_enable = true
    store.stage_plan_runner = 'maa'
    store.maa_mall_enable = true
    store.maa_mall_mode = 'mower'
    payload = store.build_config()
    expect(payload.maa_enable).toBe(1)

    // 3. New response with explicit settings
    const modernResponse = {
      stage_plan_enable: true,
      stage_plan_runner: 'mower',
      maa_mall_enable: false,
      maa_mall_mode: 'mower',
      free_blacklist: '',
      reload_room: '',
      maa_mall_buy: '',
      maa_mall_blacklist: '',
      favorite: '',
      reclamation_algorithm: {},
      secret_front: {},
      maa_weekly_plan: []
    }
    axios.get.mockResolvedValue({ data: modernResponse })
    await store.load_config()
    expect(store.stage_plan_enable).toBe(true)
    expect(store.stage_plan_runner).toBe('mower')
    expect(store.maa_mall_enable).toBe(false)
    expect(store.maa_mall_mode).toBe('mower')
  })
})

describe('factory product switching policy', () => {
  it('defaults drone loss tolerance to 30 seconds and serializes edits', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', ref(false))
    store = app.runWithContext(() => useConfigStore())
    axios.get.mockResolvedValue({
      data: {
        free_blacklist: '',
        reload_room: '',
        maa_mall_buy: '',
        maa_mall_blacklist: '',
        favorite: '',
        reclamation_algorithm: {},
        secret_front: {},
        maa_weekly_plan: []
      }
    })

    await store.load_config()
    expect(store.product_switching).toEqual({
      max_drones_per_switch: 0,
      grandet_mode: true,
      use_drones_when_leaving_orirock: true,
      direct_when_drones_insufficient: false,
      drone_loss_seconds: 30,
      waiting_seconds: 2
    })

    store.product_switching.max_drones_per_switch = 12
    store.product_switching.grandet_mode = false
    store.product_switching.use_drones_when_leaving_orirock = false
    store.product_switching.direct_when_drones_insufficient = true
    store.product_switching.drone_loss_seconds = 45
    store.product_switching.waiting_seconds = 4
    expect(store.build_config().product_switching).toEqual({
      max_drones_per_switch: 12,
      grandet_mode: false,
      use_drones_when_leaving_orirock: false,
      direct_when_drones_insufficient: true,
      drone_loss_seconds: 45,
      waiting_seconds: 4
    })
  })
})

describe('version update mood policy', () => {
  it('defaults to 80% and 12 hours and serializes user edits', () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', ref(false))
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []

    expect(store.version_update_resting_threshold).toBe(80)
    expect(store.version_update_threshold_advance_hours).toBe(12)
    store.version_update_resting_threshold = 85
    store.version_update_threshold_advance_hours = 18

    expect(store.build_config()).toMatchObject({
      version_update_resting_threshold: 0.85,
      version_update_threshold_advance_hours: 18
    })
  })
})
