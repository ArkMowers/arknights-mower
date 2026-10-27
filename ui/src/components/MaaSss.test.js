import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import Component from './MaaSss.vue'

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
const first = { id: 'a'.repeat(64), stage_name: '保全关卡一', title: '作业一' }
const second = { id: 'b'.repeat(64), stage_name: '保全关卡二', title: '作业二' }
beforeEach(() => {
  vi.clearAllMocks()
  state.config = { sss: ref({ scripts: [] }) }
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
  it('downloads through the existing proxy and imports into the separate SSS library', async () => {
    state.client.get.mockImplementation(async (url) => ({
      data: url.includes('/network/')
        ? { data: { content: '{"type":"SSS","stage_name":"保全"}' } }
        : { scripts: [first] }
    }))
    component.code.value = 'maa://123'
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
  })
  it('rejects invalid download codes without network work and preserves the queue on error', async () => {
    component.code.value = '../123'
    await component.download()
    expect(state.client.get).not.toHaveBeenCalled()
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
