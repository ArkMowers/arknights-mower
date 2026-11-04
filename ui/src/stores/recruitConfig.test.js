import { afterEach, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
let store
afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})

function setup() {
  const loaded = ref(false)
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', loaded)
  store = app.runWithContext(() => useConfigStore())
  for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
  return loaded
}

it('defaults robot automation off and saves it independently of tag preservation', async () => {
  const loaded = setup()
  expect(store.recruit_auto_robot).toBe(false)
  expect(store.build_config().recruit_auto_robot).toBe(false)
  expect(store.recruit_robot).toBe(true)
  axios.patch.mockResolvedValue({ data: {} })
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()

  store.recruit_auto_robot = true
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(1))
  expect(axios.patch.mock.calls[0][1]).toEqual({ recruit_auto_robot: true })
  expect(store.recruit_robot).toBe(true)

  store.recruit_auto_robot = false
  await vi.waitFor(() => expect(axios.patch).toHaveBeenCalledTimes(2))
  expect(axios.patch.mock.calls[1][1]).toEqual({ recruit_auto_robot: false })
  loaded.value = false
})

it.each([true, false, undefined])(
  'loads robot automation %s from saved settings',
  async (saved) => {
    setup()
    store.recruit_auto_robot = true
    axios.get.mockResolvedValue({
      data: {
        free_blacklist: '',
        reload_room: '',
        maa_mall_buy: '',
        maa_mall_blacklist: '',
        favorite: '',
        reclamation_algorithm: {},
        secret_front: {},
        maa_weekly_plan: [],
        maa_weekly_plan_active: '默认',
        recruit_robot: false,
        recruit_auto_robot: saved
      }
    })

    await store.load_config()

    expect(store.recruit_auto_robot).toBe(saved ?? false)
    expect(store.build_config().recruit_auto_robot).toBe(saved ?? false)
    expect(store.recruit_robot).toBe(false)
    expect(axios.patch).not.toHaveBeenCalled()
  }
)
