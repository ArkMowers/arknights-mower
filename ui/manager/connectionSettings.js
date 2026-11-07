export const idleActionKeys = [
  ['close', 'close_simulator_when_idle'],
  ['exit', 'exit_game_when_idle'],
  ['home', 'return_home_when_idle']
]

export function idleAction(values) {
  return idleActionKeys.find(([, key]) => values[key] === true)?.[0] || 'idle'
}

export function idleActionPatch(action) {
  if (!['idle', ...idleActionKeys.map(([value]) => value)].includes(action)) return {}
  return Object.fromEntries(idleActionKeys.map(([value, key]) => [key, action === value]))
}

export function idleOptions(values) {
  return [
    { value: 'idle', label: '无操作' },
    { value: 'home', label: '返回首页' },
    { value: 'exit', label: '退出游戏' },
    {
      value: 'close',
      label: '关闭模拟器',
      disabled: values['device.preset_id'] === 'manual.physical'
    }
  ]
}

export function connectionFields(fields, values) {
  return fields.flatMap((field) => {
    const key = field.key
    if (['exit_game_when_idle', 'return_home_when_idle'].includes(key)) return []
    if (key === 'close_simulator_when_idle')
      return [
        {
          ...field,
          label: '空闲时',
          searchKeywords: '空闲 关闭模拟器 退出游戏 返回首页',
          kind: 'idle_action',
          help: '关闭模拟器或退出游戏仅在空闲超过 5 分钟时执行；返回首页不受此限制。'
        }
      ]
    if (key === 'custom_screenshot.command' && values['device.screenshot_backend'] !== 'custom')
      return []
    if (key === 'droidcast.rotate' && values['device.screenshot_backend'] !== 'droidcast') return []
    if (
      ['tap_to_launch_game.x', 'tap_to_launch_game.y'].includes(key) &&
      values['tap_to_launch_game.mode'] !== 'tap'
    )
      return []
    if (key === 'tap_to_launch_game.command' && values['tap_to_launch_game.mode'] !== 'custom')
      return []
    if (key === 'device.simulator_hotkey_delay' && !values['device.simulator_hotkey']?.trim())
      return []
    if (
      key === 'fix_mumu12_adb_disconnect' &&
      (values['device.preset_id'] !== 'windows.mumu12' || idleAction(values) !== 'close')
    )
      return []
    return [field]
  })
}
