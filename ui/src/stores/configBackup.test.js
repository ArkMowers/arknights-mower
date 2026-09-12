import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'
import { usePlanStore } from './plan'

vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn() } }))
let stores = []
afterEach(() => {
  for (const store of stores) store.$dispose()
  stores = []
  vi.clearAllMocks()
})

function setup() {
  const loaded = ref(false)
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', loaded)
  const config = app.runWithContext(() => useConfigStore())
  const plan = app.runWithContext(() => usePlanStore())
  stores = [config, plan]
  for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) config[name] = []
  plan.plan = plan.fill_empty({})
  axios.post.mockResolvedValue({ data: {} })
  return { config, plan, loaded }
}

describe('configuration restore autosave coordination', () => {
  it('clears the browser dorm order after a changed plan is saved', async () => {
    const { config, plan } = setup()
    config.dorm_order = ['dormitory_1_2']
    axios.post.mockResolvedValueOnce({ data: { dorm_order_reset: true } })
    await plan.save_plan()
    expect(config.dorm_order).toEqual([])
    config.dorm_order = ['dormitory_2_3']
    axios.post.mockResolvedValueOnce({ data: { dorm_order_reset: false } })
    await plan.save_plan()
    expect(config.dorm_order).toEqual(['dormitory_2_3'])
  })

  it('preserves the browser dorm order when saving a plan fails', async () => {
    const { config, plan } = setup()
    config.dorm_order = ['dormitory_1_2']
    axios.post.mockRejectedValueOnce(new Error('offline'))
    await expect(plan.save_plan()).rejects.toThrow('offline')
    expect(config.dorm_order).toEqual(['dormitory_1_2'])
  })

  it('flushes the latest drafts then prevents old stores from overwriting restored values', async () => {
    const { config, plan, loaded } = setup()
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    config.autosave_paused = true
    plan.autosave_paused = true
    await nextTick()
    config.account = 'latest draft'
    await config.flush_pending_saves()
    await plan.save_plan()
    expect(axios.post.mock.calls.findLast(([url]) => url.endsWith('/conf'))[1].account).toBe(
      'latest draft'
    )
    const count = axios.post.mock.calls.length
    config.account = 'stale value'
    plan.ling_xi = 2
    await nextTick()
    expect(axios.post).toHaveBeenCalledTimes(count)
  })

  it('preserves imported dorm order at startup and resets it only for a new plan', async () => {
    const { config, plan } = setup()
    axios.get.mockResolvedValue({
      data: { conf: { ling_xi: 1 }, plan1: {}, backup_plans: [] }
    })
    config.dorm_order = ['dormitory_3', 'dormitory_1']
    await plan.load_plan({ resetDormOrder: false })
    expect(config.dorm_order).toEqual(['dormitory_3', 'dormitory_1'])
    await plan.load_plan()
    expect(config.dorm_order).toEqual([])
  })
})
