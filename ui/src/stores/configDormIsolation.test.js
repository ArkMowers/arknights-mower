import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
let store
let loaded
afterEach(() => {
  loaded.value = false
  store.$dispose()
  vi.clearAllMocks()
})

function setup() {
  loaded = ref(false)
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', loaded)
  store = app.runWithContext(() => useConfigStore())
  for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
  axios.patch.mockResolvedValue({ data: {} })
  axios.post.mockResolvedValue({ data: { active: '默认', plan: [] } })
}

const groups = [
  ['空爆', '黑角', '初雪', '泥岩', '能天使', '年'],
  ['杜林', '黑角']
]
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

describe('宿舍隔离配置', () => {
  it('保存不限人数的多个分组，嵌套修改即时保存并携带到排班导出', async () => {
    setup()
    expect(store.dorm_isolation).toEqual([])
    loaded.value = true
    await nextTick()
    await store.flush_config_saves()
    store.dorm_isolation = structuredClone(groups)
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(1))
    expect(axios.patch.mock.lastCall[1]).toEqual({ dorm_isolation: groups })
    expect(store.build_advanced_settings().dorm_isolation).toEqual(groups)
    store.dorm_isolation[0].push('讯使')
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(2))
    expect(axios.patch.mock.lastCall[1].dorm_isolation[0]).toHaveLength(7)
    store.dorm_isolation.splice(1, 1)
    await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(3))
    expect(axios.patch.mock.lastCall[1].dorm_isolation).toHaveLength(1)
  })

  it('读取已保存分组，旧配置恢复为空分组', async () => {
    setup()
    axios.get.mockResolvedValue({ data: { ...response, dorm_isolation: groups } })
    await store.load_config()
    expect(store.dorm_isolation).toEqual(groups)
    expect(store.build_config().dorm_isolation).toEqual(groups)
    axios.get.mockResolvedValue({ data: response })
    await store.load_config()
    expect(store.dorm_isolation).toEqual([])
  })
})

it('组内恢复时间差默认75分钟，修改后保存并参与排班导出', async () => {
  setup()
  expect(store.group_mood_gap_threshold_minutes).toBe(75)
  axios.get.mockResolvedValue({ data: { ...response, group_mood_gap_threshold_minutes: 60 } })
  await store.load_config()
  expect(store.group_mood_gap_threshold_minutes).toBe(60)
  expect(store.build_advanced_settings().group_mood_gap_threshold_minutes).toBe(60)
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()
  store.group_mood_gap_threshold_minutes = 90
  await vi.waitFor(() =>
    expect(axios.patch.mock.lastCall[1]).toEqual({ group_mood_gap_threshold_minutes: 90 })
  )
  axios.get.mockResolvedValue({ data: response })
  await store.load_config()
  expect(store.group_mood_gap_threshold_minutes).toBe(75)
})

it('额外等待上限读取旧值并随修改保存和排班导出', async () => {
  setup()
  expect(store.group_mood_gap_max_extra_wait_hours).toBe(0)
  axios.get.mockResolvedValue({ data: { ...response, group_mood_gap_max_extra_wait_hours: 1.5 } })
  await store.load_config()
  expect(store.group_mood_gap_max_extra_wait_hours).toBe(1.5)
  expect(store.build_advanced_settings().group_mood_gap_max_extra_wait_hours).toBe(1.5)
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()
  store.group_mood_gap_max_extra_wait_hours = 0.5
  await vi.waitFor(() =>
    expect(axios.patch.mock.lastCall[1]).toEqual({ group_mood_gap_max_extra_wait_hours: 0.5 })
  )
  axios.get.mockResolvedValue({ data: response })
  await store.load_config()
  expect(store.group_mood_gap_max_extra_wait_hours).toBe(0)
})

it('延后回班排除组支持多选、即时保存及排班导出，旧配置默认不排除', async () => {
  setup()
  expect(store.group_mood_gap_exclusions).toEqual([])
  axios.get.mockResolvedValue({
    data: { ...response, group_mood_gap_exclusions: ['主表组', '副表组'] }
  })
  await store.load_config()
  expect(store.build_config().group_mood_gap_exclusions).toEqual(['主表组', '副表组'])
  expect(store.build_advanced_settings().group_mood_gap_exclusions).toEqual(['主表组', '副表组'])
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()
  store.group_mood_gap_exclusions.push('多绑组')
  await vi.waitFor(() =>
    expect(axios.patch.mock.lastCall[1]).toEqual({
      group_mood_gap_exclusions: ['主表组', '副表组', '多绑组']
    })
  )
  store.group_mood_gap_exclusions.splice(0, 2)
  await vi.waitFor(() =>
    expect(axios.patch.mock.lastCall[1]).toEqual({ group_mood_gap_exclusions: ['多绑组'] })
  )
  axios.get.mockResolvedValue({ data: response })
  await store.load_config()
  expect(store.group_mood_gap_exclusions).toEqual([])
})
