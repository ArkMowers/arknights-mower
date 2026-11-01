import { afterEach, expect, it, vi } from 'vitest'
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

it('saves the mastery screenshot choice independently and retains it when automatic mastery is disabled', async () => {
  setup()
  expect(store.save_mastery_screenshots).toBe(false)
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()
  store.save_mastery_screenshots = true
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
  expect(axios.patch.mock.lastCall[1]).toEqual({ save_mastery_screenshots: true })
  store.enable_mastery = false
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(2))
  expect(axios.patch.mock.lastCall[1]).toEqual({ enable_mastery: false })
  expect(store.build_config().save_mastery_screenshots).toBe(true)
})

it('loads the saved choice and defaults to disabled for old configurations', async () => {
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
  axios.get.mockResolvedValue({ data: { ...response, save_mastery_screenshots: true } })
  await store.load_config()
  expect(store.save_mastery_screenshots).toBe(true)
  axios.get.mockResolvedValue({ data: response })
  await store.load_config()
  expect(store.save_mastery_screenshots).toBe(false)
})
