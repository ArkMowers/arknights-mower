import { describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'
import Component from './WebAccessSettings.vue'

const state = vi.hoisted(() => ({ config: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup() {
  state.config = reactive({
    webview: { port: 58000, token: '' },
    save_web_access: vi.fn(async (values) => Object.assign(state.config.webview, values))
  })
  return Component.setup({}, { expose: () => {} })
}

describe('web access draft', () => {
  it('keeps typing local until explicit save and reports success', async () => {
    const editor = setup()
    editor.port.value = 58001
    editor.token.value = 'synthetic-token'
    await nextTick()
    expect(state.config.webview).toEqual({ port: 58000, token: '' })
    expect(state.config.save_web_access).not.toHaveBeenCalled()
    await editor.save()
    expect(state.config.save_web_access).toHaveBeenCalledWith({
      port: 58001,
      token: 'synthetic-token'
    })
    expect(editor.saved.value).toBe(true)
    expect(editor.dirty.value).toBe(false)
  })

  it('preserves a failed draft for explicit retry and blocks invalid ports', async () => {
    const editor = setup()
    editor.port.value = null
    await editor.save()
    expect(state.config.save_web_access).not.toHaveBeenCalled()
    editor.port.value = 58002
    editor.token.value = 'synthetic-token'
    state.config.save_web_access.mockRejectedValueOnce(new Error('保存失败'))
    await editor.save()
    expect(editor.error.value).toBe('保存失败')
    expect(editor.saved.value).toBe(false)
    expect(editor.port.value).toBe(58002)
    expect(editor.token.value).toBe('synthetic-token')
    await editor.save()
    expect(editor.error.value).toBe('')
    expect(editor.saved.value).toBe(true)
  })
})
