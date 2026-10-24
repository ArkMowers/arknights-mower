import { afterEach, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'
import { usePlanStore } from './plan'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
let config
let plan
let loaded

afterEach(() => {
  loaded.value = false
  config.$dispose()
  plan.$dispose()
  vi.clearAllMocks()
})

function setup() {
  loaded = ref(false)
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', loaded)
  config = app.runWithContext(() => useConfigStore())
  plan = app.runWithContext(() => usePlanStore())
  for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) config[name] = []
  plan.plan = plan.fill_empty({})
  plan.set_advanced_settings_source(() => config.build_advanced_settings())
  axios.patch.mockResolvedValue({ data: {} })
  axios.post.mockResolvedValue({ data: { active: '默认', plan: [] } })
}

it('测试心情计算默认关闭，单独保存开关并随排班导出', async () => {
  setup()
  expect(config.test_mood_calculation).toBe(false)
  loaded.value = true
  await nextTick()
  await config.flush_config_saves()
  axios.patch.mockClear()
  config.test_mood_calculation = true
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(1))
  expect(axios.patch.mock.lastCall[1]).toEqual({ test_mood_calculation: true })
  await plan.save_plan()
  expect(axios.post.mock.lastCall[1].advanced_settings.test_mood_calculation).toBe(true)
  config.test_mood_calculation = false
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(2))
  expect(axios.patch.mock.lastCall[1]).toEqual({ test_mood_calculation: false })
})

it('读取显式开启状态，旧配置不继承之前加载的开启状态', async () => {
  setup()
  const response = {
    free_blacklist: '',
    reload_room: '',
    maa_mall_buy: '',
    maa_mall_blacklist: '',
    favorite: '',
    reclamation_algorithm: {},
    secret_front: {},
    maa_weekly_plan: []
  }
  axios.get.mockResolvedValue({ data: { ...response, test_mood_calculation: true } })
  await config.load_config()
  expect(config.build_config().test_mood_calculation).toBe(true)
  axios.get.mockResolvedValue({ data: response })
  await config.load_config()
  expect(config.test_mood_calculation).toBe(false)
  expect(config.build_advanced_settings().test_mood_calculation).toBe(false)
})
