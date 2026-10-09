import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import DeviceSettings from './DeviceSettings.vue'

const state = vi.hoisted(() => ({ mounted: [], unmounted: [], client: null, config: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: () => state.client,
  onMounted: (callback) => state.mounted.push(callback),
  onUnmounted: (callback) => state.unmounted.push(callback)
}))
vi.mock('naive-ui', () => ({ useDialog: () => ({}), useMessage: () => ({}) }))
vi.mock('@/stores/config', () => ({
  useConfigStore: () => state.config
}))

let scope
let visibilityChanged
let component
beforeEach(() => {
  vi.useFakeTimers()
  state.mounted = []
  state.unmounted = []
  state.client = { get: vi.fn(async () => ({ data: {} })) }
  state.config = {
    simulator: { wait_time: 75 },
    device_profile: {
      preset_id: 'manual.other',
      screenshot_backend: 'droidcast',
      touch_backend: 'scrcpy'
    },
    save_config: vi.fn(async () => {})
  }
  vi.stubGlobal('document', {
    visibilityState: 'visible',
    addEventListener: vi.fn((event, callback) => {
      visibilityChanged = callback
    }),
    removeEventListener: vi.fn()
  })
  scope = effectScope()
  scope.run(() => {
    component = DeviceSettings.setup({}, { expose: () => {} })
  })
})

it('preserves the stored startup protection and edits it without pending identity', () => {
  expect(component.startupWait.value).toBe(75)
  component.edit('preset_id', 'windows.ldplayer9')
  component.edit('instance_id', '2')
  component.startupWait.value = 90
  expect(state.config.simulator.wait_time).toBe(90)
  expect(state.config.device_profile.preset_id).toBe('manual.other')
  expect(state.config.device_profile).not.toHaveProperty('instance_id')
  expect(component.draft.value.instance_id).toBe('2')
})

it('ignores empty or invalid startup protection edits and locks changes during a run', () => {
  for (const value of [null, -1, 2.5]) component.startupWait.value = value
  expect(state.config.simulator.wait_time).toBe(75)
  component.metadata.value = { active: true }
  component.startupWait.value = 120
  expect(state.config.simulator.wait_time).toBe(75)
})

it.each(['starting', 'failed', 'paused'])(
  'locks the bound target while the worker is alive with device status %s',
  async (status) => {
    state.client.get.mockResolvedValueOnce({ data: { active: true, status } })
    await component.readStatus()
    expect(component.state.value.locked).toBe(true)
    const before = { ...component.draft.value }
    component.edit('last_serial', 'USB-other')
    component.edit('touch_backend', 'maatouch')
    await component.detect()
    expect(component.draft.value).toEqual(before)
    expect(state.config.save_config).not.toHaveBeenCalled()

    state.client.get.mockResolvedValueOnce({ data: { active: false, status: 'closed' } })
    await component.readStatus()
    expect(component.state.value.locked).toBe(false)
    component.edit('last_serial', 'USB-other')
    expect(component.draft.value.last_serial).toBe('USB-other')
  }
)

it('keeps vendor backend edits with an unconfirmed preset in the draft', () => {
  component.edit('preset_id', 'windows.ldplayer9')
  component.edit('screenshot_backend', 'ld_native')
  expect(component.draft.value).toMatchObject({
    preset_id: 'windows.ldplayer9',
    screenshot_backend: 'ld_native'
  })
  expect(state.config.device_profile).toMatchObject({
    preset_id: 'manual.other',
    screenshot_backend: 'droidcast'
  })
  expect(state.config.save_config).not.toHaveBeenCalled()
})

it('saves backend edits immediately when the preset is already confirmed', () => {
  state.config.device_profile.preset_id = 'windows.ldplayer9'
  component.edit('preset_id', 'windows.ldplayer9')
  component.edit('screenshot_backend', 'ld_native')
  expect(state.config.device_profile.screenshot_backend).toBe('ld_native')
  expect(state.config.save_config).toHaveBeenCalledOnce()
})

it.each([
  ['screenshot_backend', 'adb_gzip', { screenshot_backend: 'adb_gzip', touch_backend: 'scrcpy' }],
  ['screenshot_backend', 'droidcast', { screenshot_backend: 'droidcast', touch_backend: 'scrcpy' }],
  ['touch_backend', 'maatouch', { screenshot_backend: 'droidcast', touch_backend: 'maatouch' }],
  ['touch_backend', 'scrcpy', { screenshot_backend: 'droidcast', touch_backend: 'scrcpy' }]
])('saves a valid pair after a preset round trip and %s = %s', (key, value, backends) => {
  const saved = {
    preset_id: 'windows.mumu12',
    installation_path: 'D:/MuMu',
    manager_path: 'D:/MuMu/nx_main/MuMuManager.exe',
    instance_id: '0',
    instance_name: 'Main',
    last_serial: '127.0.0.1:16384',
    game_package_confirmed: true,
    screenshot_backend: 'mumu_ipc',
    touch_backend: 'mumu_ipc'
  }
  state.config.device_profile = { ...saved }
  component.draft.value = { ...saved }

  component.edit('preset_id', 'windows.ldplayer9')
  component.edit('preset_id', 'windows.mumu12')
  component.edit('installation_path', 'D:/OtherMuMu')
  component.edit('instance_id', '1')
  expect(state.config.save_config).not.toHaveBeenCalled()

  component.edit(key, value)

  expect(state.config.device_profile).toEqual({ ...saved, ...backends })
  expect(component.draft.value).toMatchObject({
    ...backends,
    installation_path: 'D:/OtherMuMu',
    instance_id: '1',
    last_serial: '',
    game_package_confirmed: false
  })
  expect(state.config.save_config).toHaveBeenCalledOnce()
})

afterEach(() => {
  state.unmounted.forEach((callback) => callback())
  scope.stop()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.clearAllMocks()
})

it('pauses hidden status polling, resumes immediately, and removes its listener', async () => {
  state.mounted.forEach((callback) => callback())
  await vi.advanceTimersByTimeAsync(3000)
  expect(state.client.get).toHaveBeenCalledTimes(2)
  document.visibilityState = 'hidden'
  visibilityChanged()
  await vi.advanceTimersByTimeAsync(9000)
  expect(state.client.get).toHaveBeenCalledTimes(2)
  document.visibilityState = 'visible'
  visibilityChanged()
  await vi.advanceTimersByTimeAsync(0)
  expect(state.client.get).toHaveBeenCalledTimes(3)
  state.unmounted.forEach((callback) => callback())
  expect(document.removeEventListener).toHaveBeenCalledWith('visibilitychange', visibilityChanged)
  await vi.advanceTimersByTimeAsync(6000)
  expect(state.client.get).toHaveBeenCalledTimes(3)
})

it('does not overlap slow status requests', async () => {
  let finish
  state.client.get.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      })
  )
  state.mounted.forEach((callback) => callback())
  await vi.advanceTimersByTimeAsync(9000)
  expect(state.client.get).toHaveBeenCalledTimes(1)
  finish({ data: {} })
  await vi.advanceTimersByTimeAsync(3000)
  expect(state.client.get).toHaveBeenCalledTimes(2)
})

const startupCases = [
  ['macos.mumu_pro', 'macos', 'start', { instance_id: '1', topology_fingerprint: 'a'.repeat(64) }],
  ['windows.mumu12', 'windows', 'start', { instance_id: '2', manager_path: 'C:/MuMuManager.exe' }],
  ['windows.ldplayer9', 'windows', 'start', { instance_id: '2', manager_path: 'C:/dnconsole.exe' }],
  [
    'windows.ldplayer14',
    'windows',
    'start',
    { instance_id: '3', manager_path: 'C:/dnconsole.exe' }
  ],
  [
    'windows.nox',
    'windows',
    'start',
    {
      instance_id: 'Nox_1',
      instance_uuid: 'uuid',
      topology_fingerprint: 'fingerprint',
      manager_path: 'C:/NoxConsole.exe'
    }
  ],
  [
    'macos.avd',
    'macos',
    'avd/start',
    { instance_id: 'Mower_API_35', manager_path: '/sdk/emulator' }
  ],
  [
    'linux.avd',
    'linux',
    'avd/start',
    { instance_id: 'Mower_API_35', manager_path: '/sdk/emulator' }
  ],
  [
    'linux.genymotion',
    'linux',
    'genymotion/start',
    { instance_id: '12345678-1234-1234-1234-123456789abc', manager_path: '/bin/gmtool' }
  ],
  [
    'linux.redroid',
    'linux',
    'redroid/start',
    {
      instance_id: 'a'.repeat(64),
      manager_path: '/bin/docker',
      installation_path: '/bin',
      config_path: 'unix:///var/run/docker.sock'
    }
  ],
  [
    'linux.waydroid',
    'linux',
    'start',
    {
      instance_id: 'waydroid:501',
      manager_path: '/bin/waydroid',
      installation_path: '/var/lib/waydroid',
      config_path: '/var/lib/waydroid/waydroid.cfg'
    }
  ]
]

it.each(startupCases)(
  'detects and starts only the selected %s target',
  async (preset_id, host, endpoint, binding) => {
    const target = { ...state.config.device_profile, preset_id, ...binding, last_serial: '' }
    component.draft.value = target
    component.metadata.value = { host_platform: host }
    state.config.flush_config_saves = vi.fn(async () => {})
    state.client.post = vi.fn(async (url) => ({
      data: url.endsWith('/preflight')
        ? { ok: false, error: { code: 'instance_stopped' } }
        : { ok: true, serial: '127.0.0.1:16416', game_package: 'com.hypergryph.arknights' }
    }))
    await component.detect('preflight')
    expect(state.client.post.mock.calls.map(([url]) => url.split('/device/')[1])).toEqual([
      'preflight',
      endpoint
    ])
    const payload = state.client.post.mock.calls[1][1]
    expect(payload.device.instance_id).toBe(binding.instance_id)
    if (endpoint !== 'start') expect(payload.confirmed_instance).toBe(binding.instance_id)
    expect(state.config.device_profile.instance_id).toBe(binding.instance_id)
    expect(component.requestError.value).toBe('')
  }
)

it.each(['package_missing', 'binding_changed', 'endpoint_unresolved', 'boot_incomplete'])(
  'does not launch after %s',
  async (code) => {
    component.draft.value = {
      preset_id: 'macos.mumu_pro',
      instance_id: '1',
      topology_fingerprint: 'a'.repeat(64)
    }
    component.metadata.value = { host_platform: 'macos' }
    state.config.flush_config_saves = vi.fn(async () => {})
    state.client.post = vi.fn(async () => ({ data: { ok: false, error: { code } } }))
    await component.detect('preflight')
    expect(state.client.post).toHaveBeenCalledOnce()
    expect(component.result.value.error.code).toBe(code)
  }
)

it('keeps the read-only connection test free of startup even when the target is stopped', async () => {
  component.draft.value = {
    preset_id: 'macos.mumu_pro',
    instance_id: '1',
    topology_fingerprint: 'a'.repeat(64)
  }
  component.metadata.value = { host_platform: 'macos' }
  state.config.flush_config_saves = vi.fn(async () => {})
  state.client.post = vi.fn(async () => ({
    data: { ok: false, error: { code: 'instance_stopped' } }
  }))
  await component.selectDetect('preflight')
  expect(state.client.post).toHaveBeenCalledOnce()
})

it('retains performance from a tested target and clears it on identity edits', async () => {
  state.config.flush_config_saves = vi.fn(async () => {})
  const performance = {
    status: 'available',
    cpu_cores: 4,
    memory_mb: 3840,
    recommended_mode: 'high'
  }
  await component.acceptPreflight({ ok: true, serial: 'USB-123', observations: { performance } })
  expect(component.performanceObservation.value).toEqual(performance)
  expect(state.config).not.toHaveProperty('performance')
  component.edit('last_serial', 'USB-other')
  expect(component.performanceObservation.value).toBe(null)
})

it('displays resources even if game validation fails and clears them before retesting', async () => {
  const performance = {
    status: 'available',
    cpu_cores: 2,
    memory_mb: 1920,
    recommended_mode: 'medium'
  }
  await component.acceptPreflight({
    ok: false,
    observations: { performance },
    error: { code: 'package_missing' }
  })
  expect(component.performanceObservation.value).toEqual(performance)
  state.config.flush_config_saves = vi.fn(async () => {})
  state.client.post = vi.fn(async () => {
    expect(component.performanceObservation.value).toBe(null)
    return { data: { ok: false, error: { code: 'target_absent' } } }
  })
  await component.selectDetect('preflight')
  expect(component.performanceObservation.value).toBe(null)
})

it('keeps multiple stopped candidates pending until a user selects one', async () => {
  state.client.get.mockResolvedValue({ data: { host_platform: 'macos' } })
  const candidates = ['0', '1'].map((instance_id) => ({
    key: instance_id,
    binding: {
      preset_id: 'macos.mumu_pro',
      instance_id,
      topology_fingerprint: instance_id.repeat(64)
    }
  }))
  component.draft.value = { preset_id: 'macos.mumu_pro', last_serial: '' }
  component.metadata.value = { host_platform: 'macos' }
  state.config.flush_config_saves = vi.fn(async () => {})
  state.client.post = vi.fn(async (url) => ({
    data: url.endsWith('/discover')
      ? { kind: 'discovery', candidates }
      : {
          ok: false,
          error: { code: url.endsWith('/preflight') ? 'instance_stopped' : 'package_missing' }
        }
  }))
  await component.detect('discover')
  expect(state.client.post).toHaveBeenCalledOnce()
  await component.detect('discover', '1')
  expect(state.client.post.mock.calls.map(([url]) => url.split('/device/')[1])).toEqual([
    'discover',
    'preflight',
    'start'
  ])
  expect(state.config.device_profile).toMatchObject({
    instance_id: '1',
    topology_fingerprint: '1'.repeat(64),
    last_serial: '',
    game_package_confirmed: false
  })
  expect(state.config.save_config).toHaveBeenCalledOnce()
})

it('retains a selected MuMu Pro identity after failed startup and retries the same target', async () => {
  state.client.get.mockResolvedValue({ data: { host_platform: 'macos' } })
  const binding = {
    preset_id: 'macos.mumu_pro',
    instance_id: '0',
    instance_name: 'alex',
    topology_fingerprint: 'a'.repeat(64)
  }
  component.draft.value = { ...state.config.device_profile, last_serial: '127.0.0.1:16448' }
  component.metadata.value = { host_platform: 'macos' }
  component.result.value = { kind: 'discovery', candidates: [{ key: 'alex', binding }] }
  state.config.flush_config_saves = vi.fn(async () => {})
  const savedTargets = []
  state.client.post = vi.fn(async (url) => {
    savedTargets.push({ ...state.config.device_profile })
    return {
      data: {
        ok: false,
        error: { code: url.endsWith('/preflight') ? 'instance_stopped' : 'startup_timeout' }
      }
    }
  })
  await component.detect('discover', 'alex')
  expect(state.config.device_profile).toMatchObject({ ...binding, last_serial: '' })
  expect(component.draft.value).toMatchObject({ ...binding, last_serial: '' })
  expect(component.savedHint.value).toBe(true)
  expect(state.config.save_config).toHaveBeenCalledOnce()
  await component.startBound()
  expect(state.client.post.mock.calls.map(([url]) => url.split('/device/')[1])).toEqual([
    'preflight',
    'start',
    'start'
  ])
  expect(savedTargets).toHaveLength(3)
  for (const target of savedTargets) expect(target).toMatchObject({ ...binding, last_serial: '' })
  expect(component.result.value.error.code).toBe('startup_timeout')
})

it('does not launch a selected instance if saving its identity fails', async () => {
  const previous = { ...state.config.device_profile }
  component.metadata.value = { host_platform: 'macos' }
  component.result.value = {
    kind: 'discovery',
    candidates: [
      {
        key: 'alex',
        binding: {
          preset_id: 'macos.mumu_pro',
          instance_id: '0',
          topology_fingerprint: 'a'.repeat(64)
        }
      }
    ]
  }
  state.config.flush_config_saves = vi.fn(async () => {})
  state.config.save_config.mockRejectedValue(new Error('保存配置失败'))
  state.client.post = vi.fn()
  await component.detect('discover', 'alex')
  expect(state.client.post).not.toHaveBeenCalled()
  expect(state.config.device_profile).toEqual(previous)
  expect(component.requestError.value).toBe('保存配置失败')
})

it('starts the unique discovered target after its stopped preflight', async () => {
  component.draft.value = { preset_id: 'macos.mumu_pro', last_serial: '' }
  component.metadata.value = { host_platform: 'macos' }
  state.config.flush_config_saves = vi.fn(async () => {})
  state.client.post = vi.fn(async (url) => ({
    data: url.endsWith('/discover')
      ? {
          kind: 'discovery',
          selected_key: 'vm',
          candidates: [
            {
              key: 'vm',
              binding: {
                preset_id: 'macos.mumu_pro',
                instance_id: '1',
                topology_fingerprint: 'a'.repeat(64)
              }
            }
          ]
        }
      : {
          ok: false,
          error: { code: url.endsWith('/preflight') ? 'instance_stopped' : 'package_missing' }
        }
  }))
  await component.detect('discover')
  expect(state.client.post.mock.calls.map(([url]) => url.split('/device/')[1])).toEqual([
    'discover',
    'preflight',
    'start'
  ])
})

it('keeps manual MuMu serial checks read-only and sends manager preparation only with detection', async () => {
  component.draft.value = {
    preset_id: 'macos.mumu_pro',
    instance_id: '1',
    last_serial: '127.0.0.1:16416'
  }
  component.metadata.value = { host_platform: 'macos' }
  state.config.flush_config_saves = vi.fn(async () => {})
  state.client.post = vi.fn(async () => ({ data: { ok: false, error: { code: 'target_absent' } } }))
  await component.detect('preflight')
  expect(state.client.post.mock.calls[0][1]).not.toHaveProperty('start_manager')
  await component.detect('discover')
  expect(state.client.post.mock.calls[1][1].start_manager).toBe(true)
})
