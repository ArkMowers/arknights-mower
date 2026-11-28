export const DEFAULT_RUNNING_LOG_LAYOUT = 'right_rail'

export const LOG_LAYOUT_MODULES = {
  screenshot: '截图预览',
  tasks: '任务列表',
  daily: '今日任务',
  log: '运行日志'
}

const SAVED_LAYOUTS = [
  {
    value: DEFAULT_RUNNING_LOG_LAYOUT,
    left: ['daily', 'log'],
    right: ['screenshot', 'tasks']
  },
  {
    value: 'left_rail',
    left: ['screenshot', 'tasks'],
    right: ['daily', 'log']
  },
  {
    value: 'right_rail_log',
    left: ['daily', 'tasks'],
    right: ['screenshot', 'log']
  },
  {
    value: 'left_rail_log',
    left: ['screenshot', 'log'],
    right: ['daily', 'tasks']
  },
  {
    value: 'stacked',
    single: ['screenshot', 'daily', 'tasks', 'log']
  }
]

function containsAllModules(ids) {
  return (
    ids.length === Object.keys(LOG_LAYOUT_MODULES).length &&
    new Set(ids).size === ids.length &&
    ids.every((id) => Object.hasOwn(LOG_LAYOUT_MODULES, id))
  )
}

function readLayout(value) {
  const preset = SAVED_LAYOUTS.find((item) => item.value === value)
  if (preset?.single) {
    return { mode: 'single', left: [], right: [], single: [...preset.single] }
  }
  if (preset) {
    return {
      mode: 'split',
      left: [...preset.left],
      right: [...preset.right],
      single: [...preset.left, ...preset.right]
    }
  }
  if (typeof value !== 'string') return null
  if (value.startsWith('custom:single:')) {
    const single = value.slice('custom:single:'.length).split(',')
    if (containsAllModules(single)) return { mode: 'single', left: [], right: [], single }
  }
  if (value.startsWith('custom:split:')) {
    const columns = value.slice('custom:split:'.length).split('|')
    if (columns.length !== 2) return null
    const [left, right] = columns.map((column) => column.split(','))
    const single = [...left, ...right]
    if (containsAllModules(single)) return { mode: 'split', left, right, single }
  }
  return null
}

export function isValidRunningLogLayout(value) {
  return readLayout(value) !== null
}

export function parseRunningLogLayout(value) {
  return readLayout(value) ?? readLayout(DEFAULT_RUNNING_LOG_LAYOUT)
}

export function serializeRunningLogLayout({ mode, left, right, single }) {
  if (mode === 'single') {
    return single.join(',') === SAVED_LAYOUTS.at(-1).single.join(',')
      ? 'stacked'
      : `custom:single:${single.join(',')}`
  }
  const preset = SAVED_LAYOUTS.find(
    (item) => item.left?.join(',') === left.join(',') && item.right.join(',') === right.join(',')
  )
  return preset?.value ?? `custom:split:${left.join(',')}|${right.join(',')}`
}
