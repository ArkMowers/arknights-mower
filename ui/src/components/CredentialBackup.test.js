import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, effectScope, nextTick, reactive } from 'vue'
import Component from './CredentialBackup.vue'
import { reloadImportedConfiguration } from '@/utils/configBackup'

const state = vi.hoisted(() => ({ config: null, plan: null, rescue: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/plan', () => ({
  usePlanStore: () => state.plan,
  useRescuePlanStore: () => state.rescue
}))
vi.mock('@/utils/configBackup', () => ({ reloadImportedConfiguration: vi.fn() }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

let editor, scope, axios
beforeEach(() => {
  vi.clearAllMocks()
  state.config = reactive({ autosave_paused: false, flush_config_saves: vi.fn(async () => {}) })
  state.plan = reactive({ autosave_paused: false, wait_for_plan_save: vi.fn(async () => {}) })
  state.rescue = reactive({ autosave_paused: false, wait_for_plan_save: vi.fn(async () => {}) })
  axios = { post: vi.fn() }
  const app = createApp({})
  app.provide('axios', axios)
  scope = effectScope()
  editor = scope.run(() => app.runWithContext(() => Component.setup({}, { expose: vi.fn() })))
})
afterEach(() => scope.stop())

function pick() {
  editor.chooseFile({
    target: { files: [new File(['encrypted'], 'backup.mower-credentials')], value: '' }
  })
}

async function preview() {
  editor.open('import')
  pick()
  editor.password.value = 'synthetic-passphrase'
  await nextTick()
  axios.post.mockResolvedValueOnce({
    data: { ok: true, groups: [{ id: 'main', label: '当前档案', count: 1 }] }
  })
  await editor.previewBackup()
}

describe('credential backup workflow', () => {
  it('requires a long repeated password before sending an export', async () => {
    editor.open('export')
    editor.password.value = editor.repeated.value = 'short'
    await editor.exportBackup()
    expect(editor.error.value).toContain('12')
    editor.password.value = 'synthetic-passphrase'
    await editor.exportBackup()
    expect(editor.error.value).toContain('不一致')
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('forgets password and file when dismissed', () => {
    editor.open('import')
    pick()
    editor.password.value = 'synthetic-passphrase'
    editor.close()
    expect(editor.password.value).toBe('')
    expect(editor.selected.value).toBeNull()
    expect(editor.mode.value).toBe('')
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('previews without importing or pausing saves, then requires another confirmation', async () => {
    await preview()
    expect(axios.post).toHaveBeenCalledTimes(1)
    expect(axios.post.mock.calls[0][0]).toContain('/preview')
    expect(axios.post.mock.calls[0][1].get('password')).toBe('synthetic-passphrase')
    expect(editor.preview.value.groups[0].count).toBe(1)
    expect(state.config.autosave_paused).toBe(false)
    editor.password.value = 'changed-passphrase'
    await nextTick()
    expect(editor.preview.value).toBeNull()
    await editor.importBackup()
    expect(axios.post).toHaveBeenCalledTimes(1)
  })

  it('drains saves, imports with explicit confirmation and keeps stale drafts paused until reload', async () => {
    await preview()
    axios.post.mockResolvedValueOnce({ data: { ok: true, message: '凭据已导入' } })
    await editor.importBackup()
    expect(state.config.flush_config_saves).toHaveBeenCalled()
    expect(state.rescue.wait_for_plan_save).toHaveBeenCalled()
    const [url, body, options] = axios.post.mock.calls[1]
    expect(url).toContain('/import')
    expect(body.get('confirmed')).toBe('1')
    expect(options.headers['X-Mower-Settings']).toBe('1')
    expect(editor.password.value).toBe('')
    for (const store of [state.config, state.plan, state.rescue])
      expect(store.autosave_paused).toBe(true)
    expect(reloadImportedConfiguration).toHaveBeenCalledWith(null)
    expect(editor.reloadRequired.value).toBe(true)
  })

  it.each([
    [new Error('network lost'), true],
    [{ response: { status: 500, data: { message: 'storage failed' } } }, true],
    [{ response: { status: 409, data: { code: 'configuration_changed' } } }, true],
    [{ response: { status: 409, data: { message: 'busy' } } }, false],
    [{ response: { status: 400, data: { message: 'wrong password' } } }, false]
  ])(
    'keeps ambiguous outcomes paused and releases rejected imports: %j',
    async (failure, paused) => {
      await preview()
      axios.post.mockRejectedValueOnce(failure)
      await editor.importBackup()
      expect(editor.password.value).toBe('')
      expect(editor.selected.value).toBeNull()
      expect(state.config.autosave_paused).toBe(paused)
      expect(editor.reloadRequired.value).toBe(paused)
      expect(reloadImportedConfiguration).not.toHaveBeenCalled()
    }
  )

  it('rejects oversized files before sending their contents', () => {
    const file = new File(['encrypted'], 'oversized.mower-credentials')
    Object.defineProperty(file, 'size', { value: 4 * 1024 * 1024 + 1 })
    editor.chooseFile({ target: { files: [file], value: '' } })
    expect(editor.selected.value).toBeNull()
    expect(editor.error.value).toContain('4 MiB')
    expect(axios.post).not.toHaveBeenCalled()
  })
})
