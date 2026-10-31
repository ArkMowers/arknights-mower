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

it('saves the mail cleanup choice independently and retains it when collection is disabled', async () => {
  setup()
  expect(store.mail_skip_clear_read).toBe(true)
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()
  store.mail_skip_clear_read = false
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledOnce())
  expect(axios.patch.mock.lastCall[1]).toEqual({ mail_skip_clear_read: false })
  store.check_mail_enable = false
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(2))
  expect(axios.patch.mock.lastCall[1]).toEqual({ check_mail_enable: false })
  expect(store.build_config().mail_skip_clear_read).toBe(false)
})

it('loads an explicit cleanup choice and defaults to retaining mail for old configurations', async () => {
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
  axios.get.mockResolvedValue({ data: { ...response, mail_skip_clear_read: false } })
  await store.load_config()
  expect(store.mail_skip_clear_read).toBe(false)
  axios.get.mockResolvedValue({ data: response })
  await store.load_config()
  expect(store.mail_skip_clear_read).toBe(true)
})
