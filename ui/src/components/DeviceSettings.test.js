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
