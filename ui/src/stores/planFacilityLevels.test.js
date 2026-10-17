import { createApp, ref } from 'vue'
import { createPinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import axios from 'axios'
import { usePlanStore } from './plan'
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
