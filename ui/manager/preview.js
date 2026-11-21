import { createApp, h } from 'vue'
import ManagerApp from './ManagerApp.vue'

if (!import.meta.env.DEV || import.meta.env.MODE !== 'manager-preview') {
  throw new Error('管理器示例仅供本地 manager-preview 模式使用')
}

const clone = (value) => JSON.parse(JSON.stringify(value))
const rows = [
  '日常基建',
  '小号 · 官服',
  '材料储备',
  'Bilibili 服',
  '活动刷图',
  '备用账号',
  '测试环境',
  '待配置实例'
].map((name, idx) => ({
  name,
  path: idx === 7 ? '' : `/Mower/instances/account-${idx + 1}`,
  token: '',
  port: 5800 + idx,
  state: [1, 3, 4].includes(idx) ? 'running' : 'stopped',
  editable: ![1, 3, 4].includes(idx),
  can_start: ![1, 3, 4, 7].includes(idx),
  can_stop: [1, 3, 4].includes(idx),
  can_open_browser: [1, 3, 4].includes(idx),
  reason: idx === 7 ? '尚未选择保存目录' : '',
  start_automatically: idx < 5
}))
const textField = (key, label, group = '模拟器与设备', kind = 'text', extra = {}) => ({
  key,
  label,
  group,
  kind,
  ...extra
})
const select = (key, label, options, group) => textField(key, label, group, 'select', { options })
const fields = [
  select('device.preset_id', '模拟器预设', [
    ['macos.mumu_pro', 'MuMu Pro'],
    ['macos.bluestacks_air', 'BlueStacks Air'],
    ['manual.other', '其他模拟器'],
    ['manual.physical', '实体设备']
  ]),
  textField('device.installation_path', '模拟器安装目录', '模拟器与设备', 'directory'),
  textField('device.manager_path', '模拟器管理程序', '模拟器与设备', 'file'),
  textField('device.config_path', '模拟器配置文件', '模拟器与设备', 'file'),
  textField('device.adb_path', 'ADB 程序', '模拟器与设备', 'file'),
  textField('device.instance_id', '模拟器实例编号'),
  textField('device.instance_name', '模拟器实例名称'),
  textField('device.last_serial', 'ADB 连接地址'),
  select('device.game_package', '游戏包名', [
    ['com.hypergryph.arknights', '官服'],
    ['com.hypergryph.arknights.bilibili', 'Bilibili 服']
  ]),
  ...['instance_uuid', 'topology_fingerprint'].map((key) =>
    textField(`device.${key}`, key, '模拟器与设备', 'text', { read_only: true })
  ),
  select(
    'device.screenshot_backend',
    '截图后端',
    [
      ['droidcast', 'DroidCast'],
      ['adb', 'ADB'],
      ['custom', '自定义命令']
    ],
    '截图与触控'
  ),
  select(
    'device.touch_backend',
    '触控后端',
    [
      ['scrcpy', 'scrcpy'],
      ['adb', 'ADB']
    ],
    '截图与触控'
  ),
  textField('droidcast.rotate', '旋转截图 180 度', '截图与触控', 'boolean'),
  textField('custom_screenshot.command', '自定义截图命令', '截图与触控'),
  textField('device.recovery_timeout', '连接超时（秒）', '连接恢复', 'integer', { min: 1 }),
  textField('device.recovery_attempts', '恢复尝试次数', '连接恢复', 'integer', { min: 0 }),
  select(
    'performance_mode',
    '设备性能适配',
    [
      ['normal', '标准'],
      ['high', '高性能'],
      ['low', '低性能']
    ],
    '性能'
  ),
  select(
    'tap_to_launch_game.mode',
    '启动游戏方式',
    [
      ['adb', 'ADB'],
      ['tap', '点击屏幕'],
      ['custom', '自定义命令']
    ],
    '游戏启动与空闲'
  ),
  textField('close_simulator_when_idle', '空闲时关闭模拟器', '游戏启动与空闲', 'boolean'),
  select(
    'startup_mode',
    '实例启动方式',
    [
      ['window', '打开窗口'],
      ['background', '后台运行']
    ],
    '实例启动'
  ),
  textField('maa_path', 'MAA 安装目录', 'MAA', 'directory')
]
const shared = {
  'device.preset_id': 'macos.mumu_pro',
  'device.installation_path': '/Applications/MuMuPlayer.app',
  'device.manager_path': '',
  'device.config_path': '',
  'device.adb_path': '',
  'device.screenshot_backend': 'droidcast',
  'device.touch_backend': 'scrcpy',
  'device.recovery_timeout': 180,
  'device.recovery_attempts': 3,
  'droidcast.rotate': false,
  'custom_screenshot.command': '',
  performance_mode: 'normal',
  'tap_to_launch_game.mode': 'adb',
  close_simulator_when_idle: false,
  startup_mode: 'window',
  maa_path: '/Applications/MAA.app'
}
const values = rows.map((row, idx) => ({
  ...clone(shared),
  'device.instance_id': String(idx),
  'device.instance_name': `MuMu ${idx + 1}`,
  'device.game_package': 'com.hypergryph.arknights',
  'device.last_serial': '',
  'device.instance_uuid': '',
  'device.topology_fingerprint': 'preview-binding'
}))
const policies = rows.map(() => ({
  independent_configuration: false,
  instance_override: { local_keys: [], manager_values: {} }
}))
function nested(flat) {
  const result = {}
  for (const [path, value] of Object.entries(flat)) {
    const parts = path.split('.')
    let target = result
    for (const key of parts.slice(0, -1)) target = target[key] ||= {}
    target[parts.at(-1)] = value
  }
  return result
}
const api = {
  add: async (name, path = null) => {
    if (path === null) {
      let number = 1
      while (rows.some((row) => row.path === `/Mower/instances/instance-${number}`)) number++
      path = `/Mower/instances/instance-${number}`
    }
    const idx = rows.length
    rows.push({
      name,
      path,
      state: 'stopped',
      editable: true,
      can_start: Boolean(path),
      can_stop: false,
      can_open_browser: false,
      port: null,
      token: '',
      reason: path ? '' : '尚未选择保存目录'
    })
    values.push({
      ...clone(shared),
      'device.instance_id': '',
      'device.instance_name': '',
      'device.game_package': 'com.hypergryph.arknights',
      'device.last_serial': '',
      'device.instance_uuid': '',
      'device.topology_fingerprint': ''
    })
    policies.push({
      independent_configuration: false,
      instance_override: { local_keys: [], manager_values: {} }
    })
    return { ok: true, idx }
  },
  rename: async (idx, name) => {
    rows[idx].name = name
    return { ok: true }
  },
  remove: async (idx) => {
    rows.splice(idx, 1)
    values.splice(idx, 1)
    policies.splice(idx, 1)
    return { ok: true }
  },
  select_path: async (idx) => {
    Object.assign(rows[idx], {
      path: `/Mower/instances/example-${idx + 1}`,
      can_start: true,
      reason: ''
    })
    return { ok: true }
  },
  update_settings: async (idx, settings) => {
    Object.assign(rows[idx], settings)
    return { ok: true }
  },
  start_all: async () => {
    for (let idx = 0; idx < rows.length; idx++) if (rows[idx].can_start) await api.start(idx)
    return { ok: true }
  },
  stop_all: async () => {
    for (let idx = 0; idx < rows.length; idx++) if (rows[idx].can_stop) await api.stop(idx)
    return { ok: true }
  },
  control_instances: async (action, targets) => {
    const results = []
    for (const target of targets) {
      const row = rows[target.idx]
      if (!row || row.name !== target.name || row.path !== target.path)
        throw new Error('实例列表已变化')
      const allowed = action === 'start' ? row.can_start : row.can_stop
      if (allowed) await api[action](target.idx)
      results.push({
        idx: target.idx,
        name: target.name,
        status: allowed ? 'dispatched' : 'skipped',
        message: allowed ? `已派发${action === 'start' ? '启动' : '停止'}请求` : '当前状态无需操作'
      })
    }
    return { ok: true, results }
  },
  get_instances: async () => clone(rows),
  mark_ready: async () => {},
  get_device_settings: async (idx) => ({
    values: nested(values[idx]),
    fields: clone(fields),
    ...clone(policies[idx]),
    shared_keys: Object.keys(shared),
    override_keys: ['startup_mode', 'maa_path'],
    original_policy: {
      revision: 'preview',
      shared_values: clone(shared),
      local_values: clone(values[idx]),
      ...clone(policies[idx])
    }
  }),
  discover_device_settings: async () => ({
    kind: 'discovery',
    ok: true,
    host_platform: 'macos',
    guidance: '检测结果为示例数据。选择具体实例后保存，实际连接将在启动时验证。',
    candidates: rows.map((row, idx) => ({
      key: String(idx),
      preset_id: 'macos.mumu_pro',
      instance_name: `MuMu ${idx + 1}`,
      instance_id: String(idx),
      state: 'stopped',
      shared_template_matches: true,
      binding: {
        preset_id: 'macos.mumu_pro',
        installation_path: '/Applications/MuMuPlayer.app',
        manager_path: '',
        config_path: '',
        instance_id: String(idx),
        instance_name: `MuMu ${idx + 1}`,
        instance_uuid: '',
        topology_fingerprint: `preview-${idx}`
      }
    }))
  }),
  test_device_settings: async () => ({
    kind: 'preflight',
    ok: true,
    host_platform: 'macos',
    status: 'ready',
    serial: '127.0.0.1:16384',
    game_package: 'com.hypergryph.arknights'
  }),
  update_device_settings: async (idx, patch, target, original, policy) => {
    Object.assign(values[idx], patch)
    Object.assign(policies[idx], policy)
    return { ok: true }
  },
  get_common_settings: async () => ({
    values: clone(shared),
    fields: clone(fields.filter((field) => Object.hasOwn(shared, field.key)))
  }),
  preview_common_settings: async () => ({
    rows: rows.map((row, idx) => ({ idx, name: row.name, fields: [], warnings: [] }))
  }),
  update_all_settings: async () => ({ ok: true, results: [] }),
  select_device_path: async () => null,
  select_common_path: async () => null,
  start: async (idx) => {
    Object.assign(rows[idx], {
      state: 'running',
      editable: false,
      can_start: false,
      can_stop: true,
      can_open_browser: true
    })
    return { ok: true }
  },
  stop: async (idx) => {
    Object.assign(rows[idx], {
      state: 'stopped',
      editable: true,
      can_start: true,
      can_stop: false,
      can_open_browser: false
    })
    return { ok: true }
  }
}
window.pywebview = {
  api: new Proxy(api, {
    get: (target, key) =>
      typeof key === 'string' && (key.startsWith('__v_') || key === 'then')
        ? undefined
        : target[key] ||
          (async () => {
            throw new Error('此操作不在离线预览范围内，请在正式管理器中使用。')
          })
  })
}
createApp({
  render: () =>
    h('div', [
      h(
        'div',
        {
          style:
            'padding:8px 16px;text-align:center;background:#e6f4ea;color:#245e3b;font:12px system-ui'
        },
        '离线预览 · 示例数据，仅在当前页面内修改，不连接设备'
      ),
      h(ManagerApp)
    ])
}).mount('#app')
