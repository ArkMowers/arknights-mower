import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { usePlanStore } from './plan'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
let store
afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})
async function load(conf, backup = {}) {
  const app = createApp({})
  const pinia = createPinia()
  setActivePinia(pinia)
  app.use(pinia)
  app.provide('loaded', ref(false))
  store = app.runWithContext(() => usePlanStore())
  axios.get.mockResolvedValue({
    data: JSON.parse(
      JSON.stringify({ plan1: {}, conf, backup_plans: [{ plan: {}, conf: backup }] })
    )
  })
  await store.load_plan()
  return store.build_plan()
}
describe('心情上下限保存', () => {
  it('旧排班保留令夕规则，新字段默认不覆盖', async () => {
    const result = await load({ ling_xi: 2 })
    expect(result.conf.ling_xi).toBe(2)
    expect(result.conf.mood_limits).toBeNull()
    expect(result.conf.operator_mood_limits).toEqual({})
    expect(result.backup_plans[0].conf.mood_limits).toBeNull()
  })
  it('主副表独立保存、修改和清除上下限', async () => {
    const main = {
      mood_limits: { lower: 2, upper: 20 },
      operator_mood_limits: { 令: { lower: 0, upper: 12 } }
    }
    const backup = { mood_limits: null, operator_mood_limits: { 红: { lower: 4, upper: 16 } } }
    const result = await load(main, backup)
    expect(result.conf).toMatchObject(main)
    expect(result.backup_plans[0].conf).toMatchObject(backup)
    store.operator_mood_limits.令.upper = 14
    expect(result.conf.operator_mood_limits.令.upper).toBe(12)
    expect(store.build_plan().conf.operator_mood_limits.令.upper).toBe(14)
    store.mood_limits = null
    store.operator_mood_limits = {}
    expect(store.build_plan().conf.mood_limits).toBeNull()
    expect(store.build_plan().conf.operator_mood_limits).toEqual({})
    expect(store.build_plan().backup_plans[0].conf.operator_mood_limits).toEqual(
      backup.operator_mood_limits
    )
  })
})
