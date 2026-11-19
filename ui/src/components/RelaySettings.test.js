import { describe, expect, it, vi } from 'vitest'
import { createApp } from 'vue'
import RelaySettings from './RelaySettings.vue'

const config = vi.hoisted(() => ({ extra_settings_visible: false }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => config }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  onMounted: vi.fn(),
  onUnmounted: vi.fn(),
  useSSRContext: () => ({ modules: new Set() })
}))

describe('standalone relay maintenance permission', () => {
  it('displays the saved permission and retains it when a change fails', async () => {
    const patch = vi.fn().mockResolvedValueOnce({ data: { extra_settings_visible: true } })
    const app = createApp({})
    app.provide('axios', { patch })
    const settings = app.runWithContext(() => RelaySettings.setup({}, { expose: vi.fn() }))
    await settings.setMaintenance(true)
    expect(patch).toHaveBeenCalledWith(expect.stringMatching(/\/conf$/), {
      extra_settings_visible: true
    })
    expect(config.extra_settings_visible).toBe(true)
    patch.mockRejectedValueOnce(new Error('offline'))
    await settings.setMaintenance(false)
    expect(config.extra_settings_visible).toBe(true)
    expect(settings.error.value).toContain('保存失败')
    expect(settings.busy.value).toBe(false)
  })
})
