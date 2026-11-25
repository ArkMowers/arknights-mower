import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import axios from 'axios'
import { CONFIG_GENERATION_HEADER } from '@/composables/configProfiles'
import Component from './MaaSss.vue'

const state = vi.hoisted(() => ({
  config: {},
  client: null,
  error: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
  flush: vi.fn()
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: (key) => (key === 'axios' ? state.client : false),
  onMounted: () => {},
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('@/stores/config', () => ({
  useConfigStore: () => ({ ...state.config, flush_config_saves: state.flush })
}))
vi.mock('pinia', () => ({ storeToRefs: (store) => store }))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useMessage: () => ({ error: state.error, warning: state.warning, success: state.success })
}))
let scope
let component
const first = { id: 'a'.repeat(64), stage_name: '保全关卡一', title: '作业一' }
const second = { id: 'b'.repeat(64), stage_name: '保全关卡二', title: '作业二' }
beforeEach(() => {
  vi.clearAllMocks()
  state.config = { copilot: ref({ scripts: [] }), sss: ref({ scripts: [] }) }
  state.client = {
    get: vi.fn(async () => ({ data: { scripts: [first, second] } })),
    post: vi.fn(async () => ({ data: first })),
    delete: vi.fn(async () => ({ data: { ok: true } }))
  }
  scope = effectScope()
  component = scope.run(() => Component.setup({}, { expose: () => {} }))
})
afterEach(() => {
  scope.stop()
  vi.unstubAllGlobals()
})

describe('SSS library and per-item rounds', () => {
  it('uses the current shared client credentials when a custom upload starts', async () => {
    const requests = []
    state.client = axios.create({
      adapter: async (config) => {
        requests.push(config)
        return {
          data: config.method === 'post' ? first : { scripts: [first] },
          status: 200,
          statusText: 'OK',
          headers: {},
          config
        }
      }
    })
    component = scope.run(() => Component.setup({}, { expose: () => {} }))
    state.client.defaults.headers.common.token = 'page-token'
    for (const generation of ['activated-page-generation', 'reloaded-page-generation']) {
      state.client.defaults.headers.common[CONFIG_GENERATION_HEADER] = generation
      const finish = vi.fn()
      const failure = vi.fn()
      await component.upload({
        file: { file: new Blob(['{}']) },
        onFinish: finish,
        onError: failure
      })
      const request = requests.filter((item) => item.method === 'post').at(-1)
      expect(request.url).toMatch(/\/sss-copilot$/)
      expect(request.data.get('copilot')).toBeInstanceOf(Blob)
      expect(request.headers.get('token')).toBe('page-token')
      expect(request.headers.get(CONFIG_GENERATION_HEADER)).toBe(generation)
      expect(finish).toHaveBeenCalledOnce()
      expect(failure).not.toHaveBeenCalled()
    }
  })
  it.each([
    'prts://123',
    '  prts://123  ',
    'maa://123',
    '123',
    'https://prts.plus/operation/123',
    'https://prts.plus/operation/123/?source=share#details'
  ])(
    'downloads %s through the existing proxy and imports into the separate SSS library',
    async (code) => {
      state.client.get.mockImplementation(async (url) => ({
        data: url.includes('/network/')
          ? { data: { content: '{"type":"SSS","stage_name":"保全"}' } }
          : { scripts: [first] }
      }))
      component.code.value = code
      await component.download()
      expect(state.client.get).toHaveBeenCalledWith(
        expect.stringMatching(/\/network\/maa-copilot\/123$/)
      )
      expect(state.client.post).toHaveBeenCalledWith(
        expect.stringMatching(/\/sss-copilot$/),
        expect.any(FormData)
      )
      expect(state.client.post.mock.calls[0][1].get('copilot')).toBeInstanceOf(Blob)
      expect(state.config.sss.value.scripts).toEqual([{ id: first.id, type: 1, ec: 1, times: 1 }])
      expect(component.loading.value).toBe(false)
    }
  )
  function mock_set(ids = ['456', '789', '456']) {
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/network/maa-copilot-set/123')) return { data: { ids } }
      if (url.includes('/network/maa-copilot/')) {
        return {
          data: {
            data: {
              content: JSON.stringify({
                type: 'SSS',
                stage_name: url.endsWith('789') ? 'second' : 'first',
                actions: []
              })
            }
          }
        }
      }
      return { data: { scripts: [first, second] } }
    })
    state.client.post.mockImplementation(async (_url, form) => {
      const content = JSON.parse(await form.get('copilot').text())
      return { data: content.stage_name === 'second' ? second : first }
    })
  }
  it('imports an operation set in member order and preserves repeated entries', async () => {
    mock_set()
    component.add_script(second.id)
    const original = { ...state.config.sss.value.scripts[0] }
    component.code.value = '  S123  '
    await component.download()
    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/network\/maa-copilot-set\/123$/)
    )
    expect(
      state.client.get.mock.calls
        .filter(([url]) => url.includes('/network/maa-copilot/'))
        .map(([url]) => url.split('/').at(-1))
    ).toEqual(['456', '789'])
    expect(state.config.sss.value.scripts).toEqual([
      original,
      { id: first.id, type: 1, ec: 1, times: 1 },
      { id: second.id, type: 1, ec: 1, times: 1 },
      { id: first.id, type: 1, ec: 1, times: 1 }
    ])
    expect(state.success).toHaveBeenCalledOnce()
    expect(state.error).not.toHaveBeenCalled()
    expect(component.code.value).toBe('')
    expect(component.loading.value).toBe(false)
  })
  it('routes ordinary members after the SSS queue reaches capacity in a large set', async () => {
    mock_set([...Array(33).fill('456'), '789'])
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) =>
      url.endsWith('/network/maa-copilot/789')
        ? { data: { data: { content: '{"stage_name":"second","actions":[]}' } } }
        : get(url)
    )
    component.code.value = 's123'
    await component.download()
    expect(state.config.sss.value.scripts).toHaveLength(32)
    expect(state.config.copilot.value.scripts).toEqual([
      { id: second.id, is_raid: false, nav_name_override: '' }
    ])
    expect(state.client.post).toHaveBeenCalledTimes(2)
    expect(state.client.post.mock.calls.at(-1)[0]).toMatch(/\/maa-copilot$/)
    expect(component.failures.value).toEqual([
      expect.stringContaining('第 33 份（456）：保全派驻队列已满')
    ])
    expect(component.selected.value).toBe(first.id)
    expect(state.warning).toHaveBeenCalledOnce()
  })
  it('ignores a duplicate download action while the current import is pending', async () => {
    mock_set()
    let complete
    const pending = new Promise((resolve) => {
      complete = resolve
    })
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/network/maa-copilot-set/123')) {
        await pending
      }
      return get(url)
    })
    component.code.value = 'prts://s123'
    const firstDownload = component.download()
    await component.download()
    complete()
    await firstDownload
    expect(state.config.sss.value.scripts).toHaveLength(3)
    expect(state.client.post).toHaveBeenCalledTimes(2)
  })
  it.each([
    '',
    '../123',
    'prts://abc',
    'https://other.test/operation/123',
    'https://prts.plus.other.test/operation/123',
    'https://prts.plus@other.test/operation/123',
    'https://prts.plus/operation/123/extra'
  ])('rejects invalid code %s without network work', async (code) => {
    component.code.value = code
    await component.download()
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.config.sss.value.scripts).toEqual([])
    expect(state.error).toHaveBeenCalledOnce()
  })
  it('preserves the queue on download error', async () => {
    component.code.value = '123'
    state.client.get.mockRejectedValue(new Error('offline'))
    await component.download()
    expect(state.config.sss.value.scripts).toEqual([])
    expect(state.error).toHaveBeenCalled()
    expect(component.loading.value).toBe(false)
  })
  it('uploads local files, preserves duplicates and reorders with their settings', async () => {
    const finish = vi.fn()
    const failure = vi.fn()
    await component.upload({ file: { file: new Blob(['{}']) }, onFinish: finish, onError: failure })
    expect(finish).toHaveBeenCalledOnce()
    expect(failure).not.toHaveBeenCalled()
    component.add_script(second.id)
    state.config.sss.value.scripts[1].times = 3
    state.config.sss.value.scripts[1].type = 2
    state.config.sss.value.scripts[1].ec = 3
    component.move(1, -1)
    expect(state.config.sss.value.scripts.map((item) => item.id)).toEqual([second.id, first.id])
    expect(state.config.sss.value.scripts[0]).toEqual({ id: second.id, type: 2, ec: 3, times: 3 })
    component.add_script(first.id)
    expect(state.config.sss.value.scripts).toHaveLength(3)
  })
  it('cannot delete a queued script and flushes removal before deleting an unused file', async () => {
    component.selected.value = first.id
    component.add_script(first.id)
    await component.delete_script()
    expect(state.client.delete).not.toHaveBeenCalled()
    state.config.sss.value.scripts = []
    await component.delete_script()
    expect(state.flush).toHaveBeenCalledOnce()
    expect(state.flush.mock.invocationCallOrder[0]).toBeLessThan(
      state.client.delete.mock.invocationCallOrder[0]
    )
    expect(state.client.delete).toHaveBeenCalledWith(
      expect.stringMatching(new RegExp('/sss-copilot/' + first.id + '$'))
    )
  })
  it('starts a new round only when the user resets the queue', async () => {
    vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) })
    component.add_script(first.id)
    const scripts = state.config.sss.value.scripts
    await component.restart_queue()
    const firstRun = state.config.sss.value.run_id
    expect(firstRun).toMatch(/^[a-f0-9]{32}$/)
    expect(state.flush).toHaveBeenCalledOnce()
    await component.restart_queue()
    expect(state.config.sss.value.run_id).not.toBe(firstRun)
    expect(state.config.sss.value.scripts).toEqual(scripts)
  })
})
