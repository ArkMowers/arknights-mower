import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'
import SoftwareUpdate from './SoftwareUpdate.vue'
import { pendingSoftwarePackage } from '@/stores/updateUpload'

const state = vi.hoisted(() => ({ mounted: [], unmounted: [], client: null, warning: vi.fn() }))

// Exercise the component's setup and lifecycle without launching a browser.
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (callback) => state.mounted.push(callback),
  onUnmounted: (callback) => state.unmounted.push(callback)
}))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useDialog: () => ({ warning: state.warning }),
  useMessage: () => ({ error: vi.fn(), info: vi.fn() })
}))

describe('offline software package installation', () => {
  let scope
  let component

  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('sessionStorage', { getItem: () => null, setItem: vi.fn(), removeItem: vi.fn() })
    state.mounted = []
    state.unmounted = []
    state.warning.mockClear()
    state.client = {
      defaults: { headers: { common: {} } },
      get: vi.fn(async (url) => ({
        data: url.endsWith('/info')
          ? {
              ok: true,
              deployment: 'release',
              version: '4.1.6-alpha.4',
              blockers: [],
              instances: [{ name: 'one' }],
              channels: [],
              settings: { channel: 'beta', auto_check: true, auto_update: true, background: true }
            }
          : { ok: true, status: 'idle' }
      })),
      post: vi.fn(async (url) => {
        if (url.endsWith('/manual/inspect'))
          return {
            data: {
              ok: true,
              check_id: 'preview',
              version: 'v4.1.5',
              downgrade: true,
              manual: true
            }
          }
        if (url.endsWith('/auto-check')) throw new Error('Network checks unavailable')
        if (url.endsWith('/start') || url.endsWith('/manual/discard'))
          return { data: { ok: true, id: 'offline-job' } }
        throw new Error('Unexpected request')
      })
    }
    scope = effectScope()
  })

  afterEach(() => {
    state.unmounted.forEach((callback) => callback())
    scope.stop()
    pendingSoftwarePackage.value = null
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  async function mount(file) {
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    await Promise.all(state.mounted.map((callback) => callback()))
    await nextTick()
    state.client.post.mockClear()
    component.dropSoftwarePackage({ dataTransfer: { files: [file] } })
    await nextTick()
  }

  it('consumes a global drop before mounting without triggering an online check or install', async () => {
    const file = new File(['offline'], '任意改名 (1).bin')
    pendingSoftwarePackage.value = file
    component = scope.run(() => SoftwareUpdate.setup({}, { expose: () => {} }))
    await Promise.all(state.mounted.map((callback) => callback()))
    expect(pendingSoftwarePackage.value).toBeNull()
    expect(component.packageFiles.value[0].file).toBe(file)
    expect(state.client.post).not.toHaveBeenCalled()
    expect(state.warning).not.toHaveBeenCalled()
    const replacement = new File(['replacement'], 'new.zip')
    pendingSoftwarePackage.value = replacement
    await nextTick()
    expect(component.packageFiles.value[0].file).toBe(replacement)
    expect(pendingSoftwarePackage.value).toBeNull()
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('keeps the default update channel after a manual PR installation', async () => {
    await mount(new File(['offline'], 'package.zip'))
    expect(component.channel.value).toBe('beta')
    await component.install(false, { check_id: 'pr', source_pr: 7 })
    expect(component.channel.value).toBe('beta')
    expect(component.autoUpdate.value).toBe(false)
  })

  it.each([true, false])(
    'inspects local contents before confirming, install=%s',
    async (confirm) => {
      const file = new File(['offline'], '任意改名 (1).bin')
      await mount(file)
      expect(state.client.post).not.toHaveBeenCalled()
      expect(state.warning).not.toHaveBeenCalled()
      await component.requestInstall(true)
      expect(state.client.post).toHaveBeenCalledOnce()
      expect(state.client.post.mock.calls[0][0]).toBe('/software-update/manual/inspect')
      expect(state.client.post.mock.calls[0][1].get('file').name).toBe(file.name)
      const dialog = state.warning.mock.calls[0][0]
      expect(dialog.title).toBe('确认回退版本？')
      expect(dialog.content).toContain('v4.1.5')
      if (confirm) {
        await dialog.onPositiveClick()
        const submission = state.client.post.mock.calls.find(([url]) => url.endsWith('/start'))
        expect(submission[1]).toMatchObject({ check_id: 'preview', confirm_downgrade: true })
      } else {
        await dialog.onNegativeClick()
        expect(state.client.post.mock.calls.map(([url]) => url)).toEqual([
          '/software-update/manual/inspect',
          '/software-update/manual/discard'
        ])
      }
      expect(
        state.client.post.mock.calls.some(
          ([url]) => url.endsWith('/check') || url.endsWith('/auto-check')
        )
      ).toBe(false)
    }
  )

  it('an unrelated pending online check does not block manual installation', async () => {
    await mount(new File(['offline'], 'arknights-mower_4.2.0_windows_x64.zip'))
    let finishCheck
    state.client.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishCheck = resolve
        })
    )
    const checking = component.checkUpdate()
    // Wait until the online request has actually started.
    for (let i = 0; i < 5 && !finishCheck; i++) await nextTick()
    expect(finishCheck).toBeTypeOf('function')
    expect(component.checking.value).toBe(true)
    await component.requestInstall(true)
    expect(state.warning).toHaveBeenCalledOnce()
    await state.warning.mock.calls[0][0].onPositiveClick()
    expect(state.client.post.mock.calls.map(([url]) => url)).toEqual([
      '/software-update/check',
      '/software-update/manual/inspect',
      '/software-update/start',
      '/software-update/manual/discard'
    ])
    finishCheck({ data: { ok: true, available: false } })
    await checking
  })
})
