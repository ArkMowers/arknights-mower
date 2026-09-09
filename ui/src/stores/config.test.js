import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'

vi.mock('axios', () => ({ default: { post: vi.fn() } }))
let pinia
let store
afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})

describe('workshop config autosave', () => {
  it('tracks nested edits and sends the latest manual draft with the acknowledged revision', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const loaded = ref(false)
    const app = createApp({})
    app.use(pinia)
    app.provide('loaded', loaded)
    store = app.runWithContext(() => useConfigStore())
    for (const name of ['reload_room', 'maa_mall_buy', 'maa_mall_blacklist']) store[name] = []
    store.workshop_settings = [{ operator: '赫拉格', source: 'mastery' }]
    const replies = []
    axios.post.mockImplementation(
      (url, sent) =>
        new Promise((resolve) => {
          replies.push(() =>
            resolve({
              data: {
                workshop_manual_settings: sent.workshop_manual_settings,
                workshop_manual_revision: sent.workshop_manual_settings_revision + 1,
                workshop_settings: [{ operator: '赫拉格', source: 'mastery' }],
                workshop_generation: 1
              }
            })
          )
        })
    )
    loaded.value = true
    await nextTick()
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    store.workshop_manual_settings.push({ operator: '空爆', items: [] })
    await nextTick()
    replies.shift()()
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    const sent = axios.post.mock.calls[1][1]
    expect(sent.workshop_manual_settings).toEqual([{ operator: '空爆', items: [] }])
    expect(sent.workshop_manual_settings_revision).toBe(1)
    expect(sent).not.toHaveProperty('workshop_settings')
    expect(sent).not.toHaveProperty('workshop_manual_backup')
    loaded.value = false
    axios.post.mockResolvedValue({ data: {} })
    replies.shift()()
  })
})
