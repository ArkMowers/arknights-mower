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

function setup() {
  const app = createApp({})
  const pinia = createPinia()
  setActivePinia(pinia)
  app.use(pinia)
  const loaded = ref(false)
  app.provide('loaded', loaded)
  store = app.runWithContext(() => usePlanStore())
  return loaded
}

describe('宿舍休息候补配置', () => {
  it('旧排班缺少候补字段时默认为空，原低优不迁移', async () => {
    setup()
    axios.get.mockResolvedValue({
      data: {
        conf: { resting_priority: '斯卡蒂' },
        plan1: {},
        backup_plans: [{ plan: {}, conf: { resting_priority: '幽灵鲨' } }]
      }
    })
    await store.load_plan()
    const saved = store.build_plan()
    expect(saved.conf.resting_priority).toBe('斯卡蒂')
    expect(saved.conf.resting_standby).toBe('')
    expect(saved.conf.dorm_order).toBe('dormitory_1,dormitory_2,dormitory_3,dormitory_4')
    expect(saved.backup_plans[0].conf.resting_priority).toBe('幽灵鲨')
    expect(saved.backup_plans[0].conf.resting_standby).toBe('')
    expect(saved.backup_plans[0].conf.dorm_order).toBe(
      'dormitory_1,dormitory_2,dormitory_3,dormitory_4'
    )
    expect(saved.backup_plans[0].exit_trigger_timing).toBeNull()
  })

  it('主副表候补名单和宿舍顺序导入后独立保存', async () => {
    const loaded = setup()
    axios.get.mockResolvedValue({
      data: {
        conf: { resting_standby: '斯卡蒂', dorm_order: 'dormitory_1_3' },
        plan1: {},
        backup_plans: [
          {
            plan: {},
            conf: { resting_standby: '幽灵鲨', dorm_order: 'dormitory_2_2' }
          }
        ]
      }
    })
    await store.load_plan()
    expect(store.resting_standby).toEqual(['斯卡蒂'])
    expect(store.dorm_order).toEqual(['dormitory_1', 'dormitory_2', 'dormitory_3', 'dormitory_4'])
    expect(store.backup_plans[0].conf.resting_standby).toEqual(['幽灵鲨'])
    expect(store.backup_plans[0].conf.dorm_order).toEqual([
      'dormitory_2',
      'dormitory_1',
      'dormitory_3',
      'dormitory_4'
    ])
    axios.post.mockResolvedValue({ data: {} })
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    store.resting_standby.push('乌尔比安')
    store.dorm_order = ['dormitory_4', 'dormitory_1', 'dormitory_2', 'dormitory_3']
    store.backup_plans[0].conf.resting_standby.push('安哲拉')
    store.backup_plans[0].conf.dorm_order = [
      'dormitory_3',
      'dormitory_2',
      'dormitory_1',
      'dormitory_4'
    ]
    store.backup_plans[0].trigger_timing = 'BEFORE_DORM'
    store.backup_plans[0].exit_trigger_timing = 'BEFORE_WORK'
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    const sent = axios.post.mock.calls[1][1]
    expect(sent.conf.resting_standby).toBe('斯卡蒂,乌尔比安')
    expect(sent.conf.dorm_order).toBe('dormitory_4,dormitory_1,dormitory_2,dormitory_3')
    expect(sent.backup_plans[0].conf.resting_standby).toBe('幽灵鲨,安哲拉')
    expect(sent.backup_plans[0].conf.dorm_order).toBe(
      'dormitory_3,dormitory_2,dormitory_1,dormitory_4'
    )
    expect(sent.backup_plans[0].trigger_timing).toBe('BEFORE_DORM')
    expect(sent.backup_plans[0].exit_trigger_timing).toBe('BEFORE_WORK')
    expect(sent.conf.resting_priority).toBe('')
    loaded.value = false
  })
})
