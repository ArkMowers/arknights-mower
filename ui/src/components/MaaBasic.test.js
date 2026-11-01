import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, effectScope, nextTick, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Component from './MaaBasic.vue'

const state = vi.hoisted(() => ({ client: null, config: {}, mounted: [], unmounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key) => (key === 'axios' ? state.client : false),
  onMounted: (callback) => state.mounted.push(callback),
  onUnmounted: (callback) => state.unmounted.push(callback)
}))
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  const wrapper = {
    inheritAttrs: false,
    props: ['label'],
    setup:
      (props, { slots }) =>
      () =>
        h('div', [slots.header?.(), slots.label?.() || props.label, slots.default?.()])
  }
  return Object.fromEntries(
    [
      'NA',
      'NAlert',
      'NButton',
      'NCard',
      'NCheckbox',
      'NDivider',
      'NForm',
      'NFormItem',
      'NInput',
      'NProgress',
      'NRadio',
      'NRadioGroup',
      'NSelect',
      'NSpace',
      'NSwitch'
    ].map((name) => [name, wrapper])
  )
})
vi.mock('./HelpText.vue', () => ({
  default: {
    setup:
      (_, { slots }) =>
      () =>
        slots.default?.()
  }
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => ({}) }))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => ({}) }))
vi.mock('pinia', () => ({ storeToRefs: () => state.config }))

describe('MAA connection and theme settings', () => {
  let scope
  let component
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', { setTimeout, clearTimeout })
    state.mounted = []
    state.unmounted = []
    state.config = Object.fromEntries(
      Object.entries({
        manager_owned_device: false,
        runtime_platform: 'android',
        updates_enabled: true,
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
  })
  afterEach(() => {
    state.unmounted.forEach((callback) => callback())
    scope.stop()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })
  it.each(['windows', 'android'])(
    'shows only theme restoration in a managed %s instance',
    async (platform) => {
      state.config.runtime_platform.value = platform
      state.config.manager_owned_device.value = true
      state.config.maa_restore_theme_enable.value = true
      await nextTick()
      const html = await renderToString(createSSRApp(Component))
      expect(html).toContain('任务结束后恢复主题')
      expect(html).toContain('目标主题')
      for (const label of ['MAA目录', '连接配置', '触控模式', '测试连接', 'CDK', '更新 MAA']) {
        expect(html).not.toContain(label)
      }
      expect(html).not.toContain('Android 应用管理')
      expect(html).not.toContain('/mowersettings#software-update')
      state.config.maa_restore_theme_enable.value = false
      const disabled = await renderToString(createSSRApp(Component))
      expect(disabled).toContain('任务结束后恢复主题')
      expect(disabled).not.toContain('目标主题')
    }
  )

  it('keeps connection controls for independently launched instances', async () => {
    state.config.runtime_platform.value = 'windows'
    const html = await renderToString(createSSRApp(Component))
    for (const label of ['MAA目录', '连接配置', '触控模式', '测试连接', '任务结束后恢复主题']) {
      expect(html).toContain(label)
    }
  })

  it('never loads update endpoints from the MAA connection panel', async () => {
    await Promise.all(state.mounted.map((callback) => callback()))
    expect(state.client.get).toHaveBeenCalledOnce()
    expect(state.client.get.mock.calls[0][0]).toMatch(/\/maa-conn-preset$/)
    expect(state.client.post).not.toHaveBeenCalled()
  })

  it('does not test or load managed connections', async () => {
    state.config.manager_owned_device.value = true
    await nextTick()
    await Promise.all(state.mounted.map((callback) => callback()))
    await component.get_maa_conn_presets()
    await component.test_maa()
    expect(state.client.get).not.toHaveBeenCalled()
    expect(state.client.post).not.toHaveBeenCalled()
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
