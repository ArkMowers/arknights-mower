import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import { useConfigStore } from './config'
import { startPhysicalPreparation } from '@/utils/deviceSettings'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
let store

afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})

async function setup(overrides = {}) {
  const loaded = ref(false)
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', loaded)
  store = app.runWithContext(() => useConfigStore())
  const data = {
    account: 'saved account',
    package_type: 1,
    free_blacklist: '',
    reload_room: '',
    maa_mall_buy: '',
    maa_mall_blacklist: '',
    favorite: '',
    reclamation_algorithm: {},
    secret_front: {},
    maa_weekly_plan: [],
    maa_weekly_plan_active: '默认',
    simulator: { name: 'ReDroid', index: '0' },
    droidcast: { enable: false, rotate: false },
    custom_screenshot: { enable: false },
    device: {
      preset_id: 'linux.redroid',
      installation_path: '',
      manager_path: '',
      adb_path: '/adb',
      instance_id: 'game',
      instance_name: 'Game',
      last_serial: '127.0.0.1:5555',
      game_package: 'com.hypergryph.arknights',
      screenshot_backend: 'adb_gzip',
      touch_backend: 'scrcpy'
    },
    ...overrides
  }
  axios.get.mockImplementation(async (url) => ({
    data: url.endsWith('/conf') ? data : { plans: ['默认'] }
  }))
  axios.patch.mockResolvedValue({ data: {} })
  await store.load_config()
  loaded.value = true
  await nextTick()
  await store.flush_config_saves()
  return { loaded, data }
}

describe('partial configuration saves', () => {
  it.each(['deepseek-flash', 'deepseek-v4-pro', 'deepseek-future-model'])(
    'loads and saves DeepSeek model %s independently of custom interfaces',
    async (model) => {
      await setup({
        ai_type: 'deepseek',
        ai_deepseek_model: model,
        ai_model: 'relay-model',
        ai_base_url: 'https://relay.example/v1',
        ai_key: 'deepseek-key',
        ai_custom_key: 'relay-key'
      })
      expect(store.ai_deepseek_model).toBe(model)
      expect(axios.patch).not.toHaveBeenCalled()
      store.ai_deepseek_model = 'another-deepseek-model'
      await nextTick()
      await store.flush_config_saves()
      expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
        ai_deepseek_model: 'another-deepseek-model'
      })
      expect(store.ai_model).toBe('relay-model')
      expect(store.ai_base_url).toBe('https://relay.example/v1')
      expect(store.ai_key).toBe('deepseek-key')
      expect(store.ai_custom_key).toBe('relay-key')
      axios.patch.mockClear()
      store.ai_type = 'custom-online'
      await nextTick()
      await store.flush_config_saves()
      expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
        ai_type: 'custom-online'
      })
      expect(store.ai_deepseek_model).toBe('another-deepseek-model')
    }
  )

  it.each(['windows', 'darwin', 'linux'])(
    'starts desktop auto at xhigh on %s',
    async (platform) => {
      await setup({ runtime_platform: platform, performance_mode: 'auto' })
      expect(store.performance_mode).toBe('auto')
      expect(store.performance_effective_mode).toBe('xhigh')
    }
  )

  it('keeps the Android auto baseline at medium', async () => {
    await setup({ runtime_platform: 'android', performance_mode: 'auto' })
    expect(store.performance_effective_mode).toBe('medium')
  })

  it('shows the backend automatic verdict after a downgrade', async () => {
    await setup({
      runtime_platform: 'darwin',
      performance_mode: 'auto',
      performance_effective_mode: 'high'
    })
    expect(store.performance_effective_mode).toBe('high')
  })

  it('preserves an explicitly selected high mode', async () => {
    await setup({ runtime_platform: 'darwin', performance_mode: 'high' })
    expect(store.performance_mode).toBe('high')
    expect(store.performance_effective_mode).toBe('high')
  })

  it('keeps legacy switching disabled and saves only an explicit master toggle', async () => {
    await setup({
      product_switching: { grandet_mode: false, waiting_seconds: 4 },
      run_order_grandet_mode: { enable: true }
    })
    expect(store.product_switching.enable).toBe(false)
    store.product_switching.enable = true
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
      product_switching: { enable: true }
    })
    expect(store.product_switching.grandet_mode).toBe(false)
    expect(store.product_switching.waiting_seconds).toBe(4)
    expect(store.run_order_grandet_mode.enable).toBe(true)
  })

  it('preserves explicitly enabled product switching on load', async () => {
    await setup({ product_switching: { enable: true, waiting_seconds: 4 } })
    expect(store.product_switching.enable).toBe(true)
    expect(store.product_switching.waiting_seconds).toBe(4)
  })

  it('saves the existing startup protection independently of device identity', async () => {
    await setup({ simulator: { name: 'ReDroid', index: '0', wait_time: 75 } })
    store.simulator.wait_time = 90
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
      simulator: { wait_time: 90 }
    })
  })

  it.each([null, 'com.hypergryph.arknights'])(
    'saves the same serial after a physical identity change with package confirmation %s',
    async (confirmedPackage) => {
      await setup({
        device: {
          preset_id: 'manual.other',
          last_serial: 'USB-phone',
          adb_path: '/adb',
          screenshot_backend: 'adb_gzip',
          touch_backend: 'scrcpy',
          game_package: 'com.hypergryph.arknights',
          game_package_confirmed: false
        }
      })
      let accepted = { ...store.device_profile }
      const saves = []
      axios.patch.mockImplementation(async (_url, payload) => {
        const next = { ...accepted, ...payload.device }
        // Conf.updated clears an unchanged endpoint when its binding changes,
        // including an explicitly reentered serial equal to the old target.
        if (next.preset_id !== accepted.preset_id && next.last_serial === accepted.last_serial) {
          next.last_serial = ''
        }
        if (next.preset_id !== accepted.preset_id || next.last_serial !== accepted.last_serial) {
          next.game_package_confirmed = false
        }
        if (payload.device?.game_package) {
          next.game_package_confirmed = payload.device.game_package_confirmed ?? true
        }
        accepted = next
        saves.push({ ...accepted })
        return { data: { device: accepted, adb: accepted.last_serial } }
      })
      axios.post.mockImplementation(async (_url, payload) => {
        expect(accepted.last_serial).toBe(payload.preparation_serial)
        expect(accepted.preset_id).toBe('manual.physical')
        return { data: true }
      })

      await startPhysicalPreparation({
        axios,
        config: store,
        profile: { ...store.device_profile, preset_id: 'manual.physical' },
        serial: 'USB-phone',
        confirmedPackage
      })

      expect(saves[0]).toMatchObject({ preset_id: 'manual.physical', last_serial: '' })
      expect(accepted).toMatchObject({
        preset_id: 'manual.physical',
        last_serial: 'USB-phone',
        game_package_confirmed: Boolean(confirmedPackage)
      })
      expect(store.device_profile).toEqual(accepted)
      expect(axios.post).toHaveBeenCalledExactlyOnceWith('/start/0', {
        preparation_serial: 'USB-phone'
      })
      expect(
        axios.patch.mock.calls.every(([, payload]) => !('preparation_serial' in payload))
      ).toBe(true)
    }
  )

  it('keeps the saved physical identity without an endpoint if the final save fails', async () => {
    await setup({
      device: {
        preset_id: 'manual.other',
        last_serial: 'USB-phone',
        game_package: 'com.hypergryph.arknights',
        game_package_confirmed: false
      }
    })
    const accepted = {
      ...store.device_profile,
      preset_id: 'manual.physical',
      last_serial: '',
      game_package_confirmed: false
    }
    axios.patch.mockImplementation(async (_url, payload) => {
      if (payload.device?.last_serial === 'USB-phone') throw new Error('endpoint save failed')
      return { data: { device: accepted, adb: '' } }
    })

    await expect(
      startPhysicalPreparation({
        axios,
        config: store,
        profile: { ...store.device_profile, preset_id: 'manual.physical' },
        serial: 'USB-phone'
      })
    ).rejects.toThrow('endpoint save failed')

    expect(store.device_profile).toEqual(accepted)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('ignores confirmation belonging to a different target or package', async () => {
    await setup()
    await store.save_config({ serial: 'other-phone', game_package: 'com.hypergryph.arknights' })
    await store.save_config({
      serial: '127.0.0.1:5555',
      game_package: 'com.hypergryph.arknights.bilibili'
    })
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it.each([false, true])(
    'sends explicit same-package confirmation after switching serial when the old confirmation is %s',
    async (confirmed) => {
      const { data } = await setup()
      data.device.game_package_confirmed = confirmed
      await store.load_config()
      await nextTick()
      store.device_profile.last_serial = 'new-phone'
      store.device_profile.game_package_confirmed = true
      await nextTick()
      // Ordinary autosave may have consumed the changed fields before the
      // successful preflight explicitly confirms this target and package.
      await store.flush_config_saves()
      axios.patch.mockClear()
      await store.save_config({ serial: 'new-phone', game_package: 'com.hypergryph.arknights' })
      expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
        device: { game_package: 'com.hypergryph.arknights', game_package_confirmed: true }
      })
    }
  )

  it.each([
    ['adding a reward', { shield: true }, { shield: true, hot_water: true }],
    ['removing a reward', { shield: true, hot_water: true }, { shield: true }],
    ['clearing all rewards', { shield: true }, {}],
    [
      'editing arbitrary reward keys',
      { future_reward: true, 'vendor.reward': true },
      { future_reward: true, 'new/reward': false }
    ]
  ])('replaces the entire selection map when %s', async (_, initial, selected) => {
    await setup({ rogue: { core_char: '棘刺', collectible_mode_start_list: initial } })
    store.rogue.collectible_mode_start_list = selected
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
      rogue: { collectible_mode_start_list: selected }
    })
    expect(store.rogue.core_char).toBe('棘刺')
    await store.save_config()
    expect(axios.patch).toHaveBeenCalledTimes(1)
  })

  it('does not save on page load, then sends only the edited nested device field', async () => {
    await setup()
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.patch).not.toHaveBeenCalled()
    store.device_profile.last_serial = '127.0.0.1:5556'
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/conf'), {
      device: { last_serial: '127.0.0.1:5556' }
    })
  })
  it('keeps failed edits available and retries without sending unrelated settings', async () => {
    await setup()
    axios.patch.mockRejectedValueOnce({ response: { data: { error: '设备配置组合无效' } } })
    store.device_profile.last_serial = 'usb-device'
    await nextTick()
    await expect(store.flush_config_saves()).rejects.toMatchObject({
      response: { data: { error: '设备配置组合无效' } }
    })
    expect(store.config_save_error).toBe('设备配置组合无效')
    expect(store.device_profile.last_serial).toBe('usb-device')
    axios.patch.mockResolvedValueOnce({ data: {} })
    await store.save_config()
    expect(axios.patch.mock.lastCall[1]).toEqual({ device: { last_serial: 'usb-device' } })
    expect(store.config_save_error).toBe('')
  })

  it('preserves typing made during a save while accepting canonical compatibility fields', async () => {
    const { data } = await setup()
    let finish
    axios.patch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    store.device_profile.last_serial = 'first'
    await nextTick()
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'))
    store.device_profile.last_serial = 'latest'
    store.account = 'new draft'
    await nextTick()
    finish({ data: { device: { ...data.device, last_serial: 'first' }, adb: 'first' } })
    await store.flush_config_saves()
    expect(store.device_profile.last_serial).toBe('latest')
    expect(axios.patch.mock.calls[1][1]).toEqual({
      account: 'new draft',
      device: { last_serial: 'latest' }
    })
  })

  it('sends empty arrays and ignores unchanged fields absent from the page', async () => {
    await setup()
    store.free_blacklist = ['one']
    await nextTick()
    await store.flush_config_saves()
    store.free_blacklist = []
    store.device_profile.instance_name = 'Renamed'
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch.mock.lastCall[1]).toEqual({
      free_blacklist: '',
      device: { instance_name: 'Renamed' }
    })
  })

  it('chooses MuMu IPC as one consistent screenshot and touch pair', async () => {
    await setup()
    store.select_screenshot_backend('mumu_ipc')
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch.mock.lastCall[1]).toEqual({
      device: { screenshot_backend: 'mumu_ipc', touch_backend: 'mumu_ipc' }
    })
    store.select_screenshot_backend('custom')
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch.mock.lastCall[1]).toEqual({
      device: { screenshot_backend: 'custom', touch_backend: 'scrcpy' }
    })
  })

  it('reloads a configuration without writing normalized or changed server values back', async () => {
    const { data } = await setup()
    data.account = 'changed on the server'
    data.device.last_serial = 'server-device'
    await store.load_config()
    await nextTick()
    await store.flush_config_saves()
    expect(store.account).toBe('changed on the server')
    expect(axios.patch).not.toHaveBeenCalled()
  })

  it('selecting a touch backend keeps the MuMu IPC pair consistent', async () => {
    await setup()
    store.select_touch_backend('mumu_ipc')
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch.mock.lastCall[1]).toEqual({
      device: { screenshot_backend: 'mumu_ipc', touch_backend: 'mumu_ipc' }
    })
    store.select_touch_backend('maatouch')
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch.mock.lastCall[1]).toEqual({
      device: { screenshot_backend: 'droidcast', touch_backend: 'maatouch' }
    })
  })
  it('accepts the canonical Bilibili package without a compatibility save loop', async () => {
    await setup()
    axios.patch.mockResolvedValueOnce({ data: { package_type: 2 } })
    store.package_type = 'bilibili'
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch).toHaveBeenCalledTimes(1)
    expect(axios.patch.mock.lastCall[1]).toEqual({ package_type: 2 })
    expect(store.package_type).toBe('bilibili')
    store.account = 'later edit'
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch.mock.lastCall[1]).toEqual({ account: 'later edit' })
  })

  it('shows the server explanation when a configuration patch is rejected', async () => {
    await setup()
    axios.patch.mockRejectedValueOnce({
      response: {
        data: { error: 'invalid_configuration', message: 'MuMu IPC 截图与触控必须同时启用' }
      }
    })
    store.device_profile.touch_backend = 'mumu_ipc'
    await nextTick()
    await expect(store.flush_config_saves()).rejects.toBeDefined()
    expect(store.config_save_error).toBe('MuMu IPC 截图与触控必须同时启用')
  })

  it.each([
    ['maa_stage_inventory_enable', true],
    ['maa_stage_limit_rules', [{ stage: '1-7', operator: 'and', enabled: true, items: [] }]],
    ['maa_stage_ratio_rules', [{ name: 'Ratio', enabled: true, members: [] }]]
  ])('includes the plan identity when only %s changes', async (field, value) => {
    await setup()
    store[field] = value
    await nextTick()
    await store.flush_config_saves()
    expect(axios.patch.mock.lastCall[1]).toEqual({
      maa_weekly_plan_active: '默认',
      [field]: value
    })
  })
})

it('saves room drag swaps locally with a layout-only patch', async () => {
  await setup({ swap_contact_train: true })
  expect(store.right_side_room_order).toEqual(['train', 'contact', 'recycle'])
  axios.patch.mockClear()
  store.swap_right_side_facilities('train', 'recycle')
  await nextTick()
  await store.flush_config_saves()
  expect(axios.patch).toHaveBeenCalledTimes(1)
  expect(axios.patch.mock.lastCall[1]).toEqual({
    right_side_room_order: ['recycle', 'contact', 'train']
  })
  expect(store.build_advanced_settings()).not.toHaveProperty('right_side_room_order')
  const before = store.build_config().right_side_room_order
  store.swap_right_side_facilities('room_1_1', 'contact')
  store.swap_right_side_facilities('', 'train')
  store.swap_right_side_facilities('contact', 'contact')
  expect(store.right_side_room_order).toEqual(before)
  await nextTick()
  await store.flush_config_saves()
  expect(axios.patch).toHaveBeenCalledTimes(1)
})

it('loads the explicit three-room order before the legacy switch', async () => {
  await setup({ swap_contact_train: true, right_side_room_order: ['recycle', 'train', 'contact'] })
  expect(store.right_side_room_order).toEqual(['recycle', 'train', 'contact'])
  expect(store.build_config()).not.toHaveProperty('swap_contact_train')
})
