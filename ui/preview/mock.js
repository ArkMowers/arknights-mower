import axios, { AxiosError } from 'axios'
import screenshot from './screenshot.svg?raw'
import {
  BlobReader,
  BlobWriter,
  TextReader,
  TextWriter,
  ZipReader,
  ZipWriter
} from '@zip.js/zip.js'

const clone = (value) => JSON.parse(JSON.stringify(value))
const previewGroups = [
  ['连接与运行', 'device', '设备与游戏连接', '示例设备身份、路径、截图与触控方式'],
  ['连接与运行', 'runtime', '运行参数', '示例性能与自动启动设置'],
  ['任务配置', 'daily', '日常任务', '示例日常任务开关'],
  ['任务配置', 'maa', 'MAA 设置', '示例 MAA 路径与更新设置'],
  ['任务配置', 'long', '长任务', '示例长任务开关与参数'],
  ['Mower 设置', 'accounts', '账号', '示例账号信息'],
  ['Mower 设置', 'notifications', '通知', '示例邮件设置'],
  ['Mower 设置', 'appearance', '界面与窗口', '示例界面主题'],
  ['Mower 设置', 'other_settings', '其他设置', '其余示例设置'],
  ['排班与计划', 'normal_plan', '正常排班', '示例主表与副表'],
  ['排班与计划', 'rescue_plan', '救急排班', '示例救急排班'],
  ['排班与计划', 'weekly_plan', '周计划', '示例 MAA 周计划'],
  ['数据', 'inventory', '库存', '示例库存数据']
].map(([section, key, label, description]) => ({ section, key, label, description }))

function previewFieldGroup(key) {
  if (['device', 'simulator', 'adb', 'maa_adb_path', 'package_type'].includes(key)) return 'device'
  if (['theme', 'webview'].includes(key)) return 'appearance'
  if (key === 'skland_info') return 'accounts'
  if (['account', 'pass_code', 'recipient', 'mail_enable', 'custom_smtp_server'].includes(key))
    return 'notifications'
  if (key.startsWith('maa_weekly_plan')) return 'weekly_plan'
  if (key.startsWith('automatic_rescue')) return 'rescue_plan'
  if (['start_automatically', 'performance_mode', 'screenshot_interval'].includes(key))
    return 'runtime'
  if (key.startsWith('maa_rg_') || key === 'maa_long_task_type') return 'long'
  if (key.startsWith('maa_')) return 'maa'
  if (['check_mail_enable', 'report_enable', 'skland_enable'].includes(key)) return 'daily'
  return 'other_settings'
}

export function createPreviewConfiguration(config, theme = 'light') {
  return {
    ...clone(config),
    theme: ['light', 'dark', 'system'].includes(theme) ? theme : 'light',
    webview: { scale: 1, tray: true, ...clone(config.webview || {}) },
    recipient: Array.isArray(config.recipient) ? clone(config.recipient) : [],
    custom_smtp_server: {
      enable: false,
      server: '',
      encryption: 'starttls',
      ssl_port: 587,
      ...clone(config.custom_smtp_server || {})
    },
    ai_type: config.ai_type || 'deepseek',
    runtime_platform: 'windows',
    adb: '127.0.0.1:16384',
    simulator: { name: 'MuMu12', index: 0 },
    maa_weekly_plan_active: '默认',
    maa_rg_sleep_min: '0:00',
    maa_rg_sleep_max: '0:00',
    start_automatically: false,
    waiting_scene: {
      CONNECTING: [1, 10],
      UNKNOWN: [1, 10],
      LOADING: [2, 30],
      LOGIN_LOADING: [3, 10],
      LOGIN_MAIN_NOENTRY: [3, 10],
      OPERATOR_ONGOING: [10, 30],
      ...clone(config.waiting_scene || {})
    },
    resource_update: { enable: false, auto_update: false }
  }
}

export function createPreviewData(config) {
  const date = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  const messages = [
    "room_1_1：读取 '能天使'、'德克萨斯'、'拉普兰德' 的当前心情",
    '宿舍恢复计划已更新，保留已安排的休息位置',
    '已收取制造站产物，下一次检查安排在 08:45:00',
    '截图识别结果需要复核，当前界面保留上一帧',
    'Scene 201: 基建总览，准备读取订单与无人机数量',
    '示例识别失败：文字区域不完整，未提交任何设备操作',
    '任务队列已更新，等待下一项计划任务',
    '预览数据已载入；日志、任务和截图均为离线示例'
  ]
  const logs = Array.from({ length: 64 }, (_, index) => {
    const level = index % 16 === 5 ? 'ERROR' : index % 8 === 3 ? 'WARNING' : 'INFO'
    const minute = String(Math.floor(index / 12)).padStart(2, '0')
    const second = String((index % 12) * 5).padStart(2, '0')
    return `${date} 08:${minute}:${second}.000 ${level} [离线预览] ${messages[index % messages.length]}`
  })
  const tasks = [
    {
      time: `${date}T08:45:00.000`,
      plan: {
        room_1_1: ['能天使', '德克萨斯', '拉普兰德'],
        dormitory_1: ['菲亚梅塔', '推进之王', null]
      },
      type: { display_value: '基建换班' }
    },
    {
      time: `${date}T09:00:00.000`,
      plan: {},
      type: { display_value: '收取订单' },
      meta_data: '贸易站 B101 · 示例'
    },
    {
      time: `${date}T09:15:00.000`,
      plan: {},
      type: { display_value: '无人机加速' },
      meta_data: '制造站 B202 · 示例'
    },
    {
      time: `${date}T09:30:00.000`,
      plan: { room_2_2: ['桃金娘', '白面鸮', '赫默'] },
      type: { display_value: '基建换班' }
    },
    {
      time: `${date}T10:00:00.000`,
      plan: {},
      type: { display_value: '技能专精' },
      meta_data: '训练室 · 示例'
    }
  ]
  return {
    config: clone(config),
    logs,
    tasks,
    status: 'running',
    plan: { conf: { ling_xi: 1 }, plan1: {}, backup_plans: [], facility_levels: {} },
    layout: { screenshot_height: 180, task_height: 132 },
    sidebar: null,
    appearance: {
      software_version_display: 'version',
      software_version_language: 'en',
      task_settings_layout: 'checklist'
    }
  }
}

function merge(target, patch) {
  for (const [key, value] of Object.entries(patch)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      target[key] = merge(target[key] && typeof target[key] === 'object' ? target[key] : {}, value)
    } else target[key] = value
  }
  return target
}

function unavailableDevicePreview() {
  return {
    kind: 'preflight',
    ok: false,
    host_platform: 'windows',
    status: 'unavailable',
    serial: '',
    observations: {},
    error: {
      code: 'preview_unavailable',
      message: '离线预览仅展示示例界面，不能连接或检测真实设备。',
      action: 'none',
      fields: []
    }
  }
}

export function createPreviewAdapter(data, requests = []) {
  const networkSettings = { http_proxy: '', github_proxy: '' }
  const softwareVersion = '4.1.6-preview'
  const softwareChannels = [
    { value: 'stable', label: '正式版', description: '跟随正式 Release，适合日常使用。' },
    { value: 'beta', label: '公测版', description: '提前体验修复和功能，可能存在不稳定行为。' },
    { value: 'dev', label: '开发版', description: '接收 Nightly 更新，可能存在不稳定行为。' }
  ]
  const softwareSettings = {
    channel: 'beta',
    background: true,
    auto_check: false,
    auto_update: false
  }
  function softwareCheck(channel) {
    return {
      ok: true,
      channel,
      version: channel === 'stable' ? softwareVersion : '4.1.7-beta.1',
      available: channel !== 'stable',
      downgrade: false,
      check_id: `preview-${channel}`,
      checked_at: Date.now() / 1000,
      message: '离线预览 · 版本检查示例，安装操作不可用。',
      notes: '此处展示示例发布说明。检查与设置修改仅保存在当前预览中。',
      url: 'https://github.com/ArkMowers/arknights-mower/releases'
    }
  }
  let softwareLastCheck = softwareCheck(softwareSettings.channel)
  const defaults = { config: clone(data.config), plan: clone(data.plan) }
  const snapshots = { 'preview-default': clone(defaults) }
  const profiles = [{ id: 'preview-default', name: '默认档案' }]
  let activeId = 'preview-default'
  let generation = '0'
  let nextId = 0
  const profileList = () => ({
    ok: true,
    active_id: activeId,
    generation,
    profiles: clone(profiles),
    groups: clone(previewGroups),
    busy: data.status === 'running'
  })
  function fail(config, message, status = 400, code = 'ERR_PREVIEW_OPERATION') {
    throw new AxiosError(message, code, config, undefined, {
      status,
      data: { ok: false, message, code: status === 409 ? 'configuration_changed' : code },
      config
    })
  }
  function selection(config, selected) {
    if (
      !Array.isArray(selected) ||
      selected.some((key) => !previewGroups.some((group) => group.key === key))
    )
      fail(config, '配置选择项目无效')
    return selected
  }
  function activate(config, id, incoming, selected) {
    selection(config, selected)
    snapshots[activeId] = { config: clone(data.config), plan: clone(data.plan) }
    const combined = {}
    for (const [index, source] of [incoming.config, data.config].entries()) {
      for (const [key, value] of Object.entries(source)) {
        if ((index === 1) === selected.includes(previewFieldGroup(key)))
          combined[key] = clone(value)
      }
    }
    data.config = combined
    data.plan = clone(selected.includes('normal_plan') ? data.plan : incoming.plan)
    activeId = id
    generation = `preview-generation-${++nextId}`
    snapshots[id] = { config: clone(data.config), plan: clone(data.plan) }
    return { ...profileList(), message: '离线示例配置已切换', recovery_path: '离线预览 · 内存示例' }
  }
  function create(config, name, incoming, selected) {
    if (typeof name !== 'string' || !name.trim() || name.trim().length > 64)
      fail(config, '请输入 1 至 64 个字符的配置名称')
    if (profiles.length >= 20) fail(config, '最多保存 20 套示例配置')
    if (profiles.some((profile) => profile.name.toLowerCase() === name.trim().toLowerCase()))
      fail(config, '已存在同名配置')
    selection(config, selected)
    const id = `preview-profile-${nextId + 1}`
    profiles.push({ id, name: name.trim() })
    return activate(config, id, incoming, selected)
  }
  return async (config) => {
    const method = (config.method || 'get').toUpperCase()
    const requestUrl = new URL(config.url, 'http://mower-preview.invalid')
    const path = requestUrl.pathname
    requests.push({ method, path })
    if (requests.length > 100) requests.shift()
    if (
      method === 'POST' &&
      ['/network/settings', '/network/test'].includes(path) &&
      (config.headers?.get?.('X-Mower-Settings') ?? config.headers?.['X-Mower-Settings']) !== '1'
    )
      fail(config, '网络设置请求缺少确认标识', 403)
    const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data
    const supplied =
      config.headers?.get?.('X-Mower-Config-Generation') ??
      config.headers?.['X-Mower-Config-Generation']
    if (
      ['POST', 'PATCH', 'PUT', 'DELETE'].includes(method) &&
      supplied !== generation &&
      !(generation === '0' && supplied == null)
    ) {
      fail(config, '当前配置已切换，请重新加载页面', 409)
    }
    let result
    const reads = {
      '/conf': () => clone(data.config),
      '/network/settings': () => ({ ok: true, ...networkSettings }),
      '/config-profiles': profileList,
      '/shop': () => ['龙门币', '招聘许可', '赤金'],
      '/item': () => ['龙门币', '赤金', '源岩'],
      // 离线示例仅提供默认预设，不读取 MAA 文件或建立连接。
      '/maa-conn-preset': () => ['General'],
      '/operator': () => [
        '能天使',
        '德克萨斯',
        '拉普兰德',
        '菲亚梅塔',
        '推进之王',
        '桃金娘',
        '白面鸮',
        '赫默'
      ],
      '/status': () => ({
        status: data.status,
        deployment: 'release',
        auto_start_handled: true,
        desktop_startup_handled: true,
        ai_assistant_enabled: false,
        updates_enabled: true,
        plan_condition: []
      }),
      '/software-update/info': () => ({
        ok: true,
        version: softwareVersion,
        deployment: 'release',
        platform: 'win32',
        channels: clone(softwareChannels),
        settings: clone(softwareSettings),
        last_check: clone(softwareLastCheck),
        blockers: [],
        instances: [{ name: '离线预览', running: true }],
        force_supported: false,
        manual_supported: true,
        manual_ota_supported: true,
        rollback_supported: false,
        component_updates: [],
        releases_url: 'https://github.com/ArkMowers/arknights-mower/releases'
      }),
      '/software-update/status': () => ({
        ok: true,
        status: 'idle',
        last_check: clone(softwareLastCheck)
      }),
      '/device/status': () => ({
        host_platform: 'windows',
        active: data.status === 'running',
        status: data.status === 'running' ? 'running' : 'closed',
        serial: '',
        readiness: null,
        preparation: null,
        error: null,
        preflight: unavailableDevicePreview(),
        managed_instance_presets: []
      }),
      '/device/performance-test': () => ({
        status: 'idle',
        id: null,
        message: '离线预览仅展示性能测试状态，不能连接设备或执行测试。'
      }),
      '/task': () => (data.status === 'running' ? clone(data.tasks) : []),
      '/plan': () => clone(data.plan),
      '/rescue-plan': () => clone(data.plan),
      '/weekly-plans': () => ({
        plans: ['默认'],
        active: '默认',
        inventory_config: { enabled: false, limit_rules: [], ratio_rules: [] }
      }),
      '/getwatermark': () => '离线预览 · 示例数据',
      '/resource-version': () => {
        const local = String(config.params?.local ?? requestUrl.searchParams.get('local')) === '1'
        return {
          current_version: 'v2026.10.17',
          current_display: '资源预览 · 当前',
          ...(local
            ? {}
            : {
                remote_version: 'v2026.10.20',
                remote_display: '资源预览 · 可更新',
                update_available: true
              })
        }
      },
      '/resource/status': () => ({ ok: true, job: { status: 'idle' } }),
      '/update-notice': () => ({ should_show: false }),
      '/crash-recovery/status': () => ({ active: false }),
      '/process-control/info': () => ({
        ok: true,
        supported: true,
        running: data.status === 'running',
        name: '离线预览',
        message: '离线预览仅展示当前实例状态与操作确认，不能重启或结束真实进程。'
      }),
      '/ui-state/log-layout': () => clone(data.layout),
      '/gui/sidebar': () => ({ sidebar: clone(data.sidebar) }),
      '/gui/appearance': () => clone(data.appearance),
      '/db-admin/stats': () => ({ log: 64, task: 5 }),
      '/screenshot/latest': () => new Blob([screenshot], { type: 'image/svg+xml' })
    }
    if (path.startsWith('/config-profiles') && method !== 'GET' && data.status === 'running')
      fail(config, '请先停止 Mower 后操作示例配置', 423)
    if (method === 'GET' && reads[path]) result = reads[path]()
    else if (method === 'GET' && path === '/config-profiles/export') {
      const writer = new ZipWriter(new BlobWriter('application/zip'), {
        useWebWorkers: false,
        level: 0
      })
      await writer.add('config/conf.yml', new TextReader(JSON.stringify(data.config)))
      await writer.add('config/plan.json', new TextReader(JSON.stringify(data.plan)))
      result = await writer.close()
    } else if (method === 'POST' && path === '/config-profiles')
      result = create(config, body?.name, defaults, body?.inherit || [])
    else if (method === 'POST' && path === '/config-profiles/import') {
      const file = body?.get?.('backup')
      if (!(file instanceof Blob) || file.size > 16 * 1024 * 1024)
        fail(config, '请选择小于 16 MB 的离线预览 ZIP')
      let imported, selected
      const reader = new ZipReader(new BlobReader(file), { useWebWorkers: false })
      try {
        const entries = await reader.getEntries()
        if (entries.length > 1024) throw new Error('too many entries')
        const texts = {}
        for (const entry of entries) {
          if (['config/conf.yml', 'config/plan.json'].includes(entry.filename)) {
            if (entry.uncompressedSize > 16 * 1024 * 1024) throw new Error('oversized entry')
            texts[entry.filename] = await entry.getData(new TextWriter())
          }
        }
        imported = {
          config: JSON.parse(texts['config/conf.yml']),
          plan: JSON.parse(texts['config/plan.json'])
        }
        selected = JSON.parse(body.get('keep') || '[]')
        if (!imported.config || !imported.plan) throw new Error('missing preview configuration')
      } catch {
        fail(config, '离线预览仅支持导入本预览导出的 ZIP；真实配置请在 Mower 中导入')
      } finally {
        await reader.close()
      }
      result = create(config, body.get('name'), imported, selected)
    } else if (method === 'POST' && /^\/config-profiles\/[^/]+\/activate$/.test(path)) {
      const id = path.split('/')[2]
      if (!snapshots[id]) fail(config, '找不到所选示例配置')
      result = activate(config, id, snapshots[id], body?.keep || [])
    } else if (method === 'PATCH' && /^\/config-profiles\/[^/]+$/.test(path)) {
      const profile = profiles.find((item) => item.id === path.split('/')[2])
      if (!profile) fail(config, '找不到所选示例配置')
      if (typeof body?.name !== 'string' || !body.name.trim() || body.name.trim().length > 64)
        fail(config, '请输入 1 至 64 个字符的配置名称')
      if (
        profiles.some(
          (item) => item !== profile && item.name.toLowerCase() === body.name.trim().toLowerCase()
        )
      )
        fail(config, '已存在同名配置')
      profile.name = body.name.trim()
      result = profileList()
    } else if (method === 'POST' && path === '/device/preflight')
      result = unavailableDevicePreview()
    else if (method === 'PATCH' && path === '/conf') result = clone(merge(data.config, body))
    else if (method === 'POST' && path === '/plan') result = { ok: true }
    else if (method === 'POST' && path === '/ui-state/log-layout')
      result = clone(merge(data.layout, body))
    else if (method === 'PUT' && path === '/gui/sidebar') {
      data.sidebar = clone(body.sidebar)
      result = { sidebar: clone(data.sidebar) }
    } else if (method === 'PUT' && path === '/gui/appearance') {
      const choices = {
        software_version_display: ['version', 'channel'],
        software_version_language: ['zh', 'en'],
        task_settings_layout: ['checklist', 'waterfall']
      }
      if (
        !body ||
        typeof body !== 'object' ||
        Array.isArray(body) ||
        Object.keys(body).length === 0 ||
        Object.entries(body).some(
          ([key, value]) => !Object.hasOwn(choices, key) || !choices[key].includes(value)
        )
      )
        fail(config, '外观配置无效')
      Object.assign(data.appearance, clone(body))
      result = clone(body)
    } else if (method === 'POST' && path === '/network/settings') {
      if (!body || typeof body.http_proxy !== 'string' || typeof body.github_proxy !== 'string')
        fail(config, '请提供完整的网络代理设置')
      networkSettings.http_proxy = body.http_proxy.trim().replace(/\/+$/, '')
      const githubProxy = body.github_proxy.trim().replace(/\/+$/, '')
      networkSettings.github_proxy = githubProxy ? `${githubProxy}/` : ''
      result = { ok: true, ...networkSettings }
    } else if (method === 'POST' && path === '/network/test') {
      result = {
        ok: true,
        settings: clone(networkSettings),
        results: [
          {
            label: 'GitHub 文件下载',
            ok: true,
            message: '离线预览 · 仅展示连接测试示例结果，未连接外网。',
            elapsed_ms: 128
          }
        ]
      }
    } else if (method === 'POST' && path === '/software-update/settings') {
      if (!body || typeof body !== 'object') fail(config, '请提供软件更新设置')
      if (
        body.channel !== undefined &&
        !softwareChannels.some((channel) => channel.value === body.channel)
      )
        fail(config, '未知更新渠道')
      for (const key of ['background', 'auto_check', 'auto_update']) {
        if (body[key] !== undefined && typeof body[key] !== 'boolean')
          fail(config, '更新开关必须是布尔值')
      }
      for (const key of Object.keys(softwareSettings)) {
        if (body[key] !== undefined) softwareSettings[key] = body[key]
      }
      if (softwareSettings.auto_update) softwareSettings.auto_check = true
      result = { ok: true, settings: clone(softwareSettings) }
    } else if (method === 'POST' && path === '/software-update/check') {
      if (!softwareChannels.some((channel) => channel.value === body?.channel))
        fail(config, '未知更新渠道')
      softwareLastCheck = softwareCheck(body.channel)
      result = clone(softwareLastCheck)
    } else if (method === 'POST' && path === '/software-update/auto-check') {
      if (softwareSettings.auto_check) softwareLastCheck = softwareCheck(softwareSettings.channel)
      result = { ok: true, update_available: softwareLastCheck.available }
    } else {
      const response = {
        status: 405,
        data: { message: `离线预览未提供此操作：${method} ${path}` },
        config
      }
      throw new AxiosError(
        response.data.message,
        'ERR_PREVIEW_OPERATION',
        config,
        undefined,
        response
      )
    }
    return { status: 200, statusText: 'OK', data: result, headers: {}, config }
  }
}

export function previewWebSocket(logs) {
  return class PreviewWebSocket extends EventTarget {
    static CONNECTING = 0
    static OPEN = 1
    static CLOSING = 2
    static CLOSED = 3
    constructor(url) {
      super()
      this.url = url
      this.readyState = 0
      this.protocol = ''
      this.timer = setTimeout(() => {
        this.readyState = 1
        const open = new Event('open')
        this.dispatchEvent(open)
        this.onopen?.(open)
        if (new URL(url, 'ws://mower-preview.invalid').pathname === '/log') {
          const message = new MessageEvent('message', {
            data: JSON.stringify({ type: 'log', data: logs.join('\n') })
          })
          this.dispatchEvent(message)
          this.onmessage?.(message)
        }
      }, 10)
    }
    send() {}
    close() {
      clearTimeout(this.timer)
      this.readyState = 3
      const event = new Event('close')
      this.dispatchEvent(event)
      this.onclose?.(event)
    }
  }
}

export function installPreviewBackend(config, target = window) {
  const data = createPreviewData(config)
  const requests = []
  axios.defaults.adapter = createPreviewAdapter(data, requests)
  target.WebSocket = previewWebSocket(data.logs)
  target.fetch = async () => {
    throw new Error('离线预览已停用网络请求')
  }
  target.XMLHttpRequest = class {
    open() {
      throw new Error('离线预览已停用网络请求')
    }
  }
  const state = {
    protocol: 'mower-window-shell-v1',
    state: 'normal',
    maximized: false,
    minimized: false,
    width: target.innerWidth,
    height: target.innerHeight
  }
  const updateState = (maximized) => {
    Object.assign(state, { state: maximized ? 'maximized' : 'normal', maximized })
    target.dispatchEvent(new CustomEvent('mower-window-state', { detail: { ...state } }))
    return true
  }
  const closePreference = {
    choice: 'tray',
    remember: false,
    tray_enabled: config.webview?.tray !== false
  }
  let launchMode = 'last'
  const previewBridge = {
    api: {
      get_platform: async () => ({
        protocol: state.protocol,
        platform: 'windows',
        event: 'mower-window-state'
      }),
      get_window_state: async () => ({ ...state }),
      get_close_preference: async () => ({ ...closePreference }),
      set_close_preference: async (choice, remember) => {
        if (!['tray', 'exit'].includes(choice) || typeof remember !== 'boolean')
          throw new Error('关闭窗口设置无效')
        if (choice === 'tray' && !closePreference.tray_enabled) throw new Error('托盘图标未启用')
        Object.assign(closePreference, { choice, remember })
        return true
      },
      get_window_launch_mode: async () => launchMode,
      set_window_launch_mode: async (mode) => {
        if (!['last', 'normal', 'maximized'].includes(mode)) throw new Error('窗口启动状态设置无效')
        launchMode = mode
        return true
      },
      minimize: async () => true,
      maximize: async () => updateState(true),
      restore: async () => updateState(false),
      close: async () => true,
      start_resize: async () => true,
      start_move: async () => true,
      mark_ready: async () => true
    }
  }
  const nativePreview =
    new URLSearchParams(target.location?.search || '').get('native_preview') === '1'
  if (!nativePreview && !target.pywebview?.api) target.pywebview = previewBridge
  target.__MOWER_PREVIEW__ = { data, requests }
  return data
}
