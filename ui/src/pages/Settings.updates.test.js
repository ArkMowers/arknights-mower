import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import Settings from './Settings.vue'

const state = vi.hoisted(() => ({ config: null, mower: null, gui: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('@/stores/gui', () => ({ useGuiStore: () => state.gui }))
vi.mock('pinia', async () => ({ storeToRefs: (await import('vue')).toRefs }))
vi.mock('naive-ui', async () => {
  const { h } = await import('vue')
  const wrapper = {
    setup:
      (_, { slots }) =>
      () =>
        h('div', [slots.label?.(), slots.default?.()])
  }
  return Object.fromEntries(
    [
      'NAlert',
      'NButton',
      'NCard',
      'NCollapse',
      'NCollapseItem',
      'NForm',
      'NFormItem',
      'NIcon',
      'NSelect',
      'NSlider',
      'NSwitch'
    ].map((key) => [key, wrapper])
  )
})
vi.mock('@/components/ChatBotSetting.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/SoftwareUpdate.vue', () => ({
  default: { setup: () => () => 'Mower 软件更新' }
}))
vi.mock('@/components/ResourceUpdate.vue', () => ({
  default: { setup: () => () => 'Mower 资源更新' }
}))
vi.mock('@/components/MaaUpdates.vue', () => ({
  default: { setup: () => () => 'MAA 本体与资源更新' }
}))
vi.mock('@/components/NetworkSettings.vue', () => ({ default: { setup: () => () => '网络设置' } }))
vi.mock('@/components/WebAccessSettings.vue', () => ({
  default: { setup: () => () => '访问端口与 Token' }
}))
vi.mock('@/components/ConfigBackup.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/ConfigProfilesSettings.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/SoftwareVersionPreference.vue', () => ({
  default: { setup: () => () => '' }
}))
vi.mock('@/components/VersionWatermarkPreference.vue', () => ({
  default: { setup: () => () => '' }
}))
vi.mock('@/components/RunningLogLayoutPreference.vue', () => ({
  default: { setup: () => () => '' }
}))
vi.mock('@/components/LogBackgroundPreference.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/HalloweenPreference.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/SettingsSegmented.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/Email.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/ProcessControl.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/DepotHistorySettings.vue', () => ({ default: { setup: () => () => '' } }))
vi.mock('@/components/MowerInputNumber.vue', () => ({ default: { setup: () => () => '' } }))

beforeEach(() => {
  state.config = reactive({
    manager_owned_device: true,
    extra_settings_visible: true,
    theme: 'light',
    webview: { scale: 1, tray: true },
    runtime_platform: 'windows',
    screenshot: 1,
    screenshot_archive_limit_mb: 5120
  })
  state.mower = reactive({ updates_enabled: true, running: false })
  state.gui = reactive({
    taskQueueDisplay: 'portraits',
    taskQueueDisplaySaving: false,
    taskQueueDisplayError: '',
    displayDisabled: false,
    loading: false,
    loaded: true,
    load: vi.fn(),
    setTaskQueueDisplay: vi.fn(),
    retryTaskQueueDisplay: vi.fn()
  })
})

async function render() {
  const app = createSSRApp(Settings)
  app.provide('mobile', false)
  return renderToString(app)
}

describe('network and update settings', () => {
  it.each([
    [false, 'darwin', true],
    [true, 'darwin', false],
    [false, 'android', false]
  ])(
    'shows access settings only on independent desktop instances (%s, %s)',
    async (managed, platform, visible) => {
      state.config.manager_owned_device = managed
      state.config.runtime_platform = platform
      expect((await render()).includes('访问端口与 Token')).toBe(visible)
    }
  )
  it('places MAA updates immediately after Mower resources in an authorized managed instance', async () => {
    const html = await render()
    const section = html.split('id="mower-updates"')[1].split('</section>')[0]
    expect(section).toContain('MAA 本体与资源更新')
    expect(section.indexOf('Mower 资源更新')).toBeLessThan(section.indexOf('MAA 本体与资源更新'))
    expect(section.indexOf('MAA 本体与资源更新')).toBeLessThan(section.indexOf('网络设置'))
    expect(html.split('MAA 本体与资源更新')).toHaveLength(2)
  })

  it('hides the section when managed maintenance is disabled', async () => {
    state.config.extra_settings_visible = false
    state.mower.updates_enabled = false
    const html = await render()
    expect(html).not.toContain('id="mower-updates"')
    expect(html).not.toContain('MAA 本体与资源更新')
  })

  it('keeps update controls hidden until the launch permission is known', async () => {
    state.mower.updates_enabled = null
    const html = await render()
    expect(html).toContain('网络设置')
    expect(html).not.toContain('MAA 本体与资源更新')
  })
})
