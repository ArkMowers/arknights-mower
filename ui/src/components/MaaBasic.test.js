import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import Component from './MaaBasic.vue'

const state = vi.hoisted(() => ({ client: null, config: {}, unmounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === 'axios' ? state.client : false),
  onMounted: () => {},
  onUnmounted: (callback) => state.unmounted.push(callback)
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({}) }))
vi.mock('pinia', () => ({ storeToRefs: () => state.config }))

describe('Android MAA companion update checks', () => {
  let scope
  let component
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', { setTimeout, clearTimeout })
    state.unmounted = []
    state.config = Object.fromEntries(
      Object.entries({
        runtime_platform: 'android',
        maa_path: '/maa',
        maa_mirrorchyan_token: '',
        maa_update_channel: 'beta',
        maa_auto_check_update: false,
        maa_auto_update: false,
        maa_resource_auto_check_update: false,
        maa_resource_auto_update: false,
        maa_restore_theme_enable: false,
        maa_restore_theme: '',
        maa_conn_preset: '',
        maa_touch_option: ''
      }).map(([key, value]) => [key, ref(value)])
    )
    state.client = {
      get: vi.fn(async () => ({
        data: {
          ok: true,
          supported: true,
          installed: true,
          platform: 'android',
          component_updates: [{ endpoint: '/android/python-update' }]
        }
      })),
      post: vi.fn(async () => ({
        data: {
          ok: true,
          available: true,
          latest: { tag: 'v6.19.0' },
          installed_version: 'v6.18.0',
          check_id: 'maa-only'
        }
      }))
    }
    scope = effectScope()
    component = scope.run(() => Component.setup({}, { expose: () => {} }))
    component.maa_installed.value = true
  })
  afterEach(() => {
    state.unmounted.forEach((callback) => callback())
    scope.stop()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })
  it('starts both checks concurrently and preserves the core check token', async () => {
    let complete
    state.client.post.mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve
        })
    )
    const check = vi.fn(async () => {})
    component.maa_component_controls.value = [{ check }]
    const pending = component.check_maa_update()
    expect(check).toHaveBeenCalledOnce()
    expect(component.maa_combined_checking.value).toBe(true)
    complete({
      data: { ok: true, available: true, latest: { tag: 'v6.19.0' }, check_id: 'maa-only' }
    })
    await pending
    expect(component.maa_update_check.value.id).toBe('maa-only')
    expect(component.maa_combined_checking.value).toBe(false)
  })
  it('a companion failure does not hide the core update', async () => {
    component.maa_component_controls.value = [
      {
        check: async () => {
          throw new Error('offline')
        }
      }
    ]
    await component.check_maa_update()
    expect(component.maa_update_check.value.available).toBe(true)
  })
  it('a core failure still checks the companion', async () => {
    state.client.post.mockRejectedValue(new Error('core offline'))
    const check = vi.fn(async () => {})
    component.maa_component_controls.value = [{ check }]
    await component.check_maa_update()
    expect(check).toHaveBeenCalledOnce()
    expect(component.maa_update_check.value.status).toBe('error')
  })
  it('uses Mirror for Android resources while keeping the core on GitHub', async () => {
    state.config.maa_mirrorchyan_token.value = 'fixture-cdk'
    component.maa_resource_source.value = 'mirrorchyan'
    await component.check_maa_resource_update()
    expect(state.client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/maa-resource-update\/check$/),
      expect.objectContaining({ source: 'mirrorchyan', mirror_token: 'fixture-cdk' })
    )
    await component.check_maa_update()
    expect(state.client.post).toHaveBeenCalledWith(
      expect.stringMatching(/\/maa-update\/check$/),
      expect.objectContaining({ source: 'github', mirror_token: '' })
    )
    expect(state.client.post.mock.calls.some(([url]) => url.endsWith('/mirrorchyan-status'))).toBe(
      false
    )
  })
  it('invalidates the resource receipt when its Android source changes', async () => {
    component.maa_resource_update_check.value = {
      status: 'success',
      available: true,
      id: 'old-receipt'
    }
    component.maa_resource_source.value = 'mirrorchyan'
    await Promise.resolve()
    expect(component.maa_resource_update_check.value.id).toBe('')
  })
  it.each(['linux', 'darwin', 'windows'])(
    'does not add requests or controls on %s',
    async (platform) => {
      state.config.runtime_platform.value = platform
      const check = vi.fn(async () => {})
      component.maa_component_controls.value = [{ check }]
      await component.get_maa_update_info()
      expect(component.maa_component_updates.value).toEqual([])
      await component.check_maa_update()
      expect(check).not.toHaveBeenCalled()
      expect(state.client.post).toHaveBeenCalledTimes(1)
      expect(state.client.post.mock.calls[0][0]).toMatch(/\/maa-update\/check$/)
    }
  )
  function mockAvailableUpdates() {
    state.client.post.mockImplementation(async (url) => ({
      data: url.endsWith('/start')
        ? { ok: true, job: { id: 'update-job', status: 'running' } }
        : {
            ok: true,
            available: true,
            check_id: 'checked',
            latest: { tag: 'v6.19.0', version: '2026-10-09 23:31:13.000' },
            current: { version: '' }
          }
    }))
    state.client.get.mockImplementation(async (url) => ({
      data: url.endsWith('/status')
        ? { ok: true, job: { status: 'running' } }
        : {
            ok: true,
            supported: true,
            installed: true,
            default_source: 'github',
            current: { version: '' }
          }
    }))
    component.maa_update_supported.value = true
    component.maa_resource_update_supported.value = true
  }

  it.each(['core', 'resource'])(
    'automatically checks only the enabled %s component',
    async (kind) => {
      mockAvailableUpdates()
      state.config[
        kind === 'core' ? 'maa_auto_check_update' : 'maa_resource_auto_check_update'
      ].value = true
      await nextTick()
      await component.auto_check_updates()
      expect(
        state.client.post.mock.calls.map(([url]) => url.split('/').slice(-2).join('/'))
      ).toEqual([kind === 'core' ? 'maa-update/check' : 'maa-resource-update/check'])
    }
  )

  it.each(['core', 'resource'])(
    'automatically installs only the opted-in %s component',
    async (kind) => {
      mockAvailableUpdates()
      state.config[kind === 'core' ? 'maa_auto_update' : 'maa_resource_auto_update'].value = true
      await nextTick()
      await component.auto_check_updates()
      const prefix = kind === 'core' ? 'maa-update' : 'maa-resource-update'
      expect(
        state.client.post.mock.calls.map(([url]) => url.split('/').slice(-2).join('/'))
      ).toEqual([`${prefix}/check`, `${prefix}/start`])
      expect(state.client.post.mock.calls[1][1].check_id).toBe('checked')
    }
  )

  it('does not let an invalid core Mirror CDK suppress independent GitHub resource checks', async () => {
    mockAvailableUpdates()
    await component.get_maa_update_info()
    component.maa_update_source.value = 'mirrorchyan'
    state.config.maa_auto_check_update.value = true
    state.config.maa_resource_auto_check_update.value = true
    await nextTick()
    state.client.post.mockClear()
    await component.auto_check_updates()
    expect(state.client.post.mock.calls.map(([url]) => url)).toEqual([
      expect.stringMatching(/\/maa-resource-update\/check$/)
    ])
  })

  it.each(['disable', 'target', 'source', 'channel', 'unmount'])(
    'does not automatically install an obsolete core check after %s',
    async (change) => {
      mockAvailableUpdates()
      await component.get_maa_update_info()
      state.config.maa_auto_update.value = true
      await nextTick()
      let complete
      state.client.post.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            complete = resolve
          })
      )
      const pending = component.auto_check_updates()
      if (change === 'disable') state.config.maa_auto_update.value = false
      if (change === 'target') state.config.maa_path.value = '/other'
      if (change === 'source') component.maa_update_source.value = 'mirrorchyan'
      if (change === 'channel') state.config.maa_update_channel.value = 'stable'
      if (change === 'unmount') state.unmounted.forEach((callback) => callback())
      await nextTick()
      complete({
        data: { ok: true, available: true, check_id: 'obsolete', latest: { tag: 'v6.19.0' } }
      })
      await pending
      expect(state.client.post.mock.calls.some(([url]) => url.endsWith('/start'))).toBe(false)
      expect(component.maa_update_check.value.id).not.toBe('obsolete')
    }
  )

  it('checks the new core channel after an invalidated slow check finishes', async () => {
    mockAvailableUpdates()
    await component.get_maa_update_info()
    state.config.maa_auto_update.value = true
    await nextTick()
    let complete
    state.client.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        })
    )
    const pending = component.auto_check_updates()
    state.config.maa_update_channel.value = 'stable'
    await vi.advanceTimersByTimeAsync(400)
    expect(state.client.post).toHaveBeenCalledTimes(1)
    complete({
      data: { ok: true, available: true, check_id: 'obsolete', latest: { tag: 'v6.19.0' } }
    })
    await pending
    await vi.advanceTimersByTimeAsync(400)
    expect(state.client.post.mock.calls.map(([url]) => url.split('/').slice(-2).join('/'))).toEqual(
      ['maa-update/check', 'maa-update/check', 'maa-update/start']
    )
    expect(state.client.post.mock.calls[2][1]).toMatchObject({
      channel: 'stable',
      check_id: 'checked'
    })
  })

  it('checks resources while an unrelated manual core check is pending', async () => {
    mockAvailableUpdates()
    state.config.maa_resource_auto_check_update.value = true
    await nextTick()
    let complete
    state.client.post.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve
        })
    )
    const pending = component.check_maa_update()
    await component.auto_check_updates()
    expect(state.client.post.mock.calls[1][0]).toMatch(/\/maa-resource-update\/check$/)
    complete({ data: { ok: true, available: false } })
    await pending
  })

  it.each(['disable', 'target', 'source', 'unmount'])(
    'does not automatically install an obsolete resource check after %s',
    async (change) => {
      mockAvailableUpdates()
      state.config.maa_resource_auto_update.value = true
      await nextTick()
      let complete
      state.client.post.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            complete = resolve
          })
      )
      const pending = component.auto_check_updates()
      if (change === 'disable') state.config.maa_resource_auto_update.value = false
      if (change === 'target') state.config.maa_path.value = '/other'
      if (change === 'source') component.maa_resource_source.value = 'mirrorchyan'
      if (change === 'unmount') state.unmounted.forEach((callback) => callback())
      await nextTick()
      complete({
        data: {
          ok: true,
          available: true,
          check_id: 'obsolete',
          latest: { version: '2026-10-09 23:31:13.000' }
        }
      })
      await pending
      expect(state.client.post.mock.calls.some(([url]) => url.endsWith('/start'))).toBe(false)
      expect(component.maa_resource_update_check.value.id).not.toBe('obsolete')
    }
  )

  it('does not hide a resource read-denied diagnostic behind an available update', async () => {
    mockAvailableUpdates()
    state.client.post.mockResolvedValueOnce({
      data: {
        ok: true,
        available: true,
        check_id: 'repair',
        current: { version: '', error: 'version.json：访问被拒绝' },
        latest: { version: '2026-10-09 23:31:13.000' }
      }
    })
    await component.check_maa_resource_update()
    expect(component.maa_resource_update_info_msg.value).toContain('访问被拒绝')
    expect(component.maa_resource_update_check.value.id).toBe('repair')
  })

  it('displays structured connection-config permission failures', async () => {
    state.client.get.mockResolvedValueOnce({
      data: { ok: false, message: 'config.json：访问被拒绝' }
    })
    await component.get_maa_conn_presets()
    expect(component.maa_msg.value).toContain('config.json：访问被拒绝')
    expect(component.maa_conn_presets.value).toEqual([])
  })
})
