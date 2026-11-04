import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
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
    const settings = { http_proxy: '', github_proxy: '', github_token: '' }
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

describe('GitHub Token settings', () => {
  it('persists the token with proxy settings and supports clearing it', async () => {
    const settings = { http_proxy: '', github_proxy: 'https://mirror.example/', github_token: '' }
    state.client = {
      get: vi.fn(async () => ({ data: { ok: true, ...settings } })),
      post: vi.fn(async (url, values) => ({ data: { ok: true, ...values } }))
    }
    const component = Component.setup({}, { expose: () => {} })
    await state.mounted[0]()
    component.githubToken.value = 'github_pat_test'
    component.changed()
    await component.save()
    expect(state.client.post).toHaveBeenLastCalledWith(
      expect.stringMatching(/settings$/),
      { ...settings, github_token: 'github_pat_test' },
      expect.any(Object)
    )
    expect(component.dirty.value).toBe(false)
    component.githubToken.value = ''
    component.changed()
    await component.save()
    expect(state.client.post).toHaveBeenLastCalledWith(
      expect.stringMatching(/settings$/),
      settings,
      expect.any(Object)
    )
  })

  it('rejects connection results for a token changed by another instance', async () => {
    const settings = { http_proxy: '', github_proxy: '', github_token: 'github_pat_test' }
    state.client = {
      get: vi.fn(async () => ({ data: { ok: true, ...settings } })),
      post: vi.fn(async () => ({
        data: {
          ok: true,
          settings: { ...settings, github_token: 'other_token' },
          results: [{ ok: true }]
        }
      }))
    }
    const component = Component.setup({}, { expose: () => {} })
    await state.mounted[0]()
    await component.testConnection()
    expect(component.results.value).toEqual([])
    expect(component.error.value).toContain('其他实例修改')
  })
})

describe('GitHub Token input', () => {
  it('renders the password field and public-repository token instructions', async () => {
    state.client = { get: vi.fn() }
    const html = await renderToString(createSSRApp(Component))
    expect(html).toContain('aria-label="GitHub Token"')
    expect(html).toContain('type="password"')
    expect(html).toContain('https://github.com/settings/personal-access-tokens/new')
    expect(html).toContain('Public repositories')
    expect(html).toContain('不添加额外权限')
    expect(html).toContain('不经过下载代理站点')
  })
})
