import { afterEach, describe, expect, it, vi } from 'vitest'
import Component from './NetworkSettings.vue'

const state = vi.hoisted(() => ({ client: null, mounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (callback) => state.mounted.push(callback),
  onBeforeUnmount: () => {}
}))

afterEach(() => {
  state.mounted = []
})

describe('network connection test', () => {
  it('allows the five download candidates to finish and displays the selected station', async () => {
    const settings = { http_proxy: '', github_proxy: '' }
    const result = { ok: true, message: '默认站点 edgeone.gh-proxy.org 回退连接成功' }
    state.client = {
      get: vi.fn(async () => ({ data: { ok: true, ...settings } })),
      post: vi.fn(async () => ({ data: { ok: true, settings, results: [result] } }))
    }
    const component = Component.setup({}, { expose: () => {} })
    await state.mounted[0]()
    await component.testConnection()

    expect(state.client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/network\/test$/),
      {},
      expect.objectContaining({ timeout: expect.any(Number) })
    )
    expect(state.client.post.mock.calls[0][2].timeout).toBeGreaterThan(100000)
    expect(component.results.value).toEqual([result])
    expect(component.error.value).toBe('')
    expect(component.testing.value).toBe(false)
  })
})
