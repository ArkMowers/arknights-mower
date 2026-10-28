import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import Component from './MaaCopilot.vue'

const state = vi.hoisted(() => ({
  config: {},
  client: null,
  error: vi.fn(),
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
  useMessage: () => ({ error: state.error, success: state.success })
}))
let scope
let component
const first = { id: 'a'.repeat(64), stage_name: '1-7', title: '作业一' }
const second = { id: 'b'.repeat(64), stage_name: 'CE-6', title: '作业二' }
beforeEach(() => {
  vi.clearAllMocks()
  state.config = { copilot: ref({ scripts: [], user_additional: [] }) }
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

describe('ordinary Copilot library and queue', () => {
  it.each([
    'prts://123',
    '  prts://123  ',
    'maa://123',
    '123',
    'https://prts.plus/operation/123',
    'https://prts.plus/operation/123/?source=share#details'
  ])(
    'downloads %s through the existing proxy and imports into the separate ordinary library',
    async (code) => {
      state.client.get.mockImplementation(async (url) => ({
        data: url.includes('/network/')
          ? { data: { content: '{"stage_name":"1-7","actions":[]}' } }
          : { scripts: [first] }
      }))
      component.code.value = code
      await component.download()
      expect(state.client.get).toHaveBeenCalledWith(
        expect.stringMatching(/\/network\/maa-copilot\/123$/)
      )
      expect(state.client.post).toHaveBeenCalledWith(
        expect.stringMatching(/\/maa-copilot$/),
        expect.any(FormData)
      )
      expect(state.config.copilot.value.scripts).toEqual([
        { id: first.id, nav_name_override: '', is_raid: false }
      ])
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
    const original = { ...state.config.copilot.value.scripts[0] }
    component.code.value = '  prts://s123  '
    await component.download()
    expect(state.client.get).toHaveBeenCalledWith(
      expect.stringMatching(/\/network\/maa-copilot-set\/123$/)
    )
    expect(
      state.client.get.mock.calls
        .filter(([url]) => url.includes('/network/maa-copilot/'))
        .map(([url]) => url.split('/').at(-1))
    ).toEqual(['456', '789', '456'])
    expect(state.config.copilot.value.scripts).toEqual([
      original,
      { id: first.id, nav_name_override: '', is_raid: false },
      { id: second.id, nav_name_override: '', is_raid: false },
      { id: first.id, nav_name_override: '', is_raid: false }
    ])
    expect(state.success).toHaveBeenCalledOnce()
    expect(state.error).not.toHaveBeenCalled()
    expect(component.code.value).toBe('')
    expect(component.loading.value).toBe(false)
  })
  it.each([{ ids: [] }, { ids: Array.from({ length: 32 }, () => '456') }])(
    'refuses empty or over-capacity sets without truncation',
    async ({ ids }) => {
      mock_set(ids)
      component.add_script(first.id)
      const original = [...state.config.copilot.value.scripts]
      component.code.value = 'prts://s123'
      await component.download()
      expect(state.client.post).not.toHaveBeenCalled()
      expect(
        state.client.get.mock.calls.some(([url]) => url.includes('/network/maa-copilot/'))
      ).toBe(false)
      expect(state.config.copilot.value.scripts).toEqual(original)
      expect(state.error).toHaveBeenCalledOnce()
      expect(component.code.value).toBe('prts://s123')
    }
  )
  it('keeps the queue unchanged when a member download fails', async () => {
    mock_set()
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/network/maa-copilot/789')) throw new Error('download failed')
      return get(url)
    })
    component.add_script(second.id)
    const original = [...state.config.copilot.value.scripts]
    component.code.value = 'prts://s123'
    await component.download()
    expect(state.config.copilot.value.scripts).toEqual(original)
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.success).not.toHaveBeenCalled()
    expect(state.error).toHaveBeenCalledOnce()
    expect(component.loading.value).toBe(false)
  })
  it('keeps partial imports in the library without adding an incomplete set to the queue', async () => {
    mock_set()
    state.client.post
      .mockResolvedValueOnce({ data: first })
      .mockRejectedValueOnce({ response: { data: { message: '作业类型不匹配' } } })
    component.add_script(second.id)
    const original = [...state.config.copilot.value.scripts]
    component.code.value = 'prts://s123'
    await component.download()
    expect(state.client.post).toHaveBeenCalledTimes(2)
    expect(state.config.copilot.value.scripts).toEqual(original)
    expect(component.library.value).toEqual([first, second])
    expect(state.success).not.toHaveBeenCalled()
    expect(state.error).toHaveBeenCalledWith(expect.stringContaining('队列未改变'))
    expect(component.code.value).toBe('prts://s123')
  })
  it('does not overfill or overwrite a queue edited during import', async () => {
    mock_set()
    state.client.post.mockImplementationOnce(async () => {
      state.config.copilot.value.scripts = Array.from({ length: 32 }, () => ({ id: second.id }))
      return { data: first }
    })
    component.code.value = 'prts://s123'
    await component.download()
    expect(state.config.copilot.value.scripts).toHaveLength(32)
    expect(state.config.copilot.value.scripts.every((item) => item.id === second.id)).toBe(true)
    expect(state.success).not.toHaveBeenCalled()
    expect(state.error).toHaveBeenCalledWith(expect.stringContaining('剩余容量不足'))
  })
  it('rejects an oversized member before uploading any member', async () => {
    mock_set()
    const get = state.client.get.getMockImplementation()
    state.client.get.mockImplementation(async (url) => {
      if (url.endsWith('/network/maa-copilot/789'))
        return { data: { data: { content: 'x'.repeat(1024 * 1024 + 1) } } }
      return get(url)
    })
    component.code.value = 'prts://s123'
    await component.download()
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.config.copilot.value.scripts).toEqual([])
    expect(state.error).toHaveBeenCalledWith(expect.stringContaining('1 MB'))
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
    expect(state.config.copilot.value.scripts).toHaveLength(3)
    expect(state.client.post).toHaveBeenCalledTimes(3)
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
    expect(state.config.copilot.value.scripts).toEqual([])
    expect(state.error).toHaveBeenCalledOnce()
  })
  it('preserves the queue on download error', async () => {
    component.code.value = '123'
    state.client.get.mockRejectedValue(new Error('offline'))
    await component.download()
    expect(state.config.copilot.value.scripts).toEqual([])
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
    state.config.copilot.value.scripts[1].is_raid = true
    component.move(1, -1)
    expect(state.config.copilot.value.scripts.map((item) => item.id)).toEqual([second.id, first.id])
    expect(state.config.copilot.value.scripts[0].is_raid).toBe(true)
    component.add_script(first.id)
    expect(state.config.copilot.value.scripts).toHaveLength(3)
  })
  it('cannot delete a queued script and flushes removal before deleting an unused file', async () => {
    component.selected.value = first.id
    component.add_script(first.id)
    await component.delete_script()
    expect(state.client.delete).not.toHaveBeenCalled()
    state.config.copilot.value.scripts = []
    await component.delete_script()
    expect(state.flush).toHaveBeenCalledOnce()
    expect(state.flush.mock.invocationCallOrder[0]).toBeLessThan(
      state.client.delete.mock.invocationCallOrder[0]
    )
    expect(state.client.delete).toHaveBeenCalledWith(
      expect.stringMatching(new RegExp('/maa-copilot/' + first.id + '$'))
    )
  })
  it('starts a new round only when the user resets the queue', async () => {
    vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) })
    component.add_script(first.id)
    const scripts = state.config.copilot.value.scripts
    await component.restart_queue()
    const firstRun = state.config.copilot.value.run_id
    expect(firstRun).toMatch(/^[a-f0-9]{32}$/)
    expect(state.flush).toHaveBeenCalledOnce()
    await component.restart_queue()
    expect(state.config.copilot.value.run_id).not.toBe(firstRun)
    expect(state.config.copilot.value.scripts).toEqual(scripts)
  })
})

describe('ParadoxCopilot queue', () => {
  it('imports through the paradox endpoint and only records the script id', async () => {
    state.config.paradox = ref({ scripts: [], run_id: '' })
    const paradox = scope.run(() => Component.setup({ paradox: true }, { expose: () => {} }))
    await paradox.upload_blob(new Blob(['{"stage_name":"mem_test_1","actions":[]}']))
    expect(state.client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/maa-paradox$/),
      expect.any(FormData)
    )
    expect(state.config.paradox.value.scripts).toEqual([{ id: first.id }])
    expect(state.config.copilot.value.scripts).toEqual([])
  })
})
