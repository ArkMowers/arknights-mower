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
