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
      installation_path: '/saved',
      manager_path: '/saved/tool',
      config_path: '',
      instance_id: '0',
      instance_name: 'first',
      game_package: 'com.hypergryph.arknights',
      screenshot_backend: 'droidcast',
      touch_backend: 'scrcpy',
      last_serial: 'saved',
      instance_uuid: 'saved-uuid',
      topology_fingerprint: 'saved-fingerprint'
    },
    custom_screenshot: { command: 'saved-command' },
    waiting_scene: {
      CONNECTING: [1, 10],
      UNKNOWN: [1, 10],
      LOADING: [2, 30],
      LOGIN_LOADING: [3, 10],
      LOGIN_MAIN_NOENTRY: [3, 10],
      OPERATOR_ONGOING: [10, 30]
    },
    performance_mode: 'high'
  }
  api = {
    get_device_settings: vi.fn(async () => ({
      values: original,
      fields: [
        { key: 'device.preset_id', group: '设备', kind: 'select' },
        { key: 'device.installation_path', group: '设备', kind: 'directory' },
        { key: 'device.manager_path', group: '设备', kind: 'file' },
        { key: 'device.config_path', group: '设备', kind: 'file' },
        { key: 'device.instance_id', group: '设备', kind: 'text' },
        { key: 'device.instance_name', group: '设备', kind: 'text' },
        { key: 'device.game_package', group: '设备', kind: 'select' },
        { key: 'device.screenshot_backend', group: '截图', kind: 'select' },
        { key: 'device.touch_backend', group: '截图', kind: 'select' },
        { key: 'device.last_serial', group: '设备', kind: 'text' },
        { key: 'device.instance_uuid', group: '设备', kind: 'text', read_only: true },
        { key: 'device.topology_fingerprint', group: '设备', kind: 'text', read_only: true },
        { key: 'custom_screenshot.command', group: '截图', kind: 'text' },
        { key: 'performance_mode', group: '性能', kind: 'select' },
        {
          key: 'waiting_scene',
          group: '运行参数',
          kind: 'waiting_scene',
          scenes: [['LOADING', '加载中']]
        }
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
      'device.instance_name': '',
      'device.last_serial': '',
      'device.instance_uuid': '',
      'device.topology_fingerprint': ''
    },
    target,
    original
  )
})

async function loadPolicy(independent = false) {
  const legacy = await api.get_device_settings()
  const sharedKeys = [
    'device.preset_id',
    'device.installation_path',
    'device.manager_path',
    'device.config_path',
    'device.screenshot_backend',
    'device.touch_backend',
    'custom_screenshot.command',
    'performance_mode',
    'waiting_scene'
  ]
  const originalPolicy = {
    revision: 'captured-policy',
    shared_values: Object.fromEntries(
      sharedKeys.map((key) => [
        key,
        key.split('.').reduce((value, part) => value?.[part], original)
      ])
    )
  }
  api.get_device_settings.mockResolvedValue({
    ...legacy,
    independent_configuration: independent,
    shared_keys: sharedKeys,
    original_policy: originalPolicy
  })
  await component.load()
  return originalPolicy
}

it('shows only the three instance inputs with shared connection settings and rejects hidden edits', async () => {
  await loadPolicy()
  expect(component.visibleFields.value.map(({ key }) => key)).toEqual([
    'device.instance_id',
    'device.instance_name',
    'device.game_package'
  ])
  expect(component.groups.value).toEqual(['设备'])
  component.edit('custom_screenshot.command', 'hidden-command')
  component.edit('device.screenshot_backend', 'mumu_ipc')
  component.edit('device.preset_id', 'macos.avd')
  component.edit('device.installation_path', '/hidden')
  component.edit('device.last_serial', 'hidden:5555')
  component.edit('waiting_scene', { ...original.waiting_scene, LOADING: [7, 30] })
  expect(component.changes.value).toEqual({})
  expect(component.hasChanges.value).toBe(false)
  await component.save()
  expect(api.update_device_settings).not.toHaveBeenCalled()
})

it('retains the complete editable form and four-argument discovery for a legacy API', async () => {
  expect(component.visibleFields.value.map(({ key }) => key)).toContain('device.preset_id')
  expect(component.visibleFields.value.map(({ key }) => key)).toContain('device.last_serial')
  expect(component.visibleFields.value.map(({ key }) => key)).toContain('custom_screenshot.command')
  expect(component.visibleFields.value.map(({ key }) => key)).not.toContain('device.instance_uuid')
  await component.detect()
  expect(api.discover_device_settings).toHaveBeenCalledExactlyOnceWith(0, {}, target, original)
})

it('never opens the path picker for a fixed shared template field', async () => {
  await loadPolicy()
  await component.browse({ key: 'device.installation_path', kind: 'directory' })
  expect(api.select_device_path).not.toHaveBeenCalled()
})

it('saves the three manual instance choices with safe identity clearing and no fixed fields', async () => {
  await loadPolicy()
  component.edit('device.instance_id', '2')
  component.edit('device.instance_name', 'second')
  component.edit('device.game_package', 'com.hypergryph.arknights.bilibili')
  await component.save()
  expect(api.update_device_settings.mock.calls[0][1]).toEqual({
    'device.instance_id': '2',
    'device.instance_name': 'second',
    'device.game_package': 'com.hypergryph.arknights.bilibili',
    'device.instance_uuid': '',
    'device.topology_fingerprint': ''
  })
})

it('selects a matching detected instance without submitting its template or ADB address', async () => {
  const originalPolicy = await loadPolicy()
  api.discover_device_settings.mockResolvedValue({
    candidates: [
      {
        key: 'selected',
        binding: {
          preset_id: 'manual.other',
          installation_path: '/saved',
          manager_path: '/saved/tool',
          config_path: '',
          instance_id: '1',
          instance_name: 'second',
          instance_uuid: 'detected-uuid',
          topology_fingerprint: 'detected-fingerprint',
          last_serial: 'unverified:5555'
        }
      }
    ]
  })
  await component.detect()
  expect(api.discover_device_settings).toHaveBeenCalledExactlyOnceWith(0, {}, target, original, {
    independent_configuration: false,
    original_policy: originalPolicy
  })
  component.selectCandidate('selected')
  expect(component.changes.value).toEqual({
    'device.instance_id': '1',
    'device.instance_name': 'second',
    'device.instance_uuid': 'detected-uuid',
    'device.topology_fingerprint': 'detected-fingerprint'
  })
  await component.save()
  expect(api.update_device_settings).toHaveBeenCalledExactlyOnceWith(
    0,
    component.changes.value,
    target,
    original,
    { independent_configuration: false, original_policy: originalPolicy }
  )
})

it.each([
  ['preset_id', 'macos.avd'],
  ['installation_path', '/another'],
  ['manager_path', '/another/tool'],
  ['config_path', '/another.conf']
])('rejects a detected instance with a different shared %s', async (field, value) => {
  await loadPolicy()
  api.discover_device_settings.mockResolvedValue({
    candidates: [
      { key: 'different', binding: { [field]: value, instance_id: '1', instance_uuid: 'other' } }
    ]
  })
  await component.detect()
  component.selectCandidate('different')
  expect(component.changes.value).toEqual({})
  expect(component.error.value).toContain('与通用设置不同')
  expect(component.error.value).toContain('独立配置')
})

it('checks the detected preset even when it is only reported on the candidate', async () => {
  await loadPolicy()
  api.discover_device_settings.mockResolvedValue({
    candidates: [{ key: 'different', preset_id: 'macos.avd', binding: { instance_id: '1' } }]
  })
  await component.detect()
  component.selectCandidate('different')
  expect(component.changes.value).toEqual({})
  expect(component.error.value).toContain('与通用设置不同')
})

it('rejects a candidate the backend identified as outside the shared template', async () => {
  await loadPolicy()
  api.discover_device_settings.mockResolvedValue({
    candidates: [
      { key: 'different', shared_template_matches: false, binding: { instance_id: '1' } }
    ]
  })
  await component.detect()
  component.selectCandidate('different')
  expect(component.changes.value).toEqual({})
  expect(component.error.value).toContain('与通用设置不同')
})

it('accepts the backend projection of a same-template candidate with an automatically resolved path', async () => {
  original.device.manager_path = ''
  await loadPolicy()
  api.discover_device_settings.mockResolvedValue({
    candidates: [
      {
        key: 'projected',
        shared_template_matches: true,
        binding: {
          preset_id: 'manual.other',
          installation_path: '/saved',
          manager_path: '',
          config_path: '',
          instance_id: '1',
          instance_name: 'second'
        }
      }
    ]
  })
  await component.detect()
  component.selectCandidate('projected')
  expect(component.error.value).toBe('')
  expect(component.draft.value['device.manager_path']).toBe('')
  expect(component.changes.value).toEqual({
    'device.instance_id': '1',
    'device.instance_name': 'second',
    'device.instance_uuid': '',
    'device.topology_fingerprint': ''
  })
})

it('clears previous derived identity when a detected candidate supplies no identity metadata', async () => {
  await loadPolicy()
  api.discover_device_settings.mockResolvedValue({
    candidates: [{ key: 'selected', binding: { instance_id: '1', instance_name: 'second' } }]
  })
  await component.detect()
  component.selectCandidate('selected')
  expect(component.changes.value).toEqual({
    'device.instance_id': '1',
    'device.instance_name': 'second',
    'device.instance_uuid': '',
    'device.topology_fingerprint': ''
  })
})

it('enables independent configuration from inherited values without requiring a field edit', async () => {
  const originalPolicy = await loadPolicy()
  component.setIndependent(true)
  expect(component.draft.value.performance_mode).toBe('high')
  expect(component.visibleFields.value.some(({ key }) => key === 'custom_screenshot.command')).toBe(
    true
  )
  expect(component.visibleFields.value).toEqual(
    component.fields.value.filter((field) => !field.read_only)
  )
  expect(component.hasChanges.value).toBe(true)
  await component.save()
  expect(api.update_device_settings).toHaveBeenCalledExactlyOnceWith(0, {}, target, original, {
    independent_configuration: true,
    original_policy: originalPolicy
  })
  expect(emit).toHaveBeenCalledWith('saved')
})

it('uses the captured shared template when disabling a different independent template', async () => {
  await loadPolicy(true)
  component.originalPolicy.value.shared_values['device.preset_id'] = 'macos.avd'
  component.originalPolicy.value.shared_values['device.installation_path'] = '/shared-sdk'
  component.setIndependent(false)
  expect(component.draft.value['device.preset_id']).toBe('macos.avd')
  expect(component.draft.value['device.installation_path']).toBe('/shared-sdk')
  expect(component.changes.value).toEqual({
    'device.instance_uuid': '',
    'device.topology_fingerprint': ''
  })
  await component.detect()
  expect(api.discover_device_settings).toHaveBeenCalledExactlyOnceWith(
    0,
    component.changes.value,
    target,
    original,
    { independent_configuration: false, original_policy: component.originalPolicy.value }
  )
})

it('discards fixed parameter edits when returning to shared configuration and keeps only the instance choice', async () => {
  const originalPolicy = await loadPolicy(true)
  component.edit('performance_mode', 'low')
  component.edit('custom_screenshot.command', 'new-command')
  component.edit('device.preset_id', 'macos.avd')
  component.edit('device.instance_id', '2')
  component.edit('device.instance_name', 'second')
  component.edit('device.last_serial', 'local:5555')
  component.setIndependent(false)
  expect(component.draft.value.performance_mode).toBe('high')
  expect(component.draft.value['custom_screenshot.command']).toBe('saved-command')
  expect(component.draft.value['device.preset_id']).toBe('manual.other')
  expect(component.draft.value['device.last_serial']).toBe('')
  await component.save()
  expect(api.update_device_settings).toHaveBeenCalledExactlyOnceWith(
    0,
    {
      'device.instance_id': '2',
      'device.instance_name': 'second',
      'device.instance_uuid': '',
      'device.topology_fingerprint': ''
    },
    target,
    original,
    { independent_configuration: false, original_policy: originalPolicy }
  )
})

it('retains independent edits when the policy snapshot is rejected by the backend', async () => {
  await loadPolicy()
  component.setIndependent(true)
  component.edit('performance_mode', 'low')
  api.update_device_settings.mockRejectedValue(new Error('通用设置已变化，请重新加载'))
  await component.save()
  expect(component.independentConfiguration.value).toBe(true)
  expect(component.changes.value).toEqual({ performance_mode: 'low' })
  expect(component.error.value).toContain('重新加载')
  expect(emit).not.toHaveBeenCalled()
})

it('saves independent scene waits without mutating the original or inherited snapshot', async () => {
  const originalPolicy = await loadPolicy()
  component.setIndependent(true)
  expect(component.visibleFields.value.some(({ key }) => key === 'waiting_scene')).toBe(true)
  const changed = { ...original.waiting_scene, LOADING: [5, 30] }
  component.edit('waiting_scene', changed)
  expect(component.initial.value.waiting_scene.LOADING).toEqual([2, 30])
  expect(original.waiting_scene.LOADING).toEqual([2, 30])
  expect(originalPolicy.shared_values.waiting_scene.LOADING).toEqual([2, 30])
  expect(component.changes.value).toEqual({ waiting_scene: changed })
  await component.save()
  expect(api.update_device_settings).toHaveBeenCalledExactlyOnceWith(
    0,
    { waiting_scene: changed },
    target,
    original,
    { independent_configuration: true, original_policy: originalPolicy }
  )
})

it('compares waiting values structurally and resets independent table drafts on returning to shared mode', async () => {
  const originalPolicy = await loadPolicy(true)
  component.edit('waiting_scene', structuredClone(original.waiting_scene))
  expect(component.hasChanges.value).toBe(false)
  component.edit('waiting_scene', { ...original.waiting_scene, LOADING: [7, 30] })
  component.setIndependent(false)
  expect(component.draft.value.waiting_scene).toEqual(originalPolicy.shared_values.waiting_scene)
  expect(component.changes.value).toEqual({})
  component.setIndependent(true)
  component.draft.value.waiting_scene.LOADING[0] = 9
  expect(originalPolicy.shared_values.waiting_scene.LOADING).toEqual([2, 30])
  expect(component.initial.value.waiting_scene.LOADING).toEqual([2, 30])
  expect(original.waiting_scene.LOADING).toEqual([2, 30])
})

it('fails closed on a response with incomplete connection inheritance metadata', async () => {
  const legacy = await api.get_device_settings()
  api.get_device_settings.mockResolvedValue({ ...legacy, independent_configuration: false })
  await component.load()
  expect(component.disabled.value).toBe(true)
  expect(component.original.value).toBeNull()
  expect(component.error.value).toContain('继承信息不完整')
  component.setIndependent(true)
  await component.save()
  expect(api.update_device_settings).not.toHaveBeenCalled()
})

async function loadOverrides() {
  const originalPolicy = await loadPolicy()
  const result = await api.get_device_settings()
  originalPolicy.shared_values = {
    ...originalPolicy.shared_values,
    maa_path: '/common/maa',
    screenshot: 2,
    startup_mode: 'window'
  }
  originalPolicy.local_values = { maa_path: '/saved/maa', screenshot: 7 }
  const instanceOverride = { local_keys: [], manager_values: {} }
  api.get_device_settings.mockResolvedValue({
    ...result,
    values: { ...result.values, maa_path: '/common/maa', screenshot: 2, startup_mode: 'window' },
    fields: [
      ...result.fields,
      { key: 'maa_path', label: 'MAA 安装目录', group: '程序位置', kind: 'directory' },
      { key: 'screenshot', label: '截图保存时间（小时）', group: '截图保存', kind: 'number' },
      { key: 'startup_mode', label: '启动方式', group: '实例启动', kind: 'select' }
    ],
    original_policy: originalPolicy,
    instance_override: instanceOverride,
    override_keys: ['maa_path', 'screenshot', 'startup_mode']
  })
  await component.load()
  return originalPolicy
}

it('offers local common-field overrides while retaining shared device connections', async () => {
  const originalPolicy = await loadOverrides()
  expect(component.visibleFields.value.some(({ key }) => key === 'maa_path')).toBe(true)
  component.edit('maa_path', '/forged')
  expect(component.changes.value).toEqual({})
  component.setLocalValue('maa_path', true)
  expect(component.draft.value.maa_path).toBe('/saved/maa')
  component.edit('maa_path', '/instance/maa')
  component.setLocalValue('screenshot', true)
  component.edit('screenshot', 9)
  component.setLocalValue('startup_mode', true)
  component.edit('startup_mode', 'background')
  await component.save()
  expect(api.update_device_settings).toHaveBeenCalledExactlyOnceWith(
    0,
    { maa_path: '/instance/maa', screenshot: 9, startup_mode: 'background' },
    target,
    component.original.value,
    {
      independent_configuration: false,
      original_policy: originalPolicy,
      instance_override: {
        local_keys: ['maa_path', 'screenshot'],
        manager_values: { startup_mode: 'background' }
      }
    }
  )
})

it('returning one item to common settings drops its unsaved edit and preserves other local choices', async () => {
  await loadOverrides()
  component.setLocalValue('maa_path', true)
  component.edit('maa_path', '/unsaved')
  component.setLocalValue('screenshot', true)
  component.edit('screenshot', 9)
  component.setLocalValue('maa_path', false)
  expect(component.draft.value.maa_path).toBe('/common/maa')
  expect(component.changes.value).toEqual({ screenshot: 9 })
  expect(component.instanceOverride.value.local_keys).toEqual(['screenshot'])
  component.setIndependent(true)
  component.setIndependent(false)
  expect(component.draft.value.screenshot).toBe(9)
})
