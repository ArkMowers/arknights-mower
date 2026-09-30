import { describe, expect, it, vi } from 'vitest'
import {
  deviceSettingsState,
  sameDeviceProfile,
  editDeviceDraft,
  manualDeviceDraft,
  devicePreflightRequest,
  deviceAvdStartRequest,
  deviceRedroidStartRequest,
  deviceGenymotionStartRequest,
  deviceStartupRequest,
  deviceSuccessPatch,
  deviceDetectionDraft,
  savePreflightDevice,
  deviceStatusResult,
  saveDiscoveredDevice,
  startPhysicalPreparation,
  isImmediateDeviceField,
  editedDevicePatch
} from './deviceSettings'

const profile = {
  preset_id: 'manual.other',
  instance_name: '',
  config_path: '',
  instance_uuid: '',
  topology_fingerprint: '',
  last_serial: 'emulator-5554',
  screenshot_backend: 'droidcast',
  touch_backend: 'scrcpy',
  game_package: 'com.hypergryph.arknights'
}

it('compares device values independently of property insertion order', () => {
  expect(sameDeviceProfile({ a: 1, b: '2' }, { b: '2', a: 1 })).toBe(true)
  expect(sameDeviceProfile({ a: 1 }, { a: 2 })).toBe(false)
  expect(sameDeviceProfile({ a: 1 }, { a: 1, b: '' })).toBe(false)
})

// The screenshot and touch backends live in their own always-visible group, so a
// repair reads them from there instead of the device-identity form.
const connectionField = (state, key) => state.connectionFields.find((field) => field.key === key)

it.each([
  ['windows.mumu12', 'mumu_ipc'],
  ['windows.ldplayer9', 'ld_native'],
  ['windows.ldplayer14', 'ld_native'],
  ['manual.other', null]
])('limits vendor screenshot choices for %s', (preset, allowed) => {
  const state = deviceSettingsState({
    profile: { ...profile, preset_id: preset },
    metadata: { host_platform: 'windows' }
  })
  for (const backend of ['mumu_ipc', 'ld_native']) {
    const option = connectionField(state, 'screenshot_backend').options.find(
      (o) => o.value === backend
    )
    expect(option).toBeDefined()
    expect(option.disabled).toBe(backend !== allowed)
  }
})

it('offers only MuMu 12 in the Windows MuMu preset menu', () => {
  const state = deviceSettingsState({
    profile,
    metadata: { host_platform: 'windows' },
    advanced: true
  })
  const options = state.fields.find((field) => field.key === 'preset_id').options
  expect(options.filter((option) => option.value.startsWith('windows.mumu'))).toEqual([
    { value: 'windows.mumu12', label: 'MuMu 12' }
  ])
})

it('clears incompatible enhancement when switching a draft preset', () => {
  const mumu = {
    ...profile,
    preset_id: 'windows.mumu12',
    screenshot_backend: 'mumu_ipc',
    touch_backend: 'mumu_ipc'
  }
  const ld = editDeviceDraft(mumu, 'preset_id', 'windows.ldplayer9')
  expect(ld).toMatchObject({
    screenshot_backend: 'droidcast',
    touch_backend: 'scrcpy',
    last_serial: ''
  })
  expect(
    manualDeviceDraft({ ...ld, screenshot_backend: 'ld_native' }, 'manual.other').screenshot_backend
  ).toBe('droidcast')
  expect(mumu.screenshot_backend).toBe('mumu_ipc')
})

it.each([
  ['windows.ldplayer9', 'windows.ldplayer14'],
  ['windows.ldplayer14', 'windows.ldplayer9']
])('keeps LD enhancement while rebinding %s to %s', (from, to) => {
  const next = editDeviceDraft(
    { ...profile, preset_id: from, screenshot_backend: 'ld_native', touch_backend: 'maatouch' },
    'preset_id',
    to
  )
  expect(next).toMatchObject({
    preset_id: to,
    screenshot_backend: 'ld_native',
    touch_backend: 'maatouch',
    last_serial: ''
  })
  expect(editDeviceDraft(next, 'preset_id', 'windows.mumu12').screenshot_backend).toBe('droidcast')
})

it('rejects vendor options on a different host even when capability metadata says available', () => {
  const state = deviceSettingsState({
    profile: { ...profile, preset_id: 'windows.mumu12' },
    metadata: {
      host_platform: 'linux',
      touch_backend_profile: 'windows.mumu12',
      touch_backends: [{ backend: 'mumu_ipc', available: true }]
    }
  })
  for (const key of ['screenshot_backend', 'touch_backend']) {
    expect(connectionField(state, key).options.find((o) => o.value === 'mumu_ipc').disabled).toBe(
      true
    )
  }
})

describe('selected screenshot backend failure', () => {
  it('shows the capture error and peer alternatives while preserving the selected backend', () => {
    const selected = { ...profile, screenshot_backend: 'mumu_ipc', touch_backend: 'mumu_ipc' }
    const before = { ...selected }
    const result = {
      ok: false,
      error: {
        code: 'frame_failed',
        message: 'MuMu IPC 截图失败：原生返回码 -3。',
        fields: ['screenshot_backend'],
        action: 'retry',
        backend: 'mumu_ipc',
        alternatives: [
          { backend: 'adb_gzip', label: 'ADB gzip' },
          { backend: 'droidcast', label: 'DroidCast' },
          { backend: 'custom', label: '自定义命令' }
        ]
      }
    }
    const state = deviceSettingsState({ profile: selected, result })
    expect(state.message).toContain('原生返回码 -3')
    expect(state.screenshotAlternativeMessage).toBe(
      '可选截图后端：ADB gzip、DroidCast、自定义命令。如需更换，请手动选择截图后端并重新检测。'
    )
    expect(state.fields).toEqual([])
    expect(connectionField(state, 'screenshot_backend')).toMatchObject({
      value: 'mumu_ipc',
      disabled: false
    })
    expect(state.actions.detect.label).toBe('重试连接')
    expect(selected).toEqual(before)
    expect(deviceSuccessPatch(before, selected, result)).toEqual({})
  })

  it.each(['frame_failed', 'frame_size_mismatch', 'screenshot_failed'])(
    'shows a %s runtime failure and repair field even after a successful preflight',
    (code) => {
      const metadata = {
        active: false,
        error: {
          code,
          message: 'ADB gzip 返回实际帧 1280×720，需要横屏 1920×1080。',
          fields: ['screenshot_backend'],
          action: 'retry',
          backend: 'adb_gzip',
          alternatives: [{ backend: 'droidcast', label: 'DroidCast' }]
        }
      }
      const selected = { ...profile, screenshot_backend: 'adb_gzip' }
      const state = deviceSettingsState({ profile: selected, metadata, result: { ok: true } })
      expect(state.statusDisplayLabel).toBe('需要配置 / 修复')
      expect(state.message).toContain('实际帧 1280×720')
      expect(state.screenshotAlternativeMessage).toBe(
        '可选截图后端：DroidCast。如需更换，请手动选择截图后端并重新检测。'
      )
      expect(state.preparationMessage).toBe('')
      expect(state.fields).toEqual([])
      expect(connectionField(state, 'screenshot_backend')).toMatchObject({
        value: 'adb_gzip',
        disabled: false
      })
      const active = deviceSettingsState({
        profile: selected,
        metadata: { ...metadata, active: true }
      })
      expect(connectionField(active, 'screenshot_backend').disabled).toBe(true)
      expect(active.actions.detect.disabled).toBe(true)
      expect(selected.screenshot_backend).toBe('adb_gzip')
    }
  )
})

describe('selected touch backend failure', () => {
  it('keeps touch peers visible and explains incompatible capabilities without replacing the selection', () => {
    const selected = { ...profile, screenshot_backend: 'mumu_ipc', touch_backend: 'mumu_ipc' }
    const metadata = {
      host_platform: 'windows',
      touch_backend_profile: 'manual.other',
      touch_backends: [
        { backend: 'scrcpy', label: 'scrcpy 1.21', available: true, reason: '' },
        { backend: 'maatouch', label: 'MaaTouch', available: true, reason: '' },
        {
          backend: 'mumu_ipc',
          label: 'MuMu IPC',
          available: false,
          reason: '需要 MuMu 模拟器 12。'
        }
      ]
    }
    const state = deviceSettingsState({ profile: selected, metadata, advanced: true })
    const touch = connectionField(state, 'touch_backend')
    expect(touch.value).toBe('mumu_ipc')
    expect(touch.options.map((option) => option.value)).toEqual(['scrcpy', 'maatouch', 'mumu_ipc'])
    expect(touch.options[0]).toMatchObject({ label: 'scrcpy 1.21', disabled: false })
    expect(touch.options[1]).toMatchObject({ label: 'MaaTouch', disabled: false })
    expect(touch.options[2]).toMatchObject({
      label: 'MuMu 自带触控（需要 MuMu 模拟器 12。）',
      disabled: true,
      reason: '需要 MuMu 模拟器 12。'
    })
    expect(selected.touch_backend).toBe('mumu_ipc')
    const edited = deviceSettingsState({
      profile: { ...selected, preset_id: 'windows.mumu12' },
      metadata,
      advanced: true
    })
    expect(connectionField(edited, 'touch_backend').options[2].disabled).toBe(false)
    const linux = deviceSettingsState({
      profile: selected,
      metadata: { host_platform: 'linux' },
      advanced: true
    })
    expect(connectionField(linux, 'touch_backend').options[2]).toMatchObject({
      disabled: true,
      reason: '仅适用于 Windows 的 MuMu 12'
    })
  })

  it.each(['touch_initialization_failed', 'touch_result_unknown'])(
    'shows %s and peer alternatives without changing the selected backend',
    (code) => {
      const selected = { ...profile, touch_backend: 'maatouch' }
      const before = { ...selected }
      const error = {
        code,
        message: 'MaaTouch 触控失败，请检查所选后端。',
        fields: ['touch_backend'],
        action: 'configure',
        backend: 'maatouch',
        alternatives: [{ backend: 'scrcpy', label: 'scrcpy 1.21' }]
      }
      for (const context of [
        { result: { ok: false, error } },
        { metadata: { error }, result: { ok: true } }
      ]) {
        const state = deviceSettingsState({ profile: selected, ...context })
        expect(state.statusDisplayLabel).toBe('需要配置 / 修复')
        expect(state.message).toContain('MaaTouch 触控失败')
        expect(state.touchAlternativeMessage).toBe(
          '可选触控后端：scrcpy 1.21。如需更换，请手动选择触控后端并重新检测。'
        )
        expect(state.fields).toEqual([])
        expect(connectionField(state, 'touch_backend')).toMatchObject({
          value: 'maatouch',
          disabled: false
        })
        expect(state.preparationMessage).toBe('')
        expect(deviceSuccessPatch(before, selected, { ok: false, error })).toEqual({})
      }
      expect(selected).toEqual(before)
      const active = deviceSettingsState({ profile: selected, metadata: { active: true, error } })
      expect(connectionField(active, 'touch_backend').disabled).toBe(true)
    }
  )
})

describe('Linux Genymotion compatibility settings', () => {
  const genymotion = {
    ...profile,
    preset_id: 'linux.genymotion',
    instance_id: '12345678-1234-1234-1234-123456789abc',
    instance_name: 'Mower Android',
    manager_path: '/opt/genymobile/genymotion/gmtool',
    last_serial: ''
  }
  const metadata = { host_platform: 'linux' }

  it('separates compatibility from discovery and rechecks only a complete saved VM binding', () => {
    const bound = deviceSettingsState({ profile: genymotion, metadata })
    expect(bound.compatibilityLabel).toBe('兼容性记录')
    expect(bound.discoveryLabel).toBe('官方 gmtool')
    expect(bound.compatibilityNote).toContain('不代表永久支持承诺')
    expect(bound.actions.detect.endpoint).toBe('preflight')
    expect(bound.actions.discover.visible).toBe(true)
    expect(bound.bindingHelp).toContain('只复核所选 VM')
    expect(bound.bindingHelp).toContain('不切换')
    for (const change of [
      { instance_id: '' },
      { instance_id: 'Mower Android' },
      { manager_path: '' }
    ]) {
      const state = deviceSettingsState({ profile: { ...genymotion, ...change }, metadata })
      expect(state.actions.detect.endpoint).toBe('discover')
    }
    const failed = deviceSettingsState({
      profile: genymotion,
      metadata,
      result: { error: { code: 'instance_missing', message: '所选 VM 已失效。' } }
    })
    expect(failed.actions.detect.endpoint).toBe('preflight')
  })

  it('requires immediate confirmation of the complete VM binding before starting', () => {
    const state = deviceSettingsState({ profile: genymotion, metadata })
    expect(state.actions.startBound).toEqual({
      visible: true,
      disabled: false,
      label: '启动并测试连接'
    })
    expect(deviceGenymotionStartRequest(genymotion, genymotion, genymotion.instance_id)).toEqual({
      device: {},
      confirmed_instance: genymotion.instance_id
    })
    for (const confirmed of [null, '', 'Mower Android', '87654321-1234-1234-1234-123456789abc']) {
      expect(() => deviceGenymotionStartRequest(genymotion, genymotion, confirmed)).toThrow()
    }
    for (const change of [{ manager_path: '' }, { instance_id: 'Mower Android' }]) {
      const draft = { ...genymotion, ...change }
      expect(deviceSettingsState({ profile: draft, metadata }).actions.startBound.disabled).toBe(
        true
      )
      expect(() => deviceGenymotionStartRequest(genymotion, draft, draft.instance_id)).toThrow()
    }
    for (const context of [
      { metadata: { host_platform: 'windows' } },
      { metadata: { ...metadata, active: true } },
      { metadata, busy: true }
    ]) {
      expect(
        deviceSettingsState({ profile: genymotion, ...context }).actions.startBound.disabled
      ).toBe(true)
    }
    expect(deviceSettingsState({ profile, metadata }).actions.startBound.visible).toBe(false)
  })

  it('explains unavailable official information and opens complete manual configuration without the old binding', () => {
    const result = {
      error: {
        code: 'genymotion_manual_required',
        action: 'manual',
        fields: ['manager_path'],
        message: 'gmtool 输出不完整，无法确认所选 VM 的连接信息。'
      }
    }
    const state = deviceSettingsState({ profile: genymotion, metadata, result })
    expect(state.message).toContain('gmtool 输出不完整')
    expect(state.actions.manualFallback).toEqual({
      visible: true,
      disabled: false,
      preset: 'manual.other',
      label: '进入高级手动配置'
    })
    const draft = manualDeviceDraft(
      {
        ...genymotion,
        instance_uuid: genymotion.instance_id,
        last_serial: '192.168.56.101:5555',
        game_package_confirmed: true
      },
      state.actions.manualFallback.preset
    )
    expect(draft).toMatchObject({
      preset_id: 'manual.other',
      manager_path: '',
      instance_id: '',
      instance_uuid: '',
      last_serial: '',
      game_package_confirmed: false
    })
    const manual = deviceSettingsState({ profile: draft, metadata, manual: true, advanced: true })
    expect(manual.actions.detect.endpoint).toBe('preflight')
    expect(manual.fields.map((field) => field.key)).toEqual(
      expect.arrayContaining(['last_serial', 'adb_path'])
    )
    // Both backends stay visible whether or not the identity form is open.
    const manualOnly = deviceSettingsState({ profile: draft, metadata, manual: true })
    expect(manualOnly.fields.map((field) => field.key)).toEqual(['last_serial'])
    for (const state of [manual, manualOnly]) {
      expect(state.connectionVisible).toBe(true)
      expect(state.connectionFields.map((field) => field.key)).toEqual([
        'screenshot_backend',
        'touch_backend'
      ])
    }
  })

  it('distinguishes equal VM names by UUID and saves only the explicitly selected identity', async () => {
    const otherUuid = '87654321-1234-1234-1234-123456789abc'
    const candidates = [genymotion.instance_id, otherUuid].map((instance_id) => ({
      key: instance_id,
      preset_id: 'linux.genymotion',
      instance_id,
      instance_name: 'Mower Android',
      state: 'running',
      binding: { ...genymotion, instance_id, instance_uuid: instance_id }
    }))
    const result = { kind: 'discovery', candidates, selected_key: null }
    const state = deviceSettingsState({ profile: genymotion, metadata, result })
    expect(state.instances.value).toBe(null)
    expect(state.instances.options[0].label).toContain(genymotion.instance_id)
    expect(state.instances.options[1].label).toContain(otherUuid)
    const config = {
      device_profile: { ...genymotion, last_serial: '192.168.56.101:5555' },
      flush_config_saves: async () => {},
      save_config: async () => {}
    }
    const selected = await saveDiscoveredDevice({
      config,
      profile: config.device_profile,
      result,
      key: otherUuid
    })
    expect(selected).toMatchObject({
      instance_id: otherUuid,
      instance_uuid: otherUuid,
      manager_path: '/opt/genymobile/genymotion/gmtool',
      last_serial: '',
      game_package_confirmed: false
    })
  })
})

describe('local Docker redroid device settings', () => {
  const redroid = {
    ...profile,
    preset_id: 'linux.redroid',
    instance_id: 'a'.repeat(64),
    instance_name: 'mower-redroid',
    installation_path: '/usr/bin',
    manager_path: '/usr/bin/docker',
    config_path: 'unix:///var/run/docker.sock',
    last_serial: ''
  }
  const metadata = { host_platform: 'linux' }

  it('discovers unbound containers and preflights only a saved local binding', () => {
    const bound = deviceSettingsState({ profile: redroid, metadata })
    expect(bound.actions.detect.endpoint).toBe('preflight')
    expect(bound.actions.startBound).toMatchObject({
      visible: true,
      disabled: false
    })
    for (const change of [
      { instance_id: '' },
      { instance_id: 'mower-redroid' },
      { config_path: 'tcp://remote:2375' },
      { manager_path: '' }
    ]) {
      const state = deviceSettingsState({ profile: { ...redroid, ...change }, metadata })
      expect(state.actions.detect.endpoint).toBe('discover')
      expect(state.actions.startBound.disabled).toBe(true)
    }
    expect(bound.summary).toContain('mower-redroid')
  })

  it('sends an immediate exact-container confirmation without storing launch consent', () => {
    const request = deviceRedroidStartRequest(redroid, redroid, redroid.instance_id)
    expect(request).toEqual({ device: {}, confirmed_instance: redroid.instance_id })
    for (const confirmed of [null, '', 'mower-redroid', 'b'.repeat(64)]) {
      expect(() => deviceRedroidStartRequest(redroid, redroid, confirmed)).toThrow()
    }
  })

  it('locks launch on the wrong host or active session and offers explicit manual fallback', () => {
    for (const context of [
      { metadata: { host_platform: 'windows' } },
      { metadata: { ...metadata, active: true } },
      { metadata, busy: true }
    ]) {
      expect(
        deviceSettingsState({ profile: redroid, ...context }).actions.startBound.disabled
      ).toBe(true)
    }
    const unsupported = deviceSettingsState({
      profile: redroid,
      metadata,
      result: { error: { code: 'redroid_manual_required', action: 'manual' } }
    })
    expect(unsupported.actions.manualFallback).toMatchObject({
      visible: true,
      preset: 'manual.other'
    })
    const replaced = deviceSettingsState({
      profile: redroid,
      metadata,
      result: { error: { code: 'redroid_binding_changed', action: 'select' } }
    })
    expect(replaced.actions.detect.endpoint).toBe('discover')
  })
})

const discoveredInstance = {
  key: 'mumu-c-0',
  preset_id: 'windows.mumu12',
  instance_id: '0',
  instance_name: '主账号',
  installation_path: 'C:/MuMuPlayer-12.0',
  state: 'stopped',
  serial: '',
  binding: {
    preset_id: 'windows.mumu12',
    instance_id: '0',
    instance_name: '主账号',
    installation_path: 'C:/MuMuPlayer-12.0',
    manager_path: 'C:/MuMuPlayer-12.0/shell/MuMuManager.exe',
    last_serial: '',
    game_package_confirmed: false
  },
  preflight: null,
  error: { code: 'instance_stopped', message: '请先启动已选实例', fields: [] }
}

describe('device settings state', () => {
  it('discovers an unbound Waydroid and preflights only its saved environment', () => {
    const metadata = { host_platform: 'linux' }
    const unbound = { ...profile, preset_id: 'linux.waydroid', instance_id: '', last_serial: '' }
    const initial = deviceSettingsState({ profile: unbound, metadata })
    expect(initial.actions.detect.endpoint).toBe('discover')
    expect(initial.actions.discover.visible).toBe(true)
    const bound = {
      ...unbound,
      manager_path: '/usr/bin/waydroid',
      installation_path: '/usr/bin',
      config_path: '/home/mower/.local/share/waydroid',
      instance_id: 'waydroid:1000'
    }
    const selected = deviceSettingsState({ profile: bound, metadata })
    expect(selected.actions.detect.endpoint).toBe('preflight')
    expect(selected.actions.discover.visible).toBe(true)
  })
  it('requires a Waydroid user identity and paths before treating a selection as bound', () => {
    const bound = {
      ...profile,
      preset_id: 'linux.waydroid',
      installation_path: '/usr/bin',
      manager_path: '/usr/bin/waydroid',
      config_path: '/home/mower/.local/share/waydroid',
      instance_id: 'waydroid:1000',
      last_serial: ''
    }
    const metadata = { host_platform: 'linux' }
    for (const repair of [
      { instance_id: '' },
      { instance_id: '-1' },
      { instance_id: '1000' },
      { instance_id: 'waydroid:other' },
      { installation_path: '' },
      { manager_path: '' },
      { config_path: '' },
      { config_path: ' ' }
    ]) {
      expect(
        deviceSettingsState({ profile: { ...bound, ...repair }, metadata }).actions.detect.endpoint
      ).toBe('discover')
    }
    for (const context of [{ busy: true }, { metadata: { ...metadata, active: true } }]) {
      const state = deviceSettingsState({ profile: bound, metadata, ...context })
      expect(state.actions.detect.disabled).toBe(true)
      expect(state.actions.discover.disabled).toBe(true)
    }
  })
  it('shows Waydroid as a Linux primary environment with official connection guidance', () => {
    const waydroid = { ...profile, preset_id: 'linux.waydroid', last_serial: '' }
    const state = deviceSettingsState({
      profile: waydroid,
      metadata: { host_platform: 'linux' },
      advanced: true
    })
    expect(state.compatibilityLabel).toBe('主要对象')
    expect(state.discoveryLabel).toBe('官方状态与 ADB 连接信息')
    expect(state.bindingHelp).toContain('waydroid status')
    expect(state.bindingHelp).toContain('IP:5555')
    expect(state.bindingHelp).toContain('同一用户')
    expect(state.bindingHelp).toContain('数据目录')
    expect(state.fields.find((field) => field.key === 'config_path').label).toBe(
      'Waydroid 数据目录'
    )
    for (const host_platform of ['linux', 'windows', 'macos']) {
      const options = deviceSettingsState({
        profile,
        metadata: { host_platform },
        advanced: true
      }).fields.find((field) => field.key === 'preset_id').options
      expect(options.some((option) => option.value === 'linux.waydroid')).toBe(
        host_platform === 'linux'
      )
    }
  })
  it('saves the selected Waydroid user binding without persisting its discovered endpoint', async () => {
    const binding = {
      preset_id: 'linux.waydroid',
      installation_path: '/usr/bin',
      manager_path: '/usr/bin/waydroid',
      config_path: '/home/mower/.local/share/waydroid',
      instance_id: 'waydroid:1000',
      instance_name: 'Waydroid UID 1000',
      last_serial: '',
      game_package_confirmed: false
    }
    const result = {
      kind: 'discovery',
      selected_key: 'waydroid-user-1000',
      candidates: [
        {
          ...binding,
          key: 'waydroid-user-1000',
          state: 'running',
          serial: '192.168.240.112:5555',
          binding
        }
      ]
    }
    const config = {
      device_profile: profile,
      flush_config_saves: vi.fn(async () => {}),
      save_config: vi.fn(async () => {})
    }
    const state = deviceSettingsState({ profile, result, metadata: { host_platform: 'linux' } })
    expect(state.instances.value).toBe('waydroid-user-1000')
    expect(state.instances.options[0].label).toBe(
      'Waydroid · Waydroid UID 1000 · 运行中 · /usr/bin'
    )
    const saved = await saveDiscoveredDevice({
      config,
      profile,
      result,
      key: state.instances.value
    })
    expect(saved).toMatchObject(binding)
    expect(saved.last_serial).toBe('')
    expect(saved).not.toHaveProperty('state')
    expect(saved).not.toHaveProperty('key')
    expect(
      deviceSettingsState({ profile: saved, metadata: { host_platform: 'linux' } }).actions.detect
        .endpoint
    ).toBe('preflight')
  })
  it('keeps Waydroid failures on the selected environment and shows only requested repairs', () => {
    const bound = {
      ...profile,
      preset_id: 'linux.waydroid',
      installation_path: '/usr/bin',
      manager_path: '/usr/bin/waydroid',
      config_path: '/home/mower/.local/share/waydroid',
      instance_id: 'waydroid:1000',
      last_serial: ''
    }
    for (const [code, fields, message] of [
      ['missing_installation', ['manager_path'], '请安装 Waydroid 或修正管理程序路径。'],
      ['waydroid_uninitialized', [], '请先初始化 Waydroid。'],
      ['instance_stopped', [], '请启动已绑定的 Waydroid 会话。'],
      ['endpoint_unresolved', ['last_serial'], '请通过官方状态确认当前连接地址。'],
      ['endpoint_ambiguous', ['last_serial'], '请补充属于当前 Waydroid 环境的 serial。']
    ]) {
      const state = deviceSettingsState({
        profile: bound,
        metadata: { host_platform: 'linux' },
        result: { ok: false, error: { code, fields, message, action: 'retry' } }
      })
      expect(state.fields.map((field) => field.key)).toEqual(fields)
      expect(state.message).toBe(message)
      expect(state.actions.detect.endpoint).toBe('preflight')
      expect(state.actions.detect.label).toBe('启动并检测')
    }
  })
  it('requires a fresh Waydroid selection when the official session identity changes', () => {
    const bound = {
      ...profile,
      preset_id: 'linux.waydroid',
      installation_path: '/usr/bin',
      manager_path: '/usr/bin/waydroid',
      config_path: '/home/mower/.local/share/waydroid',
      instance_id: 'waydroid:1000'
    }
    const state = deviceSettingsState({
      profile: bound,
      metadata: { host_platform: 'linux' },
      result: {
        ok: false,
        error: {
          code: 'waydroid_binding_changed',
          fields: [],
          message: 'Waydroid 用户或数据目录已变化，请重新发现并确认环境。'
        }
      }
    })
    expect(state.actions.detect.endpoint).toBe('discover')
    expect(state.actions.detect.label).toBe('检测实例')
    expect(state.fields).toEqual([])
    expect(state.message).toContain('重新发现并确认')
  })
  it('preflights and saves an explicitly reentered manual endpoint equal to the old MuMu Pro serial', async () => {
    const previous = {
      ...profile,
      preset_id: 'macos.mumu_pro',
      installation_path: '/Applications/MuMuPro.app',
      manager_path: '/Applications/MuMuPro.app/Contents/MacOS/mumutool',
      instance_id: '0',
      last_serial: '127.0.0.1:16384',
      game_package_confirmed: true
    }
    const manual = manualDeviceDraft(previous, 'manual.other')
    expect(manual.last_serial).toBe('')
    const draft = editDeviceDraft(manual, 'last_serial', '127.0.0.1:16384')
    const request = devicePreflightRequest(previous, draft)
    expect(request.device).toMatchObject({
      preset_id: 'manual.other',
      installation_path: '',
      manager_path: '',
      instance_id: '',
      last_serial: '127.0.0.1:16384',
      game_package_confirmed: false
    })
    const result = {
      ok: true,
      serial: '127.0.0.1:16384',
      adb_path: 'manual-adb',
      game_package: 'com.hypergryph.arknights'
    }
    const saved = []
    const config = {
      device_profile: { ...previous },
      flush_config_saves: async () => {},
      save_config: async (confirmation) => {
        saved.push({ profile: { ...config.device_profile }, confirmation })
      }
    }
    const accepted = await savePreflightDevice({ config, profile: draft, result })
    expect(saved).toHaveLength(2)
    expect(saved[0]).toMatchObject({
      profile: {
        preset_id: 'manual.other',
        instance_id: '',
        last_serial: '',
        game_package_confirmed: false
      },
      confirmation: undefined
    })
    expect(saved[1]).toMatchObject({
      profile: {
        preset_id: 'manual.other',
        instance_id: '',
        last_serial: '127.0.0.1:16384',
        game_package_confirmed: true
      },
      confirmation: { serial: '127.0.0.1:16384', game_package: 'com.hypergryph.arknights' }
    })
    expect(accepted).toEqual(saved[1].profile)
  })
  it('offers explicit manual fallback for unconfirmed MuMu Pro output and clears the old target', () => {
    const bound = {
      ...profile,
      preset_id: 'macos.mumu_pro',
      installation_path: '/Applications/MuMuPro.app',
      manager_path: '/Applications/MuMuPro.app/Contents/MacOS/mumutool',
      instance_id: '0',
      instance_name: 'MuMu Pro 1',
      last_serial: '127.0.0.1:16384',
      game_package_confirmed: true
    }
    const metadata = { host_platform: 'darwin' }
    const result = {
      ok: false,
      error: {
        code: 'manager_output',
        action: 'manual',
        fields: ['manager_path', 'last_serial'],
        message: '无法确认当前实例，请使用高级手动配置。'
      }
    }
    const state = deviceSettingsState({ profile: bound, metadata, result, advanced: true })
    expect(state.actions.manualFallback).toEqual({
      visible: true,
      disabled: false,
      preset: 'macos.mumu_pro',
      label: '手动填写连接地址'
    })
    expect(state.fields.map((field) => field.key)).toContain('last_serial')
    expect(state.fields.map((field) => field.key)).toContain('manager_path')
    expect(
      deviceSettingsState({ profile: bound, metadata: { ...metadata, active: true }, result })
        .actions.manualFallback.disabled
    ).toBe(true)
    expect(deviceSettingsState({ profile: bound, metadata }).actions.manualFallback.visible).toBe(
      false
    )
    const manual = manualDeviceDraft(bound, state.actions.manualFallback.preset)
    expect(manual).toMatchObject({
      preset_id: 'macos.mumu_pro',
      installation_path: '',
      manager_path: '',
      instance_id: '',
      instance_name: '',
      last_serial: '',
      game_package_confirmed: false
    })
    const fallback = deviceSettingsState({
      profile: manual,
      metadata,
      manual: true,
      advanced: true
    })
    expect(fallback.actions.detect.endpoint).toBe('preflight')
    expect(fallback.fields.find((field) => field.key === 'last_serial').value).toBe('')
  })
  it('marks MuMu Pro discovery as pending and sends a bound target only to preflight', () => {
    const metadata = { host_platform: 'darwin' }
    const unbound = { ...profile, preset_id: 'macos.mumu_pro', instance_id: '', last_serial: '' }
    const state = deviceSettingsState({ profile: unbound, metadata })
    expect(state.compatibilityLabel).toBe('兼容性记录')
    expect(state.discoveryLabel).toBe('官方 mumutool')
    expect(state.compatibilityNote).toContain('列出实例')
    expect(state.compatibilityNote).toContain('端口被其他实例复用')
    const advancedState = deviceSettingsState({ profile: unbound, metadata, advanced: true })
    expect(advancedState.fields.find((field) => field.key === 'installation_path').help).toContain(
      '/Applications/MuMuPlayer.app'
    )
    expect(advancedState.fields.find((field) => field.key === 'manager_path').help).toContain(
      '核验所选实例后可启动或关闭'
    )
    expect(state.fields.map((field) => field.key)).not.toContain('instance_id')
    expect(state.actions.detect.endpoint).toBe('discover')
    expect(state.actions.discover.visible).toBe(true)
    const bound = {
      ...unbound,
      instance_id: '0',
      manager_path: '/Applications/MuMuPro.app/Contents/MacOS/mumutool',
      last_serial: '127.0.0.1:16384'
    }
    const failed = deviceSettingsState({
      profile: bound,
      metadata,
      result: { ok: false, error: { code: 'endpoint_failed', fields: ['last_serial'] } }
    })
    expect(failed.actions.detect.endpoint).toBe('preflight')
    expect(failed.actions.discover.visible).toBe(true)
    expect(failed.fields.map((field) => field.key)).toContain('last_serial')
    const serialOnly = { ...unbound, last_serial: '127.0.0.1:16384' }
    expect(deviceSettingsState({ profile: serialOnly, metadata }).actions.detect.endpoint).toBe(
      'preflight'
    )
    expect(deviceSettingsState({ profile, metadata }).compatibilityLabel).toBe('')
  })
  it('lists MuMu Pro instances by index and serial and verifies the selected binding', () => {
    const result = {
      kind: 'discovery',
      status: 'selection_required',
      candidates: [
        {
          key: 'one',
          preset_id: 'macos.mumu_pro',
          instance_id: '0',
          instance_name: 'VM 0',
          state: 'running',
          serial: '127.0.0.1:16384'
        },
        {
          key: 'two',
          preset_id: 'macos.mumu_pro',
          instance_id: '1',
          instance_name: 'VM 1',
          state: 'running',
          serial: '127.0.0.1:16416'
        }
      ]
    }
    const unbound = { ...profile, preset_id: 'macos.mumu_pro', last_serial: '' }
    const state = deviceSettingsState({
      profile: unbound,
      metadata: { host_platform: 'macos' },
      result
    })
    expect(state.instances.options).toHaveLength(2)
    expect(state.instances.options[1].label).toContain('VM 1 · 实例 1 · 运行中 · 127.0.0.1:16416')
    const bound = {
      ...unbound,
      instance_id: '1',
      topology_fingerprint: 'a'.repeat(64),
      last_serial: '127.0.0.1:16416'
    }
    const boundState = deviceSettingsState({
      profile: bound,
      metadata: { host_platform: 'macos' },
      advanced: true
    })
    expect(boundState.actions.detect.endpoint).toBe('preflight')
    expect(boundState.compatibilityNote).toContain('实例文件路径核验')
    expect(boundState.fields.map((field) => field.key)).toContain('instance_id')
  })
  it('shows a repeated discovery failure only once', () => {
    const error = {
      code: 'mumu_pro_manager_missing',
      message: '未找到 MuMu Pro 的 mumutool',
      action: 'manual',
      fields: ['manager_path']
    }
    const state = deviceSettingsState({
      profile: { ...profile, preset_id: 'macos.mumu_pro' },
      metadata: { host_platform: 'macos', error },
      result: { kind: 'discovery', error, errors: [error] }
    })
    expect(state.message).toBe(error.message)
    expect(state.preparationMessage).toBe('')
    expect(state.actions.manualFallback.visible).toBe(true)
  })
  it('submits one immediate AVD confirmation for the exact instance without persisting consent', () => {
    const bound = {
      ...profile,
      preset_id: 'linux.avd',
      instance_id: 'Mower_API_35',
      installation_path: '/opt/android-sdk',
      last_serial: ''
    }
    const draft = { ...bound, adb_path: '/custom/adb' }
    expect(
      deviceAvdStartRequest(bound, draft, 'Mower_API_35', 'com.hypergryph.arknights.bilibili')
    ).toEqual({
      device: { adb_path: '/custom/adb' },
      confirmed_instance: 'Mower_API_35',
      confirmed_package: 'com.hypergryph.arknights.bilibili'
    })
    expect(draft).not.toHaveProperty('confirmed_instance')
    for (const confirmed of [null, '', 'Other_AVD']) {
      expect(() => deviceAvdStartRequest(bound, draft, confirmed)).toThrow('重新确认')
    }
    expect(() => deviceAvdStartRequest(profile, profile, 'Mower_API_35')).toThrow('重新确认')
  })
  it('requires a bound AVD and a separate launch confirmation action without changing detection', () => {
    const avd = {
      ...profile,
      preset_id: 'linux.avd',
      installation_path: '/opt/android-sdk',
      manager_path: '/opt/android-sdk/emulator/emulator',
      instance_id: 'Mower_API_35',
      instance_name: 'Mower_API_35',
      last_serial: ''
    }
    const metadata = { host_platform: 'linux' }
    const result = {
      ok: false,
      error: {
        code: 'start_confirmation_required',
        fields: [],
        message: '请确认启动已绑定 AVD。'
      }
    }
    const state = deviceSettingsState({ profile: avd, metadata, result })
    expect(state.actions.startBound).toEqual({
      visible: true,
      disabled: false,
      label: '启动并测试连接'
    })
    expect(state.actions.detect.endpoint).toBe('preflight')
    expect(state.bindingHelp).toContain('普通退出不会关闭')
    expect(state.bindingHelp).toContain('mower 启动')
    for (const context of [{ busy: true }, { metadata: { ...metadata, active: true } }]) {
      expect(
        deviceSettingsState({ profile: avd, metadata, ...context }).actions.startBound.disabled
      ).toBe(true)
    }
    for (const instance_id of ['', '-1', 'Mower;other']) {
      expect(
        deviceSettingsState({ profile: { ...avd, instance_id }, metadata }).actions.startBound
          .disabled
      ).toBe(true)
    }
    expect(deviceSettingsState({ profile, metadata }).actions.startBound.visible).toBe(false)
    expect(
      deviceSettingsState({ profile: avd, metadata: { host_platform: 'windows' } }).actions
        .startBound.disabled
    ).toBe(true)
  })
  it('discovers AVDs on Mac and Linux while keeping a selected AVD on read-only preflight', () => {
    for (const host_platform of ['macos', 'darwin', 'linux']) {
      const preset_id = host_platform === 'linux' ? 'linux.avd' : 'macos.avd'
      const metadata = { host_platform }
      const fresh = { ...profile, last_serial: '' }
      expect(deviceSettingsState({ profile: fresh, metadata }).actions.detect.endpoint).toBe(
        'discover'
      )
      const unbound = { ...fresh, preset_id, instance_id: '' }
      expect(deviceSettingsState({ profile: unbound, metadata }).actions.detect.endpoint).toBe(
        'discover'
      )
      const bound = {
        ...unbound,
        instance_id: 'Mower_API_35',
        installation_path: '/opt/android-sdk',
        manager_path: '/opt/android-sdk/emulator/emulator'
      }
      const state = deviceSettingsState({ profile: bound, metadata, advanced: true })
      expect(state.actions.detect.endpoint).toBe('preflight')
      expect(state.actions.discover.visible).toBe(true)
      expect(state.fields.find((field) => field.key === 'installation_path').label).toBe(
        'Android SDK 目录'
      )
      expect(state.fields.find((field) => field.key === 'preset_id').options).toContainEqual({
        value: preset_id,
        label: 'Android Virtual Device'
      })
      expect(deviceSettingsState({ profile, metadata }).actions.detect.endpoint).toBe('preflight')
    }
    const windows = deviceSettingsState({
      profile,
      metadata: { host_platform: 'windows' },
      advanced: true
    })
    expect(
      windows.fields
        .find((field) => field.key === 'preset_id')
        .options.some((item) => item.value.endsWith('.avd'))
    ).toBe(false)
  })
  it.each(['manual.other', 'macos.bluestacks_air'])(
    'resubmits an explicitly reselected Air serial after changing the %s binding',
    (preset_id) => {
      const previous = {
        ...profile,
        preset_id,
        installation_path: '/Previous/BlueStacks.app',
        last_serial: '127.0.0.1:5555'
      }
      const detected = deviceDetectionDraft(previous, {
        preset_id: 'macos.bluestacks_air',
        ok: false,
        error: { code: 'multiple_devices', fields: ['last_serial'] }
      })
      const repaired = editDeviceDraft(
        detected,
        'installation_path',
        '/Applications/BlueStacks.app'
      )
      expect(repaired.last_serial).toBe('')
      const selected = editDeviceDraft(repaired, 'last_serial', '127.0.0.1:5555')
      expect(devicePreflightRequest(previous, selected).device).toMatchObject({
        installation_path: '/Applications/BlueStacks.app',
        last_serial: '127.0.0.1:5555'
      })
      expect(deviceSettingsState({ profile: selected }).actions.detect.endpoint).toBe('preflight')
    }
  )
  it('includes explicit Air and manual serials in read-only requests even when unchanged', () => {
    const unbound = { ...profile, preset_id: 'macos.bluestacks_air', last_serial: '' }
    expect(devicePreflightRequest(unbound, unbound)).toEqual({ device: { last_serial: '' } })
    expect(devicePreflightRequest(profile, profile)).toEqual({
      device: { last_serial: 'emulator-5554' }
    })
  })
  it('drops previous product paths and incompatible backends after detecting Air', () => {
    const previous = {
      ...profile,
      preset_id: 'windows.nox',
      installation_path: 'C:/Nox',
      manager_path: 'C:/Nox/NoxConsole.exe',
      config_path: 'C:/Nox/config.ini',
      instance_id: 'Nox_0',
      instance_name: '旧实例',
      instance_uuid: 'old-vm',
      topology_fingerprint: 'old-topology',
      adb_path: '/custom/adb',
      screenshot_backend: 'mumu_ipc',
      touch_backend: 'mumu_ipc'
    }
    expect(
      deviceDetectionDraft(previous, { preset_id: 'macos.bluestacks_air', ok: false })
    ).toEqual({
      ...previous,
      preset_id: 'macos.bluestacks_air',
      screenshot_backend: 'droidcast',
      touch_backend: 'scrcpy',
      installation_path: '',
      manager_path: '',
      config_path: '',
      instance_id: '',
      instance_name: '',
      instance_uuid: '',
      topology_fingerprint: '',
      last_serial: '',
      game_package_confirmed: false
    })
    const repaired = {
      ...previous,
      preset_id: 'macos.bluestacks_air',
      installation_path: '/Custom/BlueStacks.app'
    }
    expect(
      deviceDetectionDraft(repaired, { preset_id: 'macos.bluestacks_air', ok: false })
    ).toEqual(repaired)
  })
  it('keeps Air repair and package retries on the detected preset without saving a failed result', () => {
    const fresh = { ...profile, last_serial: '', game_package_confirmed: true }
    const failed = {
      kind: 'preflight',
      preset_id: 'macos.bluestacks_air',
      ok: false,
      profile_patch: {},
      error: { code: 'multiple_devices', fields: ['last_serial'] }
    }
    const draft = deviceDetectionDraft(fresh, failed)
    expect(draft).toMatchObject({
      preset_id: 'macos.bluestacks_air',
      last_serial: '',
      game_package_confirmed: false
    })
    const selected = editDeviceDraft(draft, 'last_serial', '127.0.0.1:5555')
    expect(devicePreflightRequest(fresh, selected).device).toMatchObject({
      preset_id: 'macos.bluestacks_air',
      last_serial: '127.0.0.1:5555'
    })
    expect(
      deviceSettingsState({
        profile: selected,
        result: failed,
        metadata: { host_platform: 'macos' }
      }).actions.detect.endpoint
    ).toBe('preflight')
    expect(deviceSuccessPatch(fresh, selected, failed)).toEqual({})
    expect(fresh.preset_id).toBe('manual.other')
    expect(
      deviceDetectionDraft(selected, { ...failed, error: { code: 'game_package_ambiguous' } })
        .last_serial
    ).toBe('127.0.0.1:5555')
  })
  it('detects BlueStacks Air on a fresh Mac and keeps manual targets explicit', () => {
    const fresh = { ...profile, last_serial: '' }
    for (const host_platform of ['darwin', 'macos']) {
      const metadata = { host_platform }
      const state = deviceSettingsState({ profile: fresh, metadata, advanced: true })
      expect(state.actions.detect.endpoint).toBe('discover')
      expect(state.actions.discover.visible).toBe(false)
      expect(state.fields.find((field) => field.key === 'preset_id').options).toContainEqual({
        value: 'macos.bluestacks_air',
        label: 'BlueStacks Air'
      })
      expect(
        deviceSettingsState({ profile: fresh, metadata, manual: true }).actions.detect.endpoint
      ).toBe('preflight')
      expect(deviceSettingsState({ profile, metadata }).actions.detect.endpoint).toBe('preflight')
    }
    for (const host_platform of ['windows', 'linux']) {
      const state = deviceSettingsState({
        profile: fresh,
        metadata: { host_platform },
        advanced: true
      })
      expect(
        state.fields.find((field) => field.key === 'preset_id').options.map((item) => item.value)
      ).not.toContain('macos.bluestacks_air')
    }
  })
  it('shows actionable Air ADB guidance and serial choices without instance or lifecycle controls', () => {
    const air = { ...profile, preset_id: 'macos.bluestacks_air', last_serial: '' }
    const result = {
      kind: 'preflight',
      preset_id: 'macos.bluestacks_air',
      ok: false,
      guidance: '在 BlueStacks Air 设置 → 高级中启用 Android Debug Bridge，然后重试检测。',
      error: {
        code: 'multiple_devices',
        message: '请选择明确的 ADB 设备。',
        action: 'retry',
        fields: ['last_serial']
      },
      candidates: [
        { serial: '127.0.0.1:5555', state: 'device' },
        { serial: 'USB-phone', state: 'device' }
      ]
    }
    const state = deviceSettingsState({
      profile: air,
      result,
      metadata: { host_platform: 'macos' }
    })
    expect(state.statusDisplayLabel).toBe('需要配置 / 修复')
    expect(state.guidance).toBe(result.guidance)
    expect(state.message).toBe('请选择明确的 ADB 设备。')
    expect(state.instances).toBe(null)
    expect(state.actions.detect).toMatchObject({
      label: '重试连接',
      disabled: false,
      endpoint: 'preflight'
    })
    expect(state.actions.detect.options.map((option) => option.key)).toEqual(['detect'])
    expect(state.actions.discover.visible).toBe(false)
    expect(state.actions.prepare.visible).toBe(false)
    expect(state.fields).toMatchObject([
      {
        key: 'last_serial',
        value: '',
        kind: 'select',
        options: [
          { value: '127.0.0.1:5555', label: '127.0.0.1:5555 · device' },
          { value: 'USB-phone', label: 'USB-phone · device' }
        ]
      }
    ])
    const advanced = deviceSettingsState({ profile: air, result, advanced: true })
    expect(advanced.fields.find((field) => field.key === 'installation_path').label).toBe(
      '应用路径'
    )
    for (const key of ['instance_id', 'instance_name', 'manager_path', 'config_path']) {
      expect(advanced.fields.map((field) => field.key)).not.toContain(key)
    }
  })
  it('persists the validated Air application and serial without retaining an old instance binding', () => {
    const previous = {
      ...profile,
      preset_id: 'windows.mumu12',
      manager_path: 'C:/MuMu/manager.exe',
      config_path: '',
      instance_id: '0',
      instance_name: '旧账号',
      instance_uuid: '',
      topology_fingerprint: ''
    }
    const result = {
      ok: true,
      kind: 'preflight',
      preset_id: 'macos.bluestacks_air',
      serial: '127.0.0.1:5555',
      adb_path: '/Applications/BlueStacks.app/Contents/MacOS/hd-adb',
      game_package: 'com.hypergryph.arknights',
      guidance: '请手动管理 BlueStacks Air。',
      profile_patch: {
        preset_id: 'macos.bluestacks_air',
        installation_path: '/Applications/BlueStacks.app',
        manager_path: '',
        config_path: '',
        instance_id: '',
        instance_name: '',
        instance_uuid: '',
        topology_fingerprint: ''
      }
    }
    expect(deviceSuccessPatch(previous, previous, result)).toEqual({
      device: {
        preset_id: 'macos.bluestacks_air',
        installation_path: '/Applications/BlueStacks.app',
        manager_path: '',
        instance_id: '',
        instance_name: '',
        last_serial: '127.0.0.1:5555',
        adb_path: '/Applications/BlueStacks.app/Contents/MacOS/hd-adb',
        game_package_confirmed: true
      }
    })
    expect(deviceSuccessPatch(previous, previous, { ...result, ok: false })).toEqual({})
  })
  it('saves an Air binding before its verified endpoint even when the previous target used the same serial', async () => {
    const oldProfile = {
      ...profile,
      preset_id: 'windows.nox',
      last_serial: '127.0.0.1:5555',
      instance_uuid: 'old-nox-vm',
      topology_fingerprint: 'old-topology'
    }
    const saved = []
    const config = {
      device_profile: oldProfile,
      flush_config_saves: vi.fn(async () => {}),
      save_config: async (confirmation) => {
        saved.push({ profile: { ...config.device_profile }, confirmation })
      }
    }
    const result = {
      ok: true,
      serial: '127.0.0.1:5555',
      adb_path: '/Applications/BlueStacks.app/Contents/MacOS/hd-adb',
      game_package: 'com.hypergryph.arknights',
      profile_patch: {
        preset_id: 'macos.bluestacks_air',
        installation_path: '/Applications/BlueStacks.app',
        manager_path: '',
        config_path: '',
        instance_id: '',
        instance_name: '',
        instance_uuid: '',
        topology_fingerprint: ''
      }
    }
    const accepted = await savePreflightDevice({ config, profile: oldProfile, result })
    expect(saved).toHaveLength(2)
    expect(saved[0]).toMatchObject({
      profile: {
        preset_id: 'macos.bluestacks_air',
        last_serial: '',
        game_package_confirmed: false,
        instance_uuid: '',
        topology_fingerprint: ''
      },
      confirmation: undefined
    })
    expect(saved[1]).toMatchObject({
      profile: {
        preset_id: 'macos.bluestacks_air',
        last_serial: '127.0.0.1:5555',
        game_package_confirmed: true
      },
      confirmation: { serial: '127.0.0.1:5555', game_package: 'com.hypergryph.arknights' }
    })
    expect(accepted).toEqual(saved[1].profile)
  })
  it('retains the accepted Air binding with no endpoint if a session blocks the final verified save', async () => {
    const original = { ...profile, last_serial: '127.0.0.1:5555' }
    const config = {
      device_profile: original,
      flush_config_saves: vi.fn(async () => {}),
      save_config: async (confirmation) => {
        if (confirmation) throw new Error('设备会话运行中')
      }
    }
    const result = {
      ok: true,
      serial: '127.0.0.1:5555',
      game_package: 'com.hypergryph.arknights',
      profile_patch: {
        preset_id: 'macos.bluestacks_air',
        installation_path: '/Applications/BlueStacks.app'
      }
    }
    await expect(savePreflightDevice({ config, profile: original, result })).rejects.toThrow(
      '设备会话运行中'
    )
    expect(config.device_profile).toMatchObject({
      preset_id: 'macos.bluestacks_air',
      installation_path: '/Applications/BlueStacks.app',
      last_serial: '',
      game_package_confirmed: false
    })
  })
  it('revalidates only the bound BlueStacks keyword and requires its product config source', () => {
    const metadata = { host_platform: 'windows' }
    const bound = {
      ...profile,
      preset_id: 'windows.bluestacks5',
      manager_path: 'C:/BlueStacks_nxt/HD-Player.exe',
      config_path: 'C:/ProgramData/BlueStacks_nxt/bluestacks.conf',
      instance_id: 'Pie64_2',
      last_serial: ''
    }
    for (const result of [
      null,
      {
        ok: false,
        error: { code: 'endpoint_unverified', fields: [], message: '请启动已绑定实例' }
      },
      { ok: false, error: { code: 'instance_missing', fields: [], message: '已绑定实例不存在' } }
    ]) {
      const state = deviceSettingsState({ profile: bound, metadata, result })
      expect(state.actions.detect.endpoint).toBe('preflight')
      expect(state.fields).toEqual([])
    }
    for (const incomplete of [
      { config_path: '' },
      { config_path: '   ' },
      { manager_path: '' },
      { instance_id: '2' },
      { instance_id: 'Pie64-2' },
      { instance_id: 'Pie64_2 --other' }
    ]) {
      expect(
        deviceSettingsState({ profile: { ...bound, ...incomplete }, metadata }).actions.detect
          .endpoint
      ).toBe('discover')
    }
    expect(
      deviceSettingsState({
        profile: { ...bound, manager_path: '', installation_path: 'C:/BlueStacks_nxt' },
        metadata
      }).actions.detect.endpoint
    ).toBe('preflight')
  })
  it('revalidates a confirmed Nox VM by identity and discovers legacy numeric selections', () => {
    const metadata = { host_platform: 'windows' }
    const nox = {
      ...profile,
      preset_id: 'windows.nox',
      installation_path: 'C:/Nox/bin',
      instance_id: 'Nox_2',
      instance_name: '夜神主账号',
      instance_uuid: '582fe022-b9b5-452c-aa51-cd14731fb451',
      topology_fingerprint: 'confirmed-nox-topology'
    }
    expect(deviceSettingsState({ profile: nox, metadata }).actions.detect.endpoint).toBe(
      'preflight'
    )
    expect(
      deviceSettingsState({ profile: { ...nox, instance_id: 'Imported_VM' }, metadata }).actions
        .detect.endpoint
    ).toBe('preflight')
    for (const legacy of [
      { instance_id: '2' },
      { instance_uuid: '' },
      { topology_fingerprint: '' }
    ]) {
      expect(
        deviceSettingsState({ profile: { ...nox, ...legacy }, metadata }).actions.detect.endpoint
      ).toBe('discover')
    }
  })
  it('exposes the BlueStacks config path only for repair or advanced settings and locks it during a run', () => {
    const bound = {
      ...profile,
      preset_id: 'windows.bluestacks5',
      config_path: 'C:/ProgramData/BlueStacks_nxt/bluestacks.conf'
    }
    expect(deviceSettingsState({ profile: bound }).fields).toEqual([])
    const result = {
      error: {
        code: 'missing_config',
        fields: ['config_path'],
        message: '请选择此安装的 bluestacks.conf 产品配置文件'
      }
    }
    const repair = deviceSettingsState({ profile: bound, result })
    expect(repair.fields).toEqual([
      {
        key: 'config_path',
        label: '产品配置路径',
        value: bound.config_path,
        kind: 'input',
        options: undefined,
        tag: false,
        disabled: false,
        placeholder: '例如：C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf',
        help: '模拟器的全局配置文件路径（如 BlueStacks 的 bluestacks.conf），用于自动解析多开实例与端口分配。',
        span: 2
      }
    ])
    expect(repair.message).toContain('bluestacks.conf')
    const advanced = deviceSettingsState({
      profile: bound,
      advanced: true,
      metadata: { active: true }
    })
    expect(advanced.fields.find((field) => field.key === 'config_path')).toMatchObject({
      label: '产品配置路径',
      disabled: true
    })
  })
  it('requires a new instance lookup after Nox topology changes instead of retrying the old binding', () => {
    const state = deviceSettingsState({
      profile: {
        ...profile,
        preset_id: 'windows.nox',
        manager_path: 'C:/Nox/bin/NoxConsole.exe',
        instance_id: 'Nox_2',
        instance_uuid: 'previous-vm-uuid',
        topology_fingerprint: 'previous-topology'
      },
      metadata: { host_platform: 'windows' },
      result: {
        ok: false,
        error: {
          code: 'topology_changed',
          message: '夜神实例已导入、删除或重建，请重新查找并选择实例。',
          fields: []
        }
      }
    })
    expect(state.actions.detect).toMatchObject({
      label: '检测实例',
      endpoint: 'discover',
      disabled: false
    })
    expect(state.actions.discover.visible).toBe(true)
    expect(state.message).toContain('重新查找并选择实例')
  })
  it('clears Nox confirmation guards when the draft target changes or becomes manual', () => {
    const nox = {
      ...profile,
      preset_id: 'windows.nox',
      instance_id: 'Nox_2',
      instance_name: '夜神主账号',
      instance_uuid: 'previous-vm-uuid',
      topology_fingerprint: 'previous-topology',
      game_package_confirmed: true
    }
    const drafts = [
      editDeviceDraft(nox, 'preset_id', 'windows.mumu12'),
      editDeviceDraft(nox, 'installation_path', 'D:/Nox/bin'),
      editDeviceDraft(nox, 'manager_path', 'D:/Nox/bin/NoxConsole.exe'),
      editDeviceDraft(nox, 'instance_id', 'Nox_3'),
      manualDeviceDraft(nox, 'manual.other'),
      manualDeviceDraft(nox, 'manual.physical')
    ]
    for (const draft of drafts) {
      expect(draft).toMatchObject({
        instance_name: '',
        instance_uuid: '',
        topology_fingerprint: '',
        last_serial: '',
        game_package_confirmed: false
      })
    }
    expect(editDeviceDraft(nox, 'adb_path', 'C:/adb.exe').instance_uuid).toBe('previous-vm-uuid')
    expect(editDeviceDraft(nox, 'instance_id', 'Nox_2').topology_fingerprint).toBe(
      'previous-topology'
    )
  })
  it('invalidates stale BlueStacks endpoints when editing product config and clears it for new installation sources', () => {
    const bound = {
      ...profile,
      preset_id: 'windows.bluestacks5',
      installation_path: 'C:/BlueStacks_nxt',
      manager_path: 'C:/BlueStacks_nxt/HD-Player.exe',
      config_path: 'C:/ProgramData/BlueStacks_nxt/bluestacks.conf',
      instance_id: 'Pie64_2',
      instance_name: '主账号',
      game_package_confirmed: true
    }
    const newPath = 'D:/BlueStacksData/bluestacks.conf'
    expect(editDeviceDraft(bound, 'config_path', newPath)).toMatchObject({
      config_path: newPath,
      last_serial: '',
      instance_name: '',
      game_package_confirmed: false
    })
    for (const draft of [
      editDeviceDraft(bound, 'preset_id', 'windows.nox'),
      editDeviceDraft(bound, 'installation_path', 'D:/BlueStacks_nxt'),
      editDeviceDraft(bound, 'manager_path', 'D:/BlueStacks_nxt/HD-Player.exe'),
      manualDeviceDraft(bound, 'manual.other'),
      manualDeviceDraft(bound, 'manual.physical')
    ]) {
      expect(draft).toMatchObject({
        config_path: '',
        last_serial: '',
        game_package_confirmed: false
      })
    }
    expect(editDeviceDraft(bound, 'instance_id', 'Pie64_3').config_path).toBe(bound.config_path)
    expect(editDeviceDraft(bound, 'config_path', bound.config_path)).toEqual(bound)
  })
  it('saves the chosen Nox UUID and topology but clears them when another product is selected', async () => {
    const nox = {
      key: 'nox-confirmed-vm',
      binding: {
        preset_id: 'windows.nox',
        installation_path: 'C:/Nox/bin',
        instance_id: 'Nox_2',
        instance_name: '夜神主账号',
        instance_uuid: 'selected-vm-uuid',
        topology_fingerprint: 'selected-topology'
      }
    }
    const config = {
      device_profile: profile,
      flush_config_saves: vi.fn(async () => {}),
      save_config: vi.fn(async () => {})
    }
    const result = { kind: 'discovery', candidates: [nox, discoveredInstance] }
    const selected = await saveDiscoveredDevice({ config, profile, result, key: nox.key })
    expect(selected).toMatchObject({
      ...nox.binding,
      last_serial: '',
      game_package_confirmed: false
    })
    const switched = await saveDiscoveredDevice({
      config,
      profile: selected,
      result,
      key: discoveredInstance.key
    })
    expect(switched.instance_uuid).toBe('')
    expect(switched.topology_fingerprint).toBe('')
    expect(switched.instance_id).toBe('0')
  })
  it('saves an explicit BlueStacks instance keyword with its config and clears the source when switching products', async () => {
    const blueStacks = {
      key: 'bluestacks-pie64-2',
      preset_id: 'windows.bluestacks5',
      instance_name: '蓝叠主账号',
      state: 'stopped',
      binding: {
        preset_id: 'windows.bluestacks5',
        installation_path: 'C:/BlueStacks_nxt',
        manager_path: 'C:/BlueStacks_nxt/HD-Player.exe',
        config_path: 'C:/ProgramData/BlueStacks_nxt/bluestacks.conf',
        instance_id: 'Pie64_2',
        instance_name: '蓝叠主账号',
        last_serial: ''
      }
    }
    const otherBlueStacks = {
      ...blueStacks,
      key: 'bluestacks-nougat64',
      instance_name: '蓝叠小号',
      binding: { ...blueStacks.binding, instance_id: 'Nougat64', instance_name: '蓝叠小号' }
    }
    const config = {
      device_profile: profile,
      flush_config_saves: vi.fn(async () => {}),
      save_config: vi.fn(async () => {})
    }
    const result = {
      kind: 'discovery',
      candidates: [blueStacks, otherBlueStacks, discoveredInstance],
      selected_key: null
    }
    expect(deviceSettingsState({ profile, result }).instances.value).toBe(null)
    await expect(saveDiscoveredDevice({ config, profile, result, key: null })).rejects.toThrow(
      '请选择有效实例'
    )
    const selected = await saveDiscoveredDevice({ config, profile, result, key: blueStacks.key })
    expect(selected).toMatchObject({ ...blueStacks.binding, game_package_confirmed: false })
    const switched = await saveDiscoveredDevice({
      config,
      profile: selected,
      result,
      key: discoveredInstance.key
    })
    expect(switched.config_path).toBe('')
    expect(switched.instance_id).toBe('0')
  })
  it('revalidates the saved LDPlayer instance after restart or endpoint failure without rediscovery', () => {
    const bound = {
      ...profile,
      preset_id: 'windows.ldplayer9',
      instance_id: '3',
      instance_name: '雷电主账号',
      manager_path: 'D:/LDPlayer/LDPlayer9/ldconsole.exe',
      last_serial: ''
    }
    for (const result of [
      null,
      {
        ok: false,
        error: {
          code: 'endpoint_unverified',
          fields: ['adb_path'],
          message: '无法验证已选雷电实例的连接，请检查 ADB 路径'
        }
      },
      { ok: false, error: { code: 'instance_missing', fields: [], message: '已选实例已删除' } }
    ]) {
      const state = deviceSettingsState({
        profile: bound,
        metadata: { host_platform: 'win32' },
        result
      })
      expect(state.actions.detect.endpoint).toBe('preflight')
      expect(state.fields.map((field) => field.key)).toEqual(result?.error.fields || [])
      expect(state.summary).toBe('雷电模拟器 9 · 雷电主账号')
      if (result) expect(state.actions.detect.label).toBe('启动并检测')
    }
  })

  it.each(['windows.mumu12', 'windows.ldplayer9'])(
    'discovers %s until a nonnegative instance index and installation reference are known',
    (preset_id) => {
      const metadata = { host_platform: 'win32' }
      const emulator = { ...profile, preset_id, last_serial: '' }
      for (const binding of [
        { instance_id: '-1', installation_path: 'C:/MuMuPlayer-12.0' },
        { instance_id: 'unknown', installation_path: 'C:/MuMuPlayer-12.0' },
        { instance_id: '0', installation_path: '', manager_path: '' },
        { instance_id: '0', installation_path: '  ', manager_path: '' }
      ]) {
        expect(
          deviceSettingsState({ profile: { ...emulator, ...binding }, metadata }).actions.detect
            .endpoint
        ).toBe('discover')
      }
      for (const binding of [
        { instance_id: '0', installation_path: 'C:/MuMuPlayer-12.0' },
        { instance_id: '1', manager_path: 'C:/MuMuPlayer-12.0/shell/MuMuManager.exe' }
      ]) {
        expect(
          deviceSettingsState({ profile: { ...emulator, ...binding }, metadata }).actions.detect
            .endpoint
        ).toBe('preflight')
      }
    }
  )

  it('shows mixed products and saves the selected LDPlayer key even when both products use index zero', async () => {
    const ldplayer = {
      ...discoveredInstance,
      key: 'ldplayer-d-0',
      preset_id: 'windows.ldplayer9',
      installation_path: 'D:/LDPlayer/LDPlayer9',
      state: 'running',
      serial: '127.0.0.1:5555',
      binding: {
        ...discoveredInstance.binding,
        preset_id: 'windows.ldplayer9',
        installation_path: 'D:/LDPlayer/LDPlayer9',
        manager_path: 'D:/LDPlayer/LDPlayer9/ldconsole.exe'
      }
    }
    const metadata = { host_platform: 'win32' }
    const fresh = { ...profile, last_serial: '' }
    const previous = {
      ...profile,
      ...discoveredInstance.binding,
      last_serial: '127.0.0.1:16384',
      screenshot_backend: 'mumu_ipc',
      touch_backend: 'mumu_ipc'
    }
    expect(deviceSettingsState({ profile: fresh, metadata }).actions.detect.endpoint).toBe(
      'discover'
    )
    for (const candidates of [
      [discoveredInstance, ldplayer],
      [ldplayer, discoveredInstance]
    ]) {
      const result = { kind: 'discovery', candidates, selected_key: null }
      const state = deviceSettingsState({ profile, metadata, result })
      expect(state.instances.value).toBe(null)
      expect(state.instances.options).toContainEqual({
        value: 'ldplayer-d-0',
        label: '雷电模拟器 9 · 主账号 · 运行中 · D:/LDPlayer/LDPlayer9'
      })
      expect(state.instances.options).toContainEqual({
        value: 'mumu-c-0',
        label: 'MuMu 12 · 主账号 · 已停止 · C:/MuMuPlayer-12.0'
      })
      const config = {
        device_profile: previous,
        flush_config_saves: vi.fn(async () => {}),
        save_config: vi.fn(async () => {})
      }
      const saved = await saveDiscoveredDevice({
        config,
        profile: previous,
        result,
        key: 'ldplayer-d-0'
      })
      expect(saved).toEqual({
        ...previous,
        ...ldplayer.binding,
        screenshot_backend: 'droidcast',
        touch_backend: 'scrcpy'
      })
      expect(saved.last_serial).toBe('')
      expect(deviceSettingsState({ profile: saved, metadata }).actions.detect.endpoint).toBe(
        'preflight'
      )
      expect(saved).not.toHaveProperty('state')
      expect(saved).not.toHaveProperty('key')
      const repair = deviceSettingsState({
        profile: saved,
        metadata,
        result: {
          ok: false,
          error: {
            code: 'backend_unavailable',
            fields: ['screenshot_backend'],
            message: '当前实例不支持 MuMu IPC，请选择截图后端'
          }
        }
      })
      expect(repair.fields).toEqual([])
      expect(connectionField(repair, 'screenshot_backend').value).toBe('droidcast')
      expect(repair.actions.detect.endpoint).toBe('preflight')
    }
  })
  it('discovers on a fresh Windows setup and revalidates only a chosen or manual target', () => {
    const metadata = { host_platform: 'win32' }
    const fresh = { ...profile, last_serial: '' }
    expect(deviceSettingsState({ profile: fresh, metadata }).actions.detect.endpoint).toBe(
      'discover'
    )
    expect(
      deviceSettingsState({ profile: fresh, metadata, manual: true }).actions.detect.endpoint
    ).toBe('preflight')
    expect(deviceSettingsState({ profile, metadata }).actions.detect.endpoint).toBe('preflight')
    expect(
      deviceSettingsState({ profile: { ...fresh, ...discoveredInstance.binding }, metadata })
        .actions.detect.endpoint
    ).toBe('preflight')
    expect(
      deviceSettingsState({ profile: fresh, metadata: { host_platform: 'linux' } }).actions.detect
        .endpoint
    ).toBe('discover')
    expect(deviceSettingsState({ profile, metadata }).actions.discover.visible).toBe(true)
    expect(
      deviceSettingsState({ profile, metadata: { ...metadata, active: true } }).actions.discover
        .disabled
    ).toBe(true)
  })
  it('saves the chosen installation binding through config while clearing the previous session endpoint', async () => {
    const otherInstallation = {
      ...discoveredInstance,
      key: 'mumu-d-0',
      binding: {
        ...discoveredInstance.binding,
        installation_path: 'D:/MuMuPlayer-12.0',
        manager_path: 'D:/MuMuPlayer-12.0/shell/MuMuManager.exe'
      }
    }
    const config = {
      device_profile: { ...profile, game_package_confirmed: true },
      flush_config_saves: vi.fn(async () => {}),
      save_config: vi.fn(async () => {})
    }
    const result = {
      kind: 'discovery',
      candidates: [discoveredInstance, otherInstallation],
      selected_key: null
    }
    await saveDiscoveredDevice({ config, profile, result, key: 'mumu-d-0' })
    expect(config.device_profile).toEqual({
      ...profile,
      ...otherInstallation.binding
    })
    expect(config.device_profile.last_serial).toBe('')
    expect(config.save_config).toHaveBeenCalledExactlyOnceWith()
    expect(config.device_profile).not.toHaveProperty('candidates')
    await expect(saveDiscoveredDevice({ config, profile, result, key: '0' })).rejects.toThrow(
      '请选择有效实例'
    )
  })
  it('restores the saved profile when an instance binding is rejected during save', async () => {
    const config = {
      device_profile: profile,
      flush_config_saves: vi.fn(async () => {}),
      save_config: vi.fn(async () => {
        throw new Error('会话运行中，不能变更设备')
      })
    }
    await expect(
      saveDiscoveredDevice({
        config,
        profile,
        result: { kind: 'discovery', candidates: [discoveredInstance] },
        key: 'mumu-c-0'
      })
    ).rejects.toThrow('会话运行中')
    expect(config.device_profile).toEqual(profile)
  })
  it('requires a stable instance choice and keeps stopped instances recognizable without a serial', () => {
    const second = {
      ...discoveredInstance,
      key: 'mumu-d-0',
      installation_path: 'D:/MuMuPlayer-12.0',
      state: 'running',
      serial: '127.0.0.1:16640'
    }
    const result = {
      kind: 'discovery',
      candidates: [discoveredInstance, second],
      selected_key: null,
      error: { code: 'multiple_instances', fields: ['instance_id'], message: '请选择实例' }
    }
    const state = deviceSettingsState({ profile, result, metadata: { host_platform: 'win32' } })
    expect(state.instances.value).toBe(null)
    expect(state.instances.options).toEqual([
      {
        value: 'mumu-c-0',
        label: 'MuMu 12 · 主账号 · 已停止 · C:/MuMuPlayer-12.0'
      },
      {
        value: 'mumu-d-0',
        label: 'MuMu 12 · 主账号 · 运行中 · D:/MuMuPlayer-12.0'
      }
    ])
    expect(state.fields).toEqual([])
    expect(
      deviceSettingsState({ profile, result, metadata: { active: true } }).instances.disabled
    ).toBe(true)
  })

  it('retains partial discoveries and combines source repair fields without claiming readiness', () => {
    const state = deviceSettingsState({
      profile,
      result: {
        kind: 'discovery',
        ok: true,
        candidates: [discoveredInstance],
        selected_key: null,
        error: { code: 'partial_discovery', fields: [], message: '发现结果不完整，请选择实例' },
        errors: [
          { code: 'permission_denied', fields: ['installation_path'], message: '无法读取安装信息' },
          { code: 'manager_timeout', fields: ['manager_path'], message: '管理器超时，请检查路径' }
        ]
      }
    })
    expect(state.instances.options).toHaveLength(1)
    expect(state.instances.value).toBe(null)
    expect(state.fields.map((field) => field.key)).toEqual(['installation_path', 'manager_path'])
    expect(state.message).toContain('无法读取安装信息')
    expect(state.message).toContain('管理器超时，请检查路径')
    expect(state.statusDisplayLabel).toBe('请选择实例')
  })
  it('offers explicit temporary preparation only for a physical serial and locks it during a run', () => {
    expect(deviceSettingsState({ profile }).actions.prepare.visible).toBe(false)
    const physical = { ...profile, preset_id: 'manual.physical', last_serial: 'USB-phone' }
    expect(deviceSettingsState({ profile: physical }).actions.prepare).toMatchObject({
      visible: true,
      disabled: false,
      serial: 'USB-phone'
    })
    for (const context of [{ busy: true }, { metadata: { active: true } }]) {
      expect(deviceSettingsState({ profile: physical, ...context }).actions.prepare.disabled).toBe(
        true
      )
    }
    expect(
      deviceSettingsState({ profile: { ...physical, last_serial: '' } }).actions.prepare.disabled
    ).toBe(true)
    expect(
      deviceSettingsState({
        profile: physical,
        metadata: { preparation: { stage: 'conflict', last_error: '显示覆盖已由其他程序修改' } }
      }).preparationMessage
    ).toBe('显示覆盖已由其他程序修改')
  })

  it('saves a chosen physical draft then authorizes that serial for only the immediate start', async () => {
    const events = []
    const physical = { ...profile, preset_id: 'manual.physical', last_serial: 'USB-phone' }
    const config = {
      device_profile: profile,
      flush_config_saves: vi.fn(async () => events.push('flush')),
      save_config: vi.fn(async () => events.push('save'))
    }
    const axios = { post: vi.fn(async () => ({ data: true })) }
    await startPhysicalPreparation({ axios, config, profile: physical, serial: 'USB-phone' })
    expect(events).toEqual(['flush', 'save', 'save', 'flush'])
    expect(config.device_profile).toEqual(physical)
    expect(config.device_profile).not.toHaveProperty('preparation_serial')
    expect(axios.post).toHaveBeenCalledExactlyOnceWith('/start/0', {
      preparation_serial: 'USB-phone'
    })
  })

  it('does not start when the saved target no longer matches the consent or saving fails', async () => {
    const physical = { ...profile, preset_id: 'manual.physical', last_serial: 'USB-phone' }
    const axios = { post: vi.fn() }
    const config = {
      device_profile: profile,
      flush_config_saves: vi.fn(async () => {}),
      save_config: vi.fn(async () => {
        config.device_profile = { ...physical, last_serial: 'USB-different' }
      })
    }
    await expect(
      startPhysicalPreparation({ axios, config, profile: physical, serial: 'USB-phone' })
    ).rejects.toThrow('设备目标已变化')
    expect(axios.post).not.toHaveBeenCalled()
    config.device_profile = profile
    config.save_config.mockRejectedValueOnce(new Error('配置保存失败'))
    await expect(
      startPhysicalPreparation({ axios, config, profile: physical, serial: 'USB-phone' })
    ).rejects.toThrow('配置保存失败')
    expect(config.device_profile).toEqual(profile)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('replaces a stale ready result with a new worker failure without overwriting a local repair', () => {
    const ready = { ok: true, status: 'ready' }
    const failed = { ok: false, error: { code: 'device_offline', fields: [] } }
    expect(deviceStatusResult(ready, ready, failed)).toBe(failed)
    expect(deviceStatusResult(ready, ready, failed, true)).toBe(ready)
    expect(deviceStatusResult(failed, ready, { ...ready })).toBe(failed)
  })
  it('shows a successful binding without exposing configuration or choosing a browser platform', () => {
    const state = deviceSettingsState({
      profile,
      metadata: { host_platform: 'linux', active: false },
      result: { ok: true, status: 'ready', serial: 'emulator-5554' }
    })
    expect(state.hostLabel).toBe('Linux')
    expect(state.summary).toContain('其他模拟器')
    expect(state.summary).toContain('emulator-5554')
    expect(state.statusDisplayLabel).toBe('连接正常')
    expect(state.fields).toEqual([])
    expect(state.actions.detect.disabled).toBe(false)
  })

  it.each([
    ['missing_installation', ['installation_path']],
    ['missing_adb', ['adb_path']],
    ['multiple_devices', ['last_serial']],
    ['device_unauthorized', []],
    ['device_offline', []],
    ['invalid_size', []],
    // The screenshot backend keeps its own always-visible group; a repair that
    // names it therefore adds no field to the identity form.
    ['frame_failed', []],
    ['package_ambiguous', ['game_package']],
    ['package_missing', []]
  ])('shows only the repair fields and explanation for %s', (code, fields) => {
    const state = deviceSettingsState({
      profile,
      result: { ok: false, error: { code, fields, message: '请修复当前问题', action: 'retry' } }
    })
    expect(state.fields.map((field) => field.key)).toEqual(fields)
    expect(state.message).toBe('请修复当前问题')
    expect(state.actions.detect.label).toBe('重试连接')
    expect(state.fields.map((field) => field.key)).not.toContain('timeout')
  })

  it('keeps multiple targets unselected and includes offline and unauthorized evidence', () => {
    const state = deviceSettingsState({
      profile: { ...profile, last_serial: '' },
      result: {
        candidates: [
          { serial: 'first', state: 'device' },
          { serial: 'phone', state: 'unauthorized' },
          { serial: 'offline', state: 'offline' }
        ],
        error: { code: 'multiple_devices', fields: ['last_serial'] }
      }
    })
    expect(state.fields[0].value).toBe('')
    expect(state.fields[0].options).toEqual([
      { value: 'first', label: 'first · device' },
      { value: 'phone', label: 'phone · unauthorized' },
      { value: 'offline', label: 'offline · offline' }
    ])
  })

  it('does not treat the legacy default package as a confirmed dual-package choice', () => {
    const state = deviceSettingsState({
      profile,
      result: {
        packages: ['com.hypergryph.arknights', 'com.hypergryph.arknights.bilibili'],
        error: { code: 'package_ambiguous', fields: ['game_package'] }
      }
    })
    expect(state.fields[0].value).toBe(null)
    expect(state.fields[0].options.map((option) => option.label)).toEqual(['官服', 'Bilibili 服'])
  })

  it('locks only device controls in an active session and filters presets by the backend platform', () => {
    const state = deviceSettingsState({
      profile,
      metadata: { active: true, host_platform: 'darwin' },
      advanced: true
    })
    expect(state.fields.length).toBeGreaterThan(0)
    expect(state.fields.every((field) => field.disabled)).toBe(true)
    expect(state.actions.detect.disabled).toBe(true)
    expect(state.actions.manualFallback.disabled).toBe(true)
    expect(state.unrelatedLocked).toBe(false)
    const presets = state.fields.find((field) => field.key === 'preset_id').options
    expect(presets.some((option) => option.value === 'macos.bluestacks_air')).toBe(true)
    expect(presets.some((option) => option.value.startsWith('windows.'))).toBe(false)
  })

  it('provides independent manual paths which clear the previous binding and package confirmation', () => {
    const previous = {
      ...profile,
      preset_id: 'windows.mumu12',
      instance_id: '2',
      installation_path: 'C:/MuMu',
      game_package_confirmed: true
    }
    for (const preset of ['manual.other', 'manual.physical']) {
      const draft = manualDeviceDraft(previous, preset)
      expect(draft.preset_id).toBe(preset)
      expect(draft.last_serial).toBe('')
      expect(draft.installation_path).toBe('')
      expect(draft.instance_id).toBe('')
      expect(draft.game_package_confirmed).toBe(false)
    }
    expect(previous.last_serial).toBe('emulator-5554')
  })

  it('starts a new manual binding with usable bootstrap backends instead of old instance IPC', () => {
    const previous = { ...profile, screenshot_backend: 'mumu_ipc', touch_backend: 'mumu_ipc' }
    for (const preset of ['manual.other', 'manual.physical']) {
      const draft = manualDeviceDraft(previous, preset)
      expect(draft.screenshot_backend).toBe('droidcast')
      expect(draft.touch_backend).toBe('scrcpy')
    }
    expect(previous.screenshot_backend).toBe('mumu_ipc')
  })

  it('clears stale serials on binding edits and submits only changes plus an explicit package choice', () => {
    const draft = editDeviceDraft(profile, 'instance_id', 'new-instance')
    expect(draft.last_serial).toBe('')
    const selected = editDeviceDraft(draft, 'last_serial', 'chosen-phone')
    expect(devicePreflightRequest(profile, selected)).toEqual({
      device: {
        instance_id: 'new-instance',
        last_serial: 'chosen-phone',
        game_package_confirmed: false
      }
    })
    expect(devicePreflightRequest(profile, profile, 'com.hypergryph.arknights.bilibili')).toEqual({
      device: { last_serial: 'emulator-5554' },
      confirmed_package: 'com.hypergryph.arknights.bilibili'
    })
  })

  it('persists one detected package automatically without saving diagnostics or unrelated settings', () => {
    expect(
      deviceSuccessPatch(profile, profile, {
        ok: true,
        serial: 'emulator-5554',
        game_package: 'com.hypergryph.arknights.bilibili',
        adb_path: '/automatic/adb',
        host_platform: 'linux',
        observations: { frame: [1920, 1080] }
      })
    ).toEqual({
      device: {
        game_package: 'com.hypergryph.arknights.bilibili',
        game_package_confirmed: true,
        adb_path: '/automatic/adb'
      }
    })
    expect(deviceSuccessPatch(profile, profile, { ok: false })).toEqual({})
  })

  it('keeps MuMu screenshot and touch selection consistent only after an explicit backend edit', () => {
    const draft = editDeviceDraft(profile, 'screenshot_backend', 'mumu_ipc')
    expect(draft.touch_backend).toBe('mumu_ipc')
    expect(editDeviceDraft(draft, 'touch_backend', 'maatouch')).toMatchObject({
      screenshot_backend: 'droidcast',
      touch_backend: 'maatouch'
    })
  })

  it('updates recovery policy settings in device draft', () => {
    let draft = editDeviceDraft(profile, 'recovery_timeout', 120)
    draft = editDeviceDraft(draft, 'recovery_attempts', 5)
    draft = editDeviceDraft(draft, 'recovery_local_wait', 15)
    expect(draft.recovery_timeout).toBe(120)
    expect(draft.recovery_attempts).toBe(5)
    expect(draft.recovery_local_wait).toBe(15)
  })

  it('saves non-identity settings right away and keeps device identity behind the test', () => {
    for (const key of [
      'recovery_timeout',
      'recovery_shutdown_wait',
      'manager_query_timeout',
      'simulator_hotkey',
      'simulator_hotkey_delay',
      'screenshot_backend',
      'touch_backend'
    ]) {
      expect(isImmediateDeviceField(key)).toBe(true)
    }
    for (const key of [
      'preset_id',
      'installation_path',
      'manager_path',
      'config_path',
      'instance_id',
      'instance_name',
      'last_serial',
      'game_package'
    ]) {
      expect(isImmediateDeviceField(key)).toBe(false)
    }
  })

  it('sends only the edited non-identity keys, never a pending identity edit', () => {
    const draft = {
      ...profile,
      preset_id: 'windows.mumu12',
      installation_path: 'C:/MuMuPlayer-12.0',
      manager_path: 'C:/MuMuPlayer-12.0/shell/MuMuManager.exe',
      instance_id: '0'
    }
    expect(editedDevicePatch(draft, 'simulator_hotkey', '')).toEqual({ simulator_hotkey: '' })
    // Switching away from MuMu IPC carries the coupled touch backend along.
    expect(
      editedDevicePatch(
        { ...draft, screenshot_backend: 'mumu_ipc', touch_backend: 'mumu_ipc' },
        'screenshot_backend',
        'droidcast'
      )
    ).toEqual({ screenshot_backend: 'droidcast', touch_backend: 'scrcpy' })
  })

  it('offers starting the bound instance only where a manager can launch it', () => {
    const metadata = { host_platform: 'win32' }
    const bound = {
      ...profile,
      preset_id: 'windows.mumu12',
      installation_path: 'C:/MuMuPlayer-12.0',
      manager_path: 'C:/MuMuPlayer-12.0/shell/MuMuManager.exe',
      instance_id: '0',
      instance_name: '粥',
      last_serial: '127.0.0.1:16384'
    }
    const state = deviceSettingsState({ profile: bound, metadata })
    expect(state.actions.startBound).toEqual({
      visible: true,
      disabled: false,
      label: '启动并测试连接'
    })
    expect(state.actions.detect.endpoint).toBe('preflight')
    expect(state.actions.detect.options.map((option) => option.key)).toEqual([
      'detect',
      'preflight',
      'start'
    ])
    expect(state.actions.detect.options[0].label).toBe('启动并检测')
    // The read-only rule and the save rule sit next to the status tag, not in a
    // notice above the buttons.
    expect(state.bindingHelp).toBe('')
    expect(state.connectionHelp).toContain('启动并测试连接')
    expect(state.connectionHelp).toContain('连接失败不撤销选择')

    const ld14State = deviceSettingsState({
      profile: {
        ...bound,
        preset_id: 'windows.ldplayer14',
        installation_path: 'C:/leidian/LDPlayer14',
        manager_path: 'C:/leidian/LDPlayer14/dnconsole.exe'
      },
      metadata
    })
    expect(ld14State.presetTitle).toBe('雷电模拟器 14')
    expect(ld14State.actions.startBound.visible).toBe(true)

    const unbound = deviceSettingsState({
      profile: { ...bound, instance_id: '', installation_path: '', manager_path: '' },
      metadata
    })
    expect(unbound.actions.startBound.visible).toBe(false)
    expect(unbound.actions.detect.options.map((option) => option.key)).toEqual(['detect'])

    // BlueStacks 5 has discovery but no manager mower can launch.
    const blueStacks = deviceSettingsState({
      profile: {
        ...bound,
        preset_id: 'windows.bluestacks5',
        instance_id: 'Pie64',
        config_path: 'C:/ProgramData/BlueStacks_nxt/bluestacks.conf'
      },
      metadata
    })
    expect(blueStacks.actions.startBound.visible).toBe(false)
    expect(blueStacks.actions.detect.options.map((option) => option.key)).toEqual(['detect'])
    expect(blueStacks.connectionHelp).not.toContain('启动并测试连接')
    expect(blueStacks.connectionHelp).toContain('请先确保目标设备已经启动')

    const locked = deviceSettingsState({ profile: bound, metadata: { ...metadata, active: true } })
    expect(locked.actions.startBound.disabled).toBe(true)
    expect(locked.actions.detect.options[2].disabled).toBe(true)

    // The backend's own set is authoritative when it reports one.
    const backendSaysNo = deviceSettingsState({
      profile: bound,
      metadata: { ...metadata, managed_instance_presets: ['windows.ldplayer9'] }
    })
    expect(backendSaysNo.actions.startBound.visible).toBe(false)
    expect(backendSaysNo.actions.detect.options.map((option) => option.key)).toEqual(['detect'])
  })
})

describe('connection settings placement', () => {
  const bindings = {
    mumu: {
      ...profile,
      preset_id: 'windows.mumu12',
      installation_path: 'C:/MuMuPlayer-12.0',
      manager_path: 'C:/MuMuPlayer-12.0/nx_main/MuMuManager.exe',
      instance_id: '0',
      instance_name: '粥',
      last_serial: '127.0.0.1:16384'
    }
  }

  it('keeps the connection group visible without opening the advanced identity form', () => {
    const state = deviceSettingsState({ profile: bindings.mumu, metadata: {} })
    expect(state.fields).toEqual([])
    expect(state.connectionVisible).toBe(true)
    expect(state.connectionFields.map((field) => field.key)).toEqual([
      'screenshot_backend',
      'touch_backend'
    ])
    expect(connectionField(state, 'screenshot_backend')).toMatchObject({ kind: 'select' })
  })

  it('keeps the connection group out of a page that has no device yet', () => {
    const fresh = { ...profile, preset_id: '', last_serial: '' }
    const state = deviceSettingsState({ profile: fresh, metadata: {} })
    expect(state.connectionVisible).toBe(false)
    expect(state.connectionFields).toEqual([])
    // Opening the identity form or hitting a repair does expose them.
    expect(deviceSettingsState({ profile: fresh, advanced: true }).connectionVisible).toBe(true)
    expect(
      deviceSettingsState({
        profile: fresh,
        result: { ok: false, error: { code: 'frame_failed', fields: ['screenshot_backend'] } }
      }).connectionVisible
    ).toBe(true)
  })

  it('explains the read-only test and the save rule next to the status tag', () => {
    const mumu = deviceSettingsState({
      profile: bindings.mumu,
      metadata: { host_platform: 'win32' }
    })
    // The managed preset carries no notice of its own: its rule lives in the tag.
    expect(mumu.bindingHelp).toBe('')
    expect(mumu.connectionHelp).toContain('不会启动或重启模拟器')
    expect(mumu.connectionHelp).toContain('启动并测试连接')
    expect(mumu.connectionHelp).toContain('ADB 地址和游戏包在验证通过后保存')

    const manual = deviceSettingsState({ profile })
    expect(manual.bindingHelp).toBe('')
    expect(manual.connectionHelp).toContain('请先确保目标设备已经启动')
    expect(manual.connectionHelp).not.toContain('启动并测试连接')
  })

  it('keeps preset-specific guidance in the notice', () => {
    const genymotion = deviceSettingsState({
      profile: {
        ...profile,
        preset_id: 'linux.genymotion',
        instance_id: '12345678-1234-1234-1234-123456789abc',
        manager_path: '/opt/genymobile/genymotion/gmtool',
        last_serial: ''
      },
      metadata: { host_platform: 'linux' }
    })
    expect(genymotion.bindingHelp).toContain('只复核所选 VM')
    expect(genymotion.connectionHelp).toContain('先保存编号和身份核验信息')
  })
})

it('honors an empty backend startup capability list and rejects unverified MuMu serial startup', () => {
  const selected = {
    preset_id: 'macos.mumu_pro',
    instance_id: '1',
    topology_fingerprint: 'a'.repeat(64)
  }
  expect(
    deviceSettingsState({
      profile: selected,
      metadata: { host_platform: 'macos', managed_instance_presets: [] }
    }).actions.startBound.visible
  ).toBe(false)
  expect(() =>
    deviceStartupRequest({}, selected, { host_platform: 'macos', managed_instance_presets: [] })
  ).toThrow()
  expect(() =>
    deviceStartupRequest(
      {},
      { ...selected, topology_fingerprint: '', last_serial: '127.0.0.1:16416' },
      { host_platform: 'macos' }
    )
  ).toThrow()
  const request = deviceStartupRequest({}, selected, { host_platform: 'macos' })
  expect(request.endpoint).toBe('start')
  expect(request.payload.device.instance_id).toBe('1')
})

it('keeps a MuMu Pro instance error visible without hiding other candidates', () => {
  const result = {
    kind: 'discovery',
    candidates: [
      { key: 'failed', preset_id: 'macos.mumu_pro', instance_id: '0', state: 'error' },
      { key: 'healthy', preset_id: 'macos.mumu_pro', instance_id: '1', state: 'stopped' }
    ]
  }
  const state = deviceSettingsState({
    profile: { ...profile, preset_id: 'macos.mumu_pro' },
    result,
    metadata: { host_platform: 'macos' }
  })
  expect(state.instances.options).toHaveLength(2)
  expect(state.instances.options[0].label).toContain('操作失败')
  expect(state.instances.options[1].label).toContain('已停止')
})
