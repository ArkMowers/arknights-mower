import { describe, expect, it, vi } from 'vitest'
import { createSSRApp, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import CommonSettings from './CommonSettings.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup(values = {}, shared = false) {
  const props = reactive({
    values,
    fields: [
      {
        key: 'device.screenshot_backend',
        label: '截图方式',
        default: 'droidcast',
        group: '连接方式',
        shared_connection: shared
      },
      {
        key: 'device.touch_backend',
        default: 'scrcpy',
        group: '连接方式',
        shared_connection: shared
      },
      { key: 'screenshot', label: '截图保存时间', kind: 'number', default: 1, group: '截图保存' },
      { key: 'startup_mode', default: 'window', group: '实例启动' }
    ]
  })
  const emit = vi.fn((event, next) => {
    if (event === 'update:values') props.values = next
  })
  const component = CommonSettings.setup(props, { expose() {}, emit })
  return { props, emit, component }
}

function waitingField() {
  return {
    key: 'waiting_scene',
    kind: 'waiting_scene',
    group: '运行参数',
    label: '页面等待参数',
    shared_connection: true,
    scenes: [
      ['CONNECTING', '正在提交反馈至神经'],
      ['UNKNOWN', '未知'],
      ['LOADING', '加载中'],
      ['LOGIN_LOADING', '场景跳转时的等待界面'],
      ['LOGIN_MAIN_NOENTRY', '登录页面（无按钮入口）'],
      ['OPERATOR_ONGOING', '代理作战']
    ],
    default: {
      CONNECTING: [1, 10],
      UNKNOWN: [1, 10],
      LOADING: [2, 30],
      LOGIN_LOADING: [3, 10],
      LOGIN_MAIN_NOENTRY: [3, 10],
      OPERATOR_ONGOING: [10, 30]
    }
  }
}

describe('manager common settings', () => {
  it('opts into one field without copying unrelated defaults', () => {
    const { props, component } = setup()
    component.toggle(props.fields[2], true)
    expect(props.values).toEqual({ screenshot: 1 })
    component.change(props.fields[2], 24)
    expect(props.values).toEqual({ screenshot: 24 })
    component.toggle(props.fields[2], false)
    expect(props.values).toEqual({})
  })

  it('selects screenshot and touch together and preserves the MuMu pair', () => {
    const { props, component } = setup({ screenshot: 12 })
    component.toggle(props.fields[0], true)
    expect(props.values['device.touch_backend']).toBe('scrcpy')
    component.change(props.fields[0], 'mumu_ipc')
    expect(props.values['device.touch_backend']).toBe('mumu_ipc')
    component.change(props.fields[1], 'maatouch')
    expect(props.values['device.screenshot_backend']).toBe('droidcast')
    component.toggle(props.fields[1], false)
    expect(props.values).toEqual({ screenshot: 12 })
  })

  it('keeps the startup mode as an explicit draft and permits returning to the default', () => {
    const { props, component } = setup({ screenshot: 12 })
    const field = props.fields[3]
    component.toggle(field, true)
    expect(props.values).toEqual({ screenshot: 12, startup_mode: 'window' })
    component.change(field, 'background')
    expect(props.values).toEqual({ screenshot: 12, startup_mode: 'background' })
    component.toggle(field, false)
    expect(props.values).toEqual({ screenshot: 12 })
  })
})

it('keeps shared connection defaults mandatory while allowing their values to change', () => {
  const { props, emit, component } = setup(
    {
      'device.screenshot_backend': 'droidcast',
      'device.touch_backend': 'scrcpy'
    },
    true
  )
  component.toggle(props.fields[0], false)
  expect(emit).not.toHaveBeenCalled()
  expect(component.enabled('device.screenshot_backend')).toBe(true)
  component.change(props.fields[0], 'mumu_ipc')
  expect(props.values).toEqual({
    'device.screenshot_backend': 'mumu_ipc',
    'device.touch_backend': 'mumu_ipc'
  })
  component.toggle(props.fields[2], true)
  expect(props.values.screenshot).toBe(1)
  component.toggle(props.fields[2], false)
  expect(props.values.screenshot).toBeUndefined()
  expect(props.values['device.touch_backend']).toBe('mumu_ipc')
})

it('labels shared simulator presets with their simulator name and platform', () => {
  const { component } = setup()
  expect(
    component.options({
      key: 'device.preset_id',
      options: [
        ['windows.mumu12', 'windows.mumu12'],
        ['manual.other', 'manual.other']
      ]
    })
  ).toEqual([
    { value: 'windows.mumu12', label: 'MuMu 12 (windows)' },
    { value: 'manual.other', label: '其他模拟器 (manual)' }
  ])
  expect(component.options({ key: 'startup_mode', options: [['window', '普通启动']] })).toEqual([
    { value: 'window', label: '普通启动' }
  ])
})

it('edits only one waiting cell without mutating other scenes, the original object or schema defaults', () => {
  const field = waitingField()
  const original = { ...structuredClone(field.default), UNKNOWN: [7, 13] }
  const { props, emit, component } = setup({ waiting_scene: original, screenshot: 12 })
  props.fields.push(field)
  component.change(field, { ...original, LOADING: [2, 25] })
  expect(props.values).toEqual({
    screenshot: 12,
    waiting_scene: { ...original, LOADING: [2, 25] }
  })
  expect(original.LOADING).toEqual([2, 30])
  expect(field.default.LOADING).toEqual([2, 30])
  component.toggle(field, false)
  expect(emit).toHaveBeenCalledTimes(1)
  expect(component.enabled('waiting_scene')).toBe(true)
})

it.each(['disabled', 'read_only'])('does not edit the waiting table when %s', (condition) => {
  const field = waitingField()
  const { props, emit, component } = setup({ waiting_scene: structuredClone(field.default) })
  props.fields.push(field)
  if (condition === 'disabled') props.disabled = true
  else field.read_only = true
  component.change(field, { ...field.default, LOADING: [5, 30] })
  expect(emit).not.toHaveBeenCalled()
  expect(props.values.waiting_scene.LOADING).toEqual([2, 30])
})

it('searches waiting scene labels and keeps the six rows together', () => {
  const field = waitingField()
  const { props, component } = setup({ waiting_scene: structuredClone(field.default) })
  props.fields.push(field)
  component.search.value = '代理作战'
  expect(component.visibleFields.value).toEqual([field])
  expect(field.scenes).toHaveLength(6)
})

it('renders connection settings in one open board with continuous subsections', async () => {
  const { props } = setup()
  props.fields.push(
    { key: 'device.preset_id', label: '模拟器预设', group: '模拟器模板', default: 'manual.other' },
    { key: 'device.adb_path', label: 'ADB 程序', group: '程序位置', default: '' },
    { key: 'performance_mode', label: '设备性能适配', group: '性能', default: 'auto' },
    { key: 'device.recovery_timeout', label: '恢复总时限', group: '连接恢复', default: 180 },
    {
      key: 'tap_to_launch_game.mode',
      label: '启动游戏方式',
      group: '游戏启动与空闲',
      default: 'adb'
    },
    waitingField()
  )
  const html = await renderToString(createSSRApp(CommonSettings, props))
  const boards = [...html.matchAll(/<details\b[^>]*class="common-group"[^>]*>/g)]
  expect(boards).toHaveLength(2)
  expect(boards[0][0]).toContain(' open')
  const headings = [...html.matchAll(/<h3\b[^>]*>([^<]+)<\/h3>/g)].map((match) => match[1])
  expect(headings).toEqual([
    '模拟器模板',
    '程序位置',
    '连接方式',
    '性能',
    '连接恢复',
    '游戏启动与空闲',
    '运行参数',
    '实例启动'
  ])
  expect(html).toContain('连接与启动')
  expect(html).not.toContain('邮件发信人')
})

it('searches the combined connection board without including unrelated settings', () => {
  const { props, component } = setup()
  props.fields.push(waitingField())
  component.search.value = '连接与启动'
  expect(component.visibleFields.value.map((field) => field.key)).toEqual([
    'device.screenshot_backend',
    'device.touch_backend',
    'startup_mode',
    'waiting_scene'
  ])
  expect(component.groups.value).toEqual(['连接与启动'])
})

const idleFields = [
  'close_simulator_when_idle',
  'exit_game_when_idle',
  'return_home_when_idle'
].map((key) => ({
  key,
  label: key,
  kind: 'boolean',
  default: false,
  group: '游戏启动与空闲',
  shared_connection: true
}))

it.each([
  ['idle', false, false, false],
  ['home', false, false, true],
  ['exit', false, true, false],
  ['close', true, false, false]
])('saves the common idle choice %s as mutually exclusive flags', (choice, close, exit, home) => {
  const { props, component } = setup({
    close_simulator_when_idle: true,
    exit_game_when_idle: true,
    return_home_when_idle: true
  })
  props.fields.push(...idleFields)
  const controls = component.visibleFields.value.filter(({ key }) =>
    idleFields.some((field) => field.key === key)
  )
  expect(controls).toHaveLength(1)
  expect(controls[0].kind).toBe('idle_action')
  expect(component.idleAction(props.values)).toBe('close')
  component.change(controls[0], choice)
  expect(props.values).toEqual({
    close_simulator_when_idle: close,
    exit_game_when_idle: exit,
    return_home_when_idle: home
  })
})

it('shows only applicable connection details and keeps their values across parent changes', () => {
  const values = {
    'device.preset_id': 'windows.mumu12',
    'device.screenshot_backend': 'droidcast',
    'tap_to_launch_game.mode': 'adb',
    'custom_screenshot.command': 'capture --png',
    'droidcast.rotate': true,
    'tap_to_launch_game.x': 100,
    'tap_to_launch_game.y': 200,
    'tap_to_launch_game.command': 'saved launch',
    'device.simulator_hotkey': '',
    'device.simulator_hotkey_delay': 4,
    close_simulator_when_idle: true,
    fix_mumu12_adb_disconnect: true
  }
  const { props, component } = setup(values)
  const conditional = [
    'custom_screenshot.command',
    'droidcast.rotate',
    'tap_to_launch_game.x',
    'tap_to_launch_game.y',
    'tap_to_launch_game.command',
    'device.simulator_hotkey_delay',
    'fix_mumu12_adb_disconnect'
  ]
  props.fields.push(
    ...conditional.map((key) => ({ key, group: '连接方式', label: key, shared_connection: true }))
  )
  const visible = () =>
    component.visibleFields.value
      .filter(({ key }) => conditional.includes(key))
      .map(({ key }) => key)
  expect(visible()).toEqual(['droidcast.rotate', 'fix_mumu12_adb_disconnect'])
  props.values = {
    ...values,
    'device.screenshot_backend': 'custom',
    'tap_to_launch_game.mode': 'tap',
    'device.simulator_hotkey': 'ctrl+f9'
  }
  expect(visible()).toEqual([
    'custom_screenshot.command',
    'tap_to_launch_game.x',
    'tap_to_launch_game.y',
    'device.simulator_hotkey_delay',
    'fix_mumu12_adb_disconnect'
  ])
  props.values = {
    ...props.values,
    'tap_to_launch_game.mode': 'custom',
    'device.preset_id': 'manual.physical'
  }
  expect(visible()).toEqual([
    'custom_screenshot.command',
    'tap_to_launch_game.command',
    'device.simulator_hotkey_delay'
  ])
  expect(component.idleOptions(props.values).find(({ value }) => value === 'close').disabled).toBe(
    true
  )
  props.values = {
    ...props.values,
    'device.screenshot_backend': 'adb_gzip',
    'device.preset_id': 'windows.mumu12',
    close_simulator_when_idle: false,
    exit_game_when_idle: true
  }
  expect(visible()).not.toContain('fix_mumu12_adb_disconnect')
  expect(visible()).not.toContain('custom_screenshot.command')
  expect(props.values['custom_screenshot.command']).toBe('capture --png')
  expect(props.values['droidcast.rotate']).toBe(true)
  expect(props.values['tap_to_launch_game.x']).toBe(100)
})

it('renders shared connection labels without forced checkboxes while keeping opt-in checkboxes', async () => {
  const { props } = setup({}, true)
  const html = await renderToString(createSSRApp(CommonSettings, props))
  expect(html).not.toContain('aria-label="统一设置截图方式"')
  expect(html).toContain('aria-label="统一设置截图保存时间"')
})

it('finds the combined idle selector by its individual actions', () => {
  const { props, component } = setup({ close_simulator_when_idle: true })
  props.fields.push(...idleFields)
  component.search.value = '退出游戏'
  expect(component.visibleFields.value.map(({ kind }) => kind)).toEqual(['idle_action'])
})
