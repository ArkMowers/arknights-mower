import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import axios from 'axios'
import { usePlanStore, useRescuePlanStore } from './plan'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
const stores = []
afterEach(() => {
  stores.splice(0).forEach((store) => store.$dispose())
  vi.clearAllMocks()
})

it.each([
  [false, 'main'],
  [false, 0],
  [true, 'main'],
  [true, 0]
])('设施换位后保存加速目标，救急 %s，当前表 %s', async (rescue, active) => {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  const config = app.runWithContext(() => useConfigStore())
  const plan = app.runWithContext(() => (rescue ? useRescuePlanStore() : usePlanStore()))
  stores.push(config, plan)
  const source = {
    conf: {},
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [{ agent: '砾' }] },
      room_1_2: { name: '制造站', product: 'exp3', plans: [{ agent: '芬' }] }
    },
    backup_plans: [
      { plan: {}, conf: { drone_room: 'room_1_2', drone_count_limit: 150 } },
      { plan: {}, conf: { drone_room: '' } },
      { plan: {}, conf: {} }
    ]
  }
  axios.get.mockResolvedValue({ data: structuredClone(source) })
  axios.post.mockResolvedValue({ data: {} })
  await plan.load_plan()
  config.drone_room = 'room_1_1'
  config.drone_count_limit = 130
  config.drone_interval = 2.5
  plan.set_advanced_settings_source(() => config.build_advanced_settings())
  plan.sub_plan = active
  plan.swap_facilities('room_1_1', 'room_1_2', config)
  expect(plan.plan.room_1_2.plans[0].agent).toBe('砾')
  expect(config.drone_room).toBe(rescue ? 'room_1_1' : 'room_1_2')
  expect(plan.backup_plans[0].conf.drone_room).toBe('room_1_1')
  expect(plan.backup_plans[1].conf.drone_room).toBe('')
  expect(plan.backup_plans[2].conf.drone_room).toBeUndefined()
  await plan.save_plan()
  const saved = axios.post.mock.lastCall[1]
  expect(saved.backup_plans[0].conf).toMatchObject({
    drone_room: 'room_1_1',
    drone_count_limit: 150
  })
  expect(saved.backup_plans[1].conf.drone_room).toBe('')
  expect(saved.backup_plans[2].conf.drone_room).toBeUndefined()
  if (rescue) expect(saved).not.toHaveProperty('advanced_settings')
  else
    expect(saved.advanced_settings).toMatchObject({
      drone_room: 'room_1_2',
      drone_count_limit: 130,
      drone_interval: 2.5
    })
  axios.get.mockResolvedValue({ data: structuredClone(saved) })
  await plan.load_plan()
  expect(plan.build_plan()).toEqual(saved)
})
