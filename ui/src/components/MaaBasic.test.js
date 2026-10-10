import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
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
    state.unmounted = []
    state.config = Object.fromEntries(
      Object.entries({
        runtime_platform: 'android',
        maa_path: '/maa',
        maa_mirrorchyan_token: '',
        maa_update_channel: 'beta',
        maa_auto_check_update: false,
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
})
