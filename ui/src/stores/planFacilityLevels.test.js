import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import axios from 'axios'
import { usePlanStore, useRescuePlanStore } from './plan'
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
let store
afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})
it('loads, edits and saves shared levels without manufacturing empty staffing', async () => {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  store = app.runWithContext(() => usePlanStore())
  store.plan = store.fill_empty({})
  const original = store.build_plan()
  original.facility_levels = { dormitory_1: 2, contact: 1 }
  axios.get.mockResolvedValue({ data: original })
  axios.post.mockResolvedValue({ data: {} })
  await store.load_plan()
  expect(store.facility_levels).toEqual(original.facility_levels)
  store.facility_levels.dormitory_1 = 4
  await store.save_plan()
  const saved = axios.post.mock.calls.at(-1)[1]
  expect(saved.facility_levels).toEqual({ dormitory_1: 4, contact: 1 })
  expect(saved.plan1.contact).toBeUndefined()
  saved.facility_levels.contact = 3
  expect(store.facility_levels.contact).toBe(1)
  delete original.facility_levels
  axios.get.mockResolvedValue({ data: original })
  await store.load_plan()
  expect(store.facility_levels).toEqual({})
})

const swapLevelCases = [
  ['both', { room_1_1: 2, room_1_2: 3 }, { room_1_1: 3, room_1_2: 2 }],
  ['source only', { room_1_1: 2 }, { room_1_2: 2 }],
  ['target only', { room_1_2: 3 }, { room_1_1: 3 }],
  ['inferred', {}, {}],
  ['unbuilt', { room_1_1: 0, room_1_2: 3 }, { room_1_1: 3, room_1_2: 0 }]
]

it.each(
  [false, true].flatMap((rescue) =>
    ['main', 0].flatMap((active) =>
      swapLevelCases.map(([label, levels, expected]) => ({
        rescue,
        active,
        label,
        levels,
        expected
      }))
    )
  )
)(
  'swaps and autosaves $label facility levels (rescue=$rescue, table=$active)',
  async ({ rescue, active, levels, expected }) => {
    const app = createApp({})
    app.use(createPinia())
    const loaded = ref(false)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => (rescue ? useRescuePlanStore() : usePlanStore()))
    const source = {
      conf: {},
      facility_levels: { ...levels, room_3_3: 1, dormitory_1: 4, contact: 1 },
      plan1: {
        room_1_1: { name: '制造站', product: 'gold', plans: [{ agent: '砾' }] },
        room_1_2: { name: '制造站', product: 'exp3', plans: [{ agent: '芬' }] }
      },
      backup_plans: [
        {
          plan: {
            room_1_1: { name: '制造站', product: 'exp3', plans: [{ agent: '香草' }] }
          },
          conf: {}
        },
        { plan: {}, conf: {} }
      ]
    }
    axios.get.mockResolvedValue({ data: structuredClone(source) })
    axios.post.mockResolvedValue({ data: {} })
    await store.load_plan()
    loaded.value = true
    await nextTick()
    await store.wait_for_plan_save()
    axios.post.mockClear()

    store.sub_plan = active
    store.swap_facilities('room_1_1', 'room_1_2')
    expect(store.facility_levels).toEqual({
      ...expected,
      room_3_3: 1,
      dormitory_1: 4,
      contact: 1
    })
    expect(store.plan.room_1_1.product).toBe('exp3')
    expect(store.plan.room_1_1.plans[0].agent).toBe('芬')
    expect(store.plan.room_1_2.product).toBe('gold')
    expect(store.plan.room_1_2.plans[0].agent).toBe('砾')
    expect(store.backup_plans[0].plan.room_1_2.plans[0].agent).toBe('香草')
    expect(store.backup_plans[1].plan.room_1_1.plans.every((slot) => !slot.agent)).toBe(true)

    await nextTick()
    await store.wait_for_plan_save()
    expect(axios.post).toHaveBeenCalled()
    expect(axios.post.mock.lastCall[0]).toMatch(new RegExp(`/${rescue ? 'rescue-plan' : 'plan'}$`))
    const saved = structuredClone(axios.post.mock.lastCall[1])
    expect(saved.facility_levels).toEqual(store.facility_levels)
    expect(saved.plan1.room_1_2.plans[0].agent).toBe('砾')
    expect(saved.backup_plans[0].plan.room_1_2.plans[0].agent).toBe('香草')

    axios.get.mockResolvedValue({ data: structuredClone(saved) })
    await store.load_plan()
    expect(store.build_plan()).toEqual(saved)
    store.swap_facilities('room_1_1', 'room_1_2')
    expect(store.facility_levels).toEqual(source.facility_levels)
    await nextTick()
    await store.wait_for_plan_save()
  }
)

it('roundtrips backup groups and normalizes legacy backup types', async () => {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  store = app.runWithContext(() => usePlanStore())
  store.plan = store.fill_empty({})
  const original = store.build_plan()
  original.backup_plans = [{ name: 'old', plan: {}, conf: {}, trigger: {}, task: {} }]
  delete original.backup_groups
  axios.get.mockResolvedValue({ data: original })
  axios.post.mockResolvedValue({ data: {} })
  await store.load_plan()
  expect(store.backup_groups.map((group) => group.id)).toEqual(['default'])
  expect(store.backup_plans[0].type).toBe('global')
  expect(store.backup_plans[0].group_ids).toEqual(['default'])
  store.backup_groups.push({
    id: 'rest',
    name: '休息',
    trigger: { left: 'True', operator: '==', right: 'True' }
  })
  store.backup_plans[0].group_ids = ['default', 'rest']
  store.backup_plans[0].type = 'exclusive'
  await store.save_plan()
  const saved = axios.post.mock.lastCall[1]
  expect(saved.backup_groups).toEqual(store.backup_groups)
  expect(saved.backup_plans[0]).toMatchObject({ group_ids: ['default', 'rest'], type: 'exclusive' })
  saved.backup_groups[1].name = 'changed'
  expect(store.backup_groups[1].name).toBe('休息')
})

it('preserves legacy exclusions and roundtrips explicit parallel and symmetric groups', async () => {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  store = app.runWithContext(() => usePlanStore())
  store.plan = store.fill_empty({})
  const original = store.build_plan()
  original.backup_groups = [
    { id: 'a', name: '贸易', trigger: {} },
    { id: 'b', name: '制造', trigger: {} }
  ]
  axios.get.mockResolvedValue({ data: original })
  axios.post.mockResolvedValue({ data: {} })
  await store.load_plan()
  expect(store.backup_groups.map((group) => group.exclusive_with)).toEqual([[], ['b'], ['a']])
  store.backup_groups[1].exclusive_with = []
  store.backup_groups[2].exclusive_with = []
  await store.save_plan()
  const saved = axios.post.mock.lastCall[1]
  axios.get.mockResolvedValue({ data: saved })
  await store.load_plan()
  expect(store.backup_groups.map((group) => group.exclusive_with)).toEqual([[], [], []])
  saved.backup_groups[1].exclusive_with.push('b')
  expect(store.backup_groups[1].exclusive_with).toEqual([])
})
