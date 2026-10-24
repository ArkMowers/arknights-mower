import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import DeviceSettingsEditor from './DeviceSettingsEditor.vue'

const hooks = vi.hoisted(() => ({ mounted: [], unmounted: [] }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  onMounted: (callback) => hooks.mounted.push(callback),
  onUnmounted: (callback) => hooks.unmounted.push(callback)
}))

let scope, component, api, emit, original
const target = { name: 'first', path: '/first' }
beforeEach(async () => {
  hooks.mounted = []
  hooks.unmounted = []
  original = {
    device: {
      preset_id: 'manual.other',
      screenshot_backend: 'droidcast',
      touch_backend: 'scrcpy',
      last_serial: 'saved',
      instance_uuid: 'saved-uuid',
      topology_fingerprint: 'saved-fingerprint'
    },
    custom_screenshot: { command: 'saved-command' },
    performance_mode: 'high'
  }
  api = {
    get_device_settings: vi.fn(async () => ({
      values: original,
      fields: [
        { key: 'device.preset_id', group: '设备', kind: 'select' },
        { key: 'device.screenshot_backend', group: '截图', kind: 'select' },
        { key: 'device.touch_backend', group: '截图', kind: 'select' },
        { key: 'device.last_serial', group: '设备', kind: 'text' },
        { key: 'device.instance_uuid', group: '设备', kind: 'text', read_only: true },
        { key: 'device.topology_fingerprint', group: '设备', kind: 'text', read_only: true },
        { key: 'custom_screenshot.command', group: '截图', kind: 'text' },
        { key: 'performance_mode', group: '性能', kind: 'select' }
      ]
    })),
    update_device_settings: vi.fn(async () => ({ ok: true })),
    discover_device_settings: vi.fn(async () => ({
      candidates: [{ key: 'chosen', binding: { last_serial: 'unverified' } }]
    })),
    select_device_path: vi.fn(async () => '/chosen')
  }
  emit = vi.fn()
  scope = effectScope()
  component = scope.run(() =>
    DeviceSettingsEditor.setup({ api, idx: 0, target }, { expose() {}, emit })
  )
  await Promise.all(hooks.mounted.map((callback) => callback()))
})
afterEach(() => {
  hooks.unmounted.forEach((callback) => callback())
  scope.stop()
})

it('keeps detected identity metadata out of manual edits', () => {
  component.edit('device.instance_uuid', 'forged')
  component.edit('device.topology_fingerprint', 'forged')
  expect(component.changes.value).toEqual({})
})

it('submits only edited settings with the captured instance and original values', async () => {
  component.edit('custom_screenshot.command', 'new-command')
  component.edit('performance_mode', 'low')
  await component.save()
  expect(api.update_device_settings).toHaveBeenCalledExactlyOnceWith(
    0,
    { 'custom_screenshot.command': 'new-command', performance_mode: 'low' },
    target,
    original
  )
  expect(original.custom_screenshot.command).toBe('saved-command')
  expect(emit).toHaveBeenCalledWith('saved')
})

it('couples MuMu capture and touch and preserves the draft on a rejected save', async () => {
  component.edit('device.screenshot_backend', 'mumu_ipc')
  expect(component.changes.value).toEqual({
    'device.screenshot_backend': 'mumu_ipc',
    'device.touch_backend': 'mumu_ipc'
  })
  api.update_device_settings.mockRejectedValue(new Error('实例进程运行期间不能修改配置'))
  await component.save()
  expect(component.error.value).toContain('实例进程运行')
  expect(component.draft.value['device.screenshot_backend']).toBe('mumu_ipc')
  expect(emit).not.toHaveBeenCalled()
})

it('does not save on discovery or candidate selection and clears an unverified endpoint', async () => {
  await component.detect()
  component.selectCandidate('chosen')
  expect(component.draft.value['device.last_serial']).toBe('')
  expect(api.update_device_settings).not.toHaveBeenCalled()
})

it('cannot save defaults after a failed reload', async () => {
  api.get_device_settings.mockRejectedValue(new Error('unreadable'))
  await component.load()
  component.edit('performance_mode', 'low')
  await component.save()
  expect(component.disabled.value).toBe(true)
  expect(api.update_device_settings).not.toHaveBeenCalled()
})

it('discards a late discovery response after closing the editor', async () => {
  let finish
  api.discover_device_settings.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  const pending = component.detect()
  await Promise.resolve()
  hooks.unmounted.forEach((callback) => callback())
  finish({ candidates: [{ key: 'stale' }] })
  await pending
  expect(component.discovery.value).toBeNull()
  expect(emit).not.toHaveBeenCalled()
})

it('clears the previous endpoint immediately when editing the target preset', async () => {
  component.edit('device.preset_id', 'macos.avd')
  expect(component.draft.value['device.last_serial']).toBe('')
  await component.save()
  expect(api.update_device_settings).toHaveBeenCalledWith(
    0,
    {
      'device.preset_id': 'macos.avd',
      'device.last_serial': '',
      'device.instance_uuid': '',
      'device.topology_fingerprint': ''
    },
    target,
    original
  )
})
