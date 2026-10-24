import { configPatch } from './configPatch'

// DeviceProfile contains only scalar fields; key order has no identity meaning.
export function sameDeviceProfile(left, right) {
  const keys = Object.keys(left)
  return (
    keys.length === Object.keys(right).length &&
    keys.every((key) => Object.hasOwn(right, key) && left[key] === right[key])
  )
}

const presetLabels = {
  'windows.mumu12': 'MuMu 12',
  'windows.ldplayer9': '雷电模拟器 9',
  'windows.ldplayer14': '雷电模拟器 14',
  'windows.nox': '夜神模拟器',
  'windows.bluestacks5': 'BlueStacks 5',
  'macos.bluestacks_air': 'BlueStacks Air',
  'macos.avd': 'Android Virtual Device',
  'macos.mumu_pro': 'MuMu Pro',
  'linux.waydroid': 'Waydroid',
  'linux.avd': 'Android Virtual Device',
  'linux.redroid': 'redroid',
  'linux.genymotion': 'Genymotion',
  'manual.other': '其他模拟器',
  'manual.physical': '实体设备'
}

// Fallback for a backend that does not report its managed preset set yet. The
// backend list in /device/status is authoritative when it is present.
const managedStartPresets = [
  'windows.mumu12',
  'windows.ldplayer9',
  'windows.ldplayer14',
  'windows.nox',
  'macos.mumu_pro',
  'linux.waydroid'
]

// Settings that never change which device mower targets, so they are written
// straight away instead of waiting for a verified connection. Anything that
// identifies the device (preset, paths, instance, endpoint, game server) stays
// behind the detection gate.
const immediateDeviceFields = new Set([
  'screenshot_backend',
  'touch_backend',
  'recovery_timeout',
  'recovery_attempts',
  'recovery_local_wait',
  'recovery_shutdown_wait',
  'manager_query_timeout',
  'simulator_hotkey',
  'simulator_hotkey_delay'
])

// Screenshot and touch backends never change which device mower targets, so they
// are edited and saved outside the device-identity form: they keep their own
// always-visible group instead of hiding behind the advanced toggle.
const connectionBackendKeys = ['screenshot_backend', 'touch_backend']

const nativeCapturePresets = {
  mumu_ipc: ['windows.mumu12'],
  ld_native: ['windows.ldplayer9', 'windows.ldplayer14']
}

function capturePresetReason(backend, preset, host) {
  const required = nativeCapturePresets[backend]
  if (!required || (required.includes(preset) && (!host || host === 'windows'))) return ''
  return backend === 'mumu_ipc'
    ? '仅适用于 Windows 的 MuMu 12'
    : '仅适用于 Windows 的雷电模拟器 9 或 14'
}

export function isImmediateDeviceField(key) {
  return immediateDeviceFields.has(key)
}

// The keys one edit actually changed, including a coupled backend. Unsaved
// identity edits elsewhere in the draft stay out of it.
export function editedDevicePatch(profile, key, value) {
  const next = editDeviceDraft(profile, key, value)
  const patch = {}
  for (const [field, nextValue] of Object.entries(next)) {
    if (JSON.stringify(nextValue) !== JSON.stringify(profile[field])) patch[field] = nextValue
  }
  return patch
}

export function editDeviceDraft(profile, key, value) {
  const draft = { ...profile, [key]: value }
  if (profile[key] === value) return draft
  if (
    ['preset_id', 'installation_path', 'manager_path', 'config_path', 'instance_id'].includes(key)
  ) {
    draft.last_serial = ''
    draft.instance_name = ''
    draft.instance_uuid = ''
    draft.topology_fingerprint = ''
    draft.game_package_confirmed = false
  }
  if (['preset_id', 'installation_path', 'manager_path'].includes(key)) draft.config_path = ''
  if (key === 'last_serial') draft.game_package_confirmed = false
  if (key === 'screenshot_backend') {
    if (value === 'mumu_ipc') draft.touch_backend = 'mumu_ipc'
    else if (profile.touch_backend === 'mumu_ipc') draft.touch_backend = 'scrcpy'
  }
  if (key === 'touch_backend') {
    if (value === 'mumu_ipc') draft.screenshot_backend = 'mumu_ipc'
    else if (profile.screenshot_backend === 'mumu_ipc') draft.screenshot_backend = 'droidcast'
  }
  if (key === 'preset_id' && capturePresetReason(draft.screenshot_backend, value)) {
    draft.screenshot_backend = 'droidcast'
    if (draft.touch_backend === 'mumu_ipc') draft.touch_backend = 'scrcpy'
  }
  return draft
}

export function manualDeviceDraft(profile, preset) {
  const backends = nativeCapturePresets[profile.screenshot_backend]
    ? {
        screenshot_backend: 'droidcast',
        touch_backend: profile.touch_backend === 'mumu_ipc' ? 'scrcpy' : profile.touch_backend
      }
    : {}
  return {
    ...profile,
    ...backends,
    preset_id: preset,
    installation_path: '',
    manager_path: '',
    config_path: '',
    instance_id: '',
    instance_name: '',
    instance_uuid: '',
    topology_fingerprint: '',
    last_serial: '',
    game_package_confirmed: false
  }
}

export function devicePreflightRequest(profile, draft, confirmedPackage = null) {
  return {
    device: {
      ...configPatch(profile, draft),
      // A reselected Air or manual endpoint may equal the previous binding's serial.
      // Preserve that explicit target through the backend's binding reset.
      ...(draft.preset_id === 'macos.bluestacks_air' ||
      draft.preset_id === 'macos.mumu_pro' ||
      draft.preset_id?.startsWith('manual.')
        ? { last_serial: draft.last_serial ?? '' }
        : {})
    },
    ...(confirmedPackage ? { confirmed_package: confirmedPackage } : {})
  }
}

export function deviceAvdStartRequest(profile, draft, confirmedInstance, confirmedPackage = null) {
  if (
    !['macos.avd', 'linux.avd'].includes(draft.preset_id) ||
    !confirmedInstance ||
    confirmedInstance === '-1' ||
    !/^[A-Za-z0-9_.-]+$/.test(confirmedInstance) ||
    draft.instance_id !== confirmedInstance
  ) {
    throw new Error('AVD 目标已变化，请重新确认要启动的实例。')
  }
  return {
    ...devicePreflightRequest(profile, draft, confirmedPackage),
    confirmed_instance: confirmedInstance
  }
}

export function deviceRedroidStartRequest(
  profile,
  draft,
  confirmedInstance,
  confirmedPackage = null
) {
  if (
    draft.preset_id !== 'linux.redroid' ||
    !/^[a-f0-9]{64}$/.test(confirmedInstance || '') ||
    draft.instance_id !== confirmedInstance ||
    draft.config_path !== 'unix:///var/run/docker.sock'
  ) {
    throw new Error('redroid 目标已变化，请重新确认要启动的容器。')
  }
  return {
    ...devicePreflightRequest(profile, draft, confirmedPackage),
    confirmed_instance: confirmedInstance
  }
}

export function deviceGenymotionStartRequest(
  profile,
  draft,
  confirmedInstance,
  confirmedPackage = null
) {
  if (
    draft.preset_id !== 'linux.genymotion' ||
    !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(confirmedInstance || '') ||
    draft.instance_id !== confirmedInstance ||
    !draft.manager_path?.trim()
  ) {
    throw new Error('Genymotion 目标已变化，请重新确认要启动的 VM。')
  }
  return {
    ...devicePreflightRequest(profile, draft, confirmedPackage),
    confirmed_instance: confirmedInstance
  }
}

export function deviceStartupRequest(profile, draft, metadata = {}, confirmedPackage = null) {
  if (!deviceSettingsState({ profile: draft, metadata }).actions.startBound.visible) {
    throw new Error('当前目标不支持启动，请先检测并选择支持启动的实例。')
  }
  const product = {
    'macos.avd': ['avd', deviceAvdStartRequest],
    'linux.avd': ['avd', deviceAvdStartRequest],
    'linux.redroid': ['redroid', deviceRedroidStartRequest],
    'linux.genymotion': ['genymotion', deviceGenymotionStartRequest]
  }[draft.preset_id]
  return product
    ? {
        endpoint: `${product[0]}/start`,
        payload: product[1](profile, draft, draft.instance_id, confirmedPackage)
      }
    : { endpoint: 'start', payload: devicePreflightRequest(profile, draft, confirmedPackage) }
}

export const buildGenymotionStartRequest = deviceGenymotionStartRequest

export function deviceDetectionDraft(profile, result) {
  if (result?.preset_id === 'macos.bluestacks_air' && profile.preset_id !== result.preset_id) {
    return {
      ...editDeviceDraft(profile, 'preset_id', result.preset_id),
      installation_path: '',
      manager_path: '',
      instance_id: ''
    }
  }
  return result?.preset_id
    ? editDeviceDraft(profile, 'preset_id', result.preset_id)
    : { ...profile }
}

export function deviceSuccessPatch(profile, draft, result) {
  if (!result?.ok) return {}
  return {
    device: configPatch(profile, {
      ...draft,
      ...result.profile_patch,
      ...(result.adb_path ? { adb_path: result.adb_path } : {}),
      last_serial: result.serial,
      game_package: result.game_package,
      game_package_confirmed: true
    })
  }
}

export async function savePreflightDevice({ config, profile, result }) {
  if (!result?.ok) return { ...profile }
  const verified = { ...profile, ...deviceSuccessPatch(profile, profile, result).device }
  return saveDeviceBinding(config, verified, {
    serial: result.serial,
    game_package: result.game_package
  })
}

async function saveDeviceBinding(config, profile, confirmation = null) {
  await config.flush_config_saves()
  let previous = { ...config.device_profile }
  try {
    if (
      [
        'preset_id',
        'installation_path',
        'manager_path',
        'config_path',
        'instance_id',
        'instance_uuid',
        'topology_fingerprint'
      ].some((key) => previous[key] !== profile[key])
    ) {
      // Conf clears an unchanged endpoint when its binding changes. Save the
      // identity first, then the verified or explicitly authorized endpoint.
      config.device_profile = { ...profile, last_serial: '', game_package_confirmed: false }
      await config.save_config()
      previous = { ...config.device_profile }
    }
    config.device_profile = profile
    await config.save_config(confirmation)
  } catch (error) {
    config.device_profile = previous
    throw error
  }
  return { ...config.device_profile }
}

export async function saveDiscoveredDevice({ config, profile, result, key }) {
  const candidate =
    result?.kind === 'discovery' && result.candidates?.find((item) => item.key === key)
  if (!candidate?.binding) throw new Error('请选择有效实例。')
  await config.flush_config_saves()
  const previous = { ...config.device_profile }
  config.device_profile = {
    ...editDeviceDraft(profile, 'preset_id', candidate.binding.preset_id || profile.preset_id),
    config_path: '',
    instance_uuid: '',
    topology_fingerprint: '',
    ...candidate.binding,
    last_serial: '',
    game_package_confirmed: false
  }
  try {
    await config.save_config()
  } catch (error) {
    config.device_profile = previous
    throw error
  }
  return { ...config.device_profile }
}

export function deviceStatusResult(current, previous, incoming, protectedDraft = false) {
  if (protectedDraft || JSON.stringify(previous) === JSON.stringify(incoming)) return current
  return incoming || null
}

export async function startPhysicalPreparation({
  axios,
  config,
  profile,
  serial,
  confirmedPackage = null,
  base = ''
}) {
  if (
    profile.preset_id !== 'manual.physical' ||
    !serial?.trim() ||
    profile.last_serial !== serial
  ) {
    throw new Error('设备目标已变化，请重新确认实体设备 serial。')
  }
  await saveDeviceBinding(
    config,
    {
      ...profile,
      ...(confirmedPackage ? { game_package: confirmedPackage, game_package_confirmed: true } : {})
    },
    confirmedPackage ? { serial, game_package: confirmedPackage } : null
  )
  await config.flush_config_saves()
  if (
    config.device_profile.preset_id !== 'manual.physical' ||
    config.device_profile.last_serial !== serial
  ) {
    throw new Error('设备目标已变化，请重新确认实体设备 serial。')
  }
  const response = await axios.post(`${base}/start/0`, { preparation_serial: serial })
  if (response.data !== true && response.data !== 'true') {
    throw new Error('当前无法启动，请先停止正在运行的任务或等待维护结束。')
  }
}

const fieldLabels = {
  preset_id: '模拟器',
  installation_path: '安装目录',
  manager_path: '管理程序路径',
  config_path: '产品配置路径',
  adb_path: 'ADB 路径',
  instance_id: '多开实例序号',
  instance_name: '多开实例名称',
  last_serial: '连接地址',
  screenshot_backend: '截图后端',
  touch_backend: '触控后端',
  game_package: '游戏服务器'
}

const presetPlaceholders = {
  'windows.mumu12': {
    installation_path: '例如：D:\\MuMuPlayer-12.0',
    manager_path: '例如：D:\\MuMuPlayer-12.0\\nx_main\\MuMuManager.exe',
    adb_path: '例如：D:\\MuMuPlayer-12.0\\shell\\adb.exe',
    instance_id: '0',
    instance_name: '选填',
    last_serial: '例如：127.0.0.1:16384'
  },
  'windows.ldplayer9': {
    installation_path: '例如：C:\\leidian\\LDPlayer9',
    manager_path: '例如：C:\\leidian\\LDPlayer9\\dnconsole.exe',
    adb_path: '例如：C:\\leidian\\LDPlayer9\\adb.exe',
    instance_id: '0',
    instance_name: '选填',
    last_serial: '例如：127.0.0.1:5555'
  },
  'windows.ldplayer14': {
    installation_path: '例如：C:\\leidian\\LDPlayer14',
    manager_path: '例如：C:\\leidian\\LDPlayer14\\dnconsole.exe',
    adb_path: '例如：C:\\leidian\\LDPlayer14\\adb.exe',
    instance_id: '0',
    instance_name: '选填',
    last_serial: '例如：127.0.0.1:5555'
  },
  'windows.nox': {
    installation_path: '例如：C:\\Program Files\\Nox\\bin',
    manager_path: '例如：C:\\Program Files\\Nox\\bin\\Nox.exe',
    adb_path: '例如：C:\\Program Files\\Nox\\bin\\nox_adb.exe',
    instance_id: '0',
    instance_name: '选填',
    last_serial: '例如：127.0.0.1:62001'
  },
  'windows.bluestacks5': {
    installation_path: '例如：C:\\Program Files\\BlueStacks_nxt',
    manager_path: '例如：C:\\Program Files\\BlueStacks_nxt\\HD-Player.exe',
    config_path: '例如：C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf',
    adb_path: '例如：C:\\Program Files\\BlueStacks_nxt\\HD-Adb.exe',
    instance_id: 'Pie64',
    instance_name: '选填',
    last_serial: '例如：127.0.0.1:5555'
  },
  'macos.mumu_pro': {
    installation_path: '例如：/Applications/MuMuPlayer.app',
    manager_path: '例如：/Applications/MuMuPlayer.app/Contents/MacOS/mumutool',
    adb_path: '例如：/Applications/MuMuPlayer.app/Contents/MacOS/adb',
    instance_id: '0',
    instance_name: '选填',
    last_serial: '例如：127.0.0.1:16384'
  },
  'macos.bluestacks_air': {
    installation_path: '例如：/Applications/BlueStacks.app',
    adb_path: '例如：adb',
    last_serial: '例如：127.0.0.1:5555'
  },
  'linux.waydroid': {
    installation_path: '例如：/var/lib/waydroid',
    manager_path: '例如：waydroid',
    config_path: '例如：/var/lib/waydroid',
    adb_path: '例如：adb',
    last_serial: '例如：192.168.240.112:5555'
  },
  'linux.redroid': {
    installation_path: '例如：docker',
    manager_path: '例如：docker',
    config_path: '例如：unix:///var/run/docker.sock',
    instance_id: '例如：redroid1',
    adb_path: '例如：adb',
    last_serial: '例如：127.0.0.1:5555'
  },
  'linux.genymotion': {
    installation_path: '例如：/opt/genymobile/genymotion',
    manager_path: '例如：/opt/genymobile/genymotion/gmtool',
    instance_id: '例如：0',
    adb_path: '例如：adb',
    last_serial: '例如：192.168.56.101:5555'
  },
  'macos.avd': {
    installation_path: '例如：/Users/username/Library/Android/sdk',
    manager_path: '例如：emulator',
    instance_id: '例如：Pixel_6_API_33',
    adb_path: '例如：adb',
    last_serial: '例如：emulator-5554'
  },
  'linux.avd': {
    installation_path: '例如：/home/username/Android/Sdk',
    manager_path: '例如：emulator',
    instance_id: '例如：Pixel_6_API_33',
    adb_path: '例如：adb',
    last_serial: '例如：emulator-5554'
  },
  default: {
    installation_path: '请输入模拟器安装根目录',
    manager_path: '请输入模拟器管理程序完整路径',
    config_path: '请输入产品配置文件路径',
    adb_path: '请输入 adb.exe 所在路径',
    instance_id: '0',
    instance_name: '选填',
    last_serial: '例如：127.0.0.1:5555'
  }
}

const fieldHelpTexts = {
  installation_path:
    '模拟器的安装根目录。Mower 会在此目录下定位模拟器核心程序、多开管理工具及内置 ADB。检测到的路径会自动填写；也可指定管理程序路径。',
  manager_path:
    '模拟器的多开管理控制程序（如 MuMuManager.exe、dnconsole.exe）。用于查询多开列表、控制启动与关停。',
  config_path:
    '模拟器的全局配置文件路径（如 BlueStacks 的 bluestacks.conf），用于自动解析多开实例与端口分配。',
  adb_path:
    '用于与模拟器通信的 ADB 调试工具路径。默认填写 Mower 自带的 ADB，可手动指定其他路径。留空时会自动优先探测模拟器自带的 ADB。选填。',
  instance_id:
    '所选实例的编号或标识，格式由模拟器决定。建议通过“检测实例”选择；MuMu Pro 和夜神的身份核验信息也由检测提供，不能仅填写序号启停。',
  instance_name: '多开实例的自定义名称（仅用于界面展示与日志标识）。选填。',
  last_serial:
    '模拟器的 ADB 调试连接地址与端口号（如 127.0.0.1:16384 或 127.0.0.1:5555）。通常可在模拟器多开器或设置中查看。已绑定实例会核验并读取当前端口；手动连接模式需填写。',
  screenshot_backend:
    '用于捕获游戏画面的方式。MuMu 截图增强适用于 Windows MuMu 12，LD 截图增强适用于 Windows 雷电 9 和 14。LD 可搭配 scrcpy 或 MaaTouch 触控。',
  touch_backend: '用于向模拟器发送点击与滑动指令的方式。可选 scrcpy、MaaTouch 或 MuMu 自带触控。',
  game_package: '明日方舟游戏客户端服务器类型（官服或 Bilibili 服）。'
}

const backendOptions = {
  screenshot_backend: [
    { label: 'ADB gzip', value: 'adb_gzip' },
    { label: 'DroidCast', value: 'droidcast' },
    { label: 'MuMu 截图增强', value: 'mumu_ipc' },
    { label: 'LD 截图增强', value: 'ld_native' },
    { label: '自定义命令', value: 'custom' }
  ],
  touch_backend: [
    { label: 'scrcpy 1.21', value: 'scrcpy' },
    { label: 'MaaTouch', value: 'maatouch' },
    { label: 'MuMu 自带触控', value: 'mumu_ipc' }
  ]
}

export function deviceSettingsState({
  profile = {},
  metadata = {},
  result = null,
  busy = false,
  advanced = false,
  manual = false,
  selectedKey = null,
  confirmedPackage = null
}) {
  const locked = busy || metadata.active === true
  const air = profile.preset_id === 'macos.bluestacks_air'
  const waydroid = profile.preset_id === 'linux.waydroid'
  const boundWaydroid =
    waydroid &&
    /^waydroid:\d+$/.test(profile.instance_id || '') &&
    Boolean(
      profile.manager_path?.trim() &&
      profile.installation_path?.trim() &&
      profile.config_path?.trim()
    )
  const mumuPro = profile.preset_id === 'macos.mumu_pro'
  const boundMumuPro =
    mumuPro &&
    (Boolean(profile.last_serial?.trim()) ||
      (Boolean(profile.topology_fingerprint?.trim()) && /^\d+$/.test(profile.instance_id || '')))
  const avd = ['macos.avd', 'linux.avd'].includes(profile.preset_id)
  const genymotion = profile.preset_id === 'linux.genymotion'
  const boundGenymotion =
    genymotion &&
    /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(profile.instance_id || '') &&
    Boolean(profile.manager_path?.trim())
  const redroid = profile.preset_id === 'linux.redroid'
  const boundRedroid =
    redroid &&
    /^[a-f0-9]{64}$/.test(profile.instance_id || '') &&
    profile.config_path === 'unix:///var/run/docker.sock' &&
    Boolean(profile.manager_path?.trim() && profile.installation_path?.trim())
  const boundAvd =
    avd &&
    profile.instance_id !== '-1' &&
    /^[A-Za-z0-9_.-]+$/.test(profile.instance_id || '') &&
    Boolean(profile.installation_path?.trim() || profile.manager_path?.trim())
  const discovery = result?.kind === 'discovery'
  const instances = discovery
    ? {
        value: selectedKey || result.selected_key || null,
        disabled: locked,
        options: (result.candidates || []).map((candidate) => ({
          value: candidate.key,
          label: [
            presetLabels[candidate.preset_id],
            candidate.instance_name,
            candidate.preset_id === 'linux.genymotion'
              ? candidate.instance_id
              : candidate.preset_id === 'macos.mumu_pro'
                ? `实例 ${candidate.instance_id}`
                : '',
            { running: '运行中', starting: '启动中', stopped: '已停止', error: '操作失败' }[
              candidate.state
            ],
            candidate.preset_id === 'macos.mumu_pro'
              ? candidate.serial
              : candidate.installation_path
          ]
            .filter(Boolean)
            .join(' · ')
        }))
      }
    : null
  const host = metadata.host_platform || result?.host_platform
  const presetPrefix = {
    win32: 'windows',
    windows: 'windows',
    darwin: 'macos',
    macos: 'macos',
    linux: 'linux'
  }[host]
  const boundInstance =
    ((['windows.mumu12', 'windows.ldplayer9', 'windows.ldplayer14'].includes(profile.preset_id) &&
      /^\d+$/.test(profile.instance_id)) ||
      (profile.preset_id === 'windows.nox' &&
        /^[A-Za-z][A-Za-z0-9_-]*$/.test(profile.instance_id) &&
        Boolean(profile.instance_uuid?.trim() && profile.topology_fingerprint?.trim())) ||
      (profile.preset_id === 'windows.bluestacks5' &&
        /^[A-Za-z][A-Za-z0-9_]*$/.test(profile.instance_id) &&
        Boolean(profile.config_path?.trim()))) &&
    Boolean(profile.installation_path?.trim() || profile.manager_path?.trim())
  const managedPresets = Array.isArray(metadata.managed_instance_presets)
    ? metadata.managed_instance_presets
    : managedStartPresets
  const verifiedMumuPro =
    mumuPro &&
    Boolean(profile.topology_fingerprint?.trim()) &&
    /^(0|[1-9][0-9]*)$/.test(profile.instance_id || '')
  const managedStart =
    (managedPresets.includes(profile.preset_id) &&
      ((presetPrefix === 'windows' && boundInstance) ||
        (presetPrefix === 'macos' && verifiedMumuPro) ||
        (presetPrefix === 'linux' && boundWaydroid))) ||
    (avd && boundAvd && profile.preset_id === `${presetPrefix}.avd`) ||
    (presetPrefix === 'linux' && ((redroid && boundRedroid) || (genymotion && boundGenymotion)))
  const manualTarget = profile.preset_id?.startsWith('manual.') && Boolean(profile.last_serial)
  const discover =
    !manual &&
    !manualTarget &&
    ((presetPrefix === 'windows' && !boundInstance) ||
      (['macos', 'linux'].includes(presetPrefix) &&
        (!profile.preset_id ||
          profile.preset_id === 'manual.other' ||
          (avd && !boundAvd) ||
          (genymotion && !boundGenymotion) ||
          (redroid && !boundRedroid) ||
          (waydroid && !boundWaydroid) ||
          (mumuPro && !boundMumuPro))))
  const presets = Object.entries(presetLabels)
    .filter(([value]) => value.startsWith('manual.') || value.startsWith(`${presetPrefix}.`))
    .map(([value, label]) => ({ value, label }))
  const touchCapabilities =
    metadata.touch_backend_profile === profile.preset_id ? metadata.touch_backends || [] : []
  const touchOptions = backendOptions.touch_backend.map((option) => {
    const capability = touchCapabilities.find((item) => item.backend === option.value)
    const presetReason =
      option.value === 'mumu_ipc'
        ? capturePresetReason('mumu_ipc', profile.preset_id, host ? presetPrefix : undefined)
        : ''
    const reason =
      capability?.available === false
        ? capability.reason || '当前环境不支持此触控后端。'
        : presetReason
    return {
      ...option,
      label: reason ? `${option.label}（${reason}）` : option.label,
      disabled: Boolean(reason),
      reason
    }
  })
  const screenshotOptions = backendOptions.screenshot_backend.map((option) => {
    const reason = capturePresetReason(
      option.value,
      profile.preset_id,
      host ? presetPrefix : undefined
    )
    return {
      ...option,
      label: reason ? `${option.label}（${reason}）` : option.label,
      disabled: Boolean(reason),
      reason
    }
  })
  const candidates = (discovery ? [] : result?.candidates || []).map(({ serial, state }) => ({
    value: serial,
    label: `${serial} · ${state}`
  }))
  const packages = (result?.packages || []).map((value) => ({
    value,
    label: value === 'com.hypergryph.arknights' ? '官服' : 'Bilibili 服'
  }))
  const screenshotFailureCodes = ['frame_failed', 'frame_size_mismatch', 'screenshot_failed']
  const touchFailureCodes = ['touch_initialization_failed', 'touch_result_unknown']
  const runtimeBackendError = [...screenshotFailureCodes, ...touchFailureCodes].includes(
    metadata.error?.code
  )
    ? metadata.error
    : null
  const errors = [result?.error, ...(result?.errors || []), runtimeBackendError].filter(Boolean)
  const messages = [...new Set(errors.map((error) => error.message).filter(Boolean))]
  const preparationMessage =
    metadata.preparation?.last_error || (runtimeBackendError ? '' : metadata.error?.message) || ''
  const screenshotError = errors.find((error) => screenshotFailureCodes.includes(error.code))
  const screenshotAlternatives = (screenshotError?.alternatives || []).map((item) => item.label)
  const touchError = errors.find((error) => touchFailureCodes.includes(error.code))
  const touchAlternatives = (touchError?.alternatives || []).map((item) => item.label)
  const reconfirmInstance = errors.some((error) =>
    ['topology_changed', 'waydroid_binding_changed', 'redroid_binding_changed'].includes(error.code)
  )
  const repairFields = errors.flatMap((error) => error.fields || [])
  const visible = advanced
    ? Object.keys(fieldLabels).filter((key) => key !== 'game_package' || packages.length > 1)
    : errors.length
      ? repairFields
      : manual
        ? ['last_serial']
        : []
  const needsConfigPath =
    ['windows.bluestacks5', 'linux.waydroid', 'linux.redroid'].includes(profile.preset_id) ||
    repairFields.includes('config_path')
  const identityFieldShown = (key) =>
    key in fieldLabels &&
    !connectionBackendKeys.includes(key) &&
    !(discovery && instances.options.length && key === 'instance_id') &&
    !(mumuPro && !profile.topology_fingerprint && ['instance_id', 'instance_name'].includes(key)) &&
    !(air && ['manager_path', 'config_path', 'instance_id', 'instance_name'].includes(key)) &&
    !(key === 'config_path' && !needsConfigPath)
  const buildField = (key) => {
    const options =
      key === 'preset_id'
        ? presets
        : key === 'last_serial' && candidates.length
          ? candidates
          : key === 'game_package'
            ? packages
            : key === 'touch_backend'
              ? touchOptions
              : key === 'screenshot_backend'
                ? screenshotOptions
                : backendOptions[key]
    const presetsMap = presetPlaceholders[profile.preset_id] || presetPlaceholders.default
    const placeholder = presetsMap[key] || presetPlaceholders.default[key] || ''
    const help = mumuPro
      ? {
          installation_path:
            'MuMu Pro 应用路径；留空时使用 /Applications/MuMuPlayer.app。用于发现和核验所选实例。',
          manager_path: 'mumutool 路径；留空时从应用路径查找。核验所选实例后可启动或关闭该实例。',
          instance_id: '从检测结果中选择的实例序号；手动填写 ADB 地址时无需填写。',
          last_serial: profile.topology_fingerprint
            ? '检测连接时从已选实例读取当前 ADB 地址；无需手动维护。'
            : '手动模式下填写目标实例的 ADB 地址，例如 127.0.0.1:16384。'
        }[key] ||
        fieldHelpTexts[key] ||
        ''
      : fieldHelpTexts[key] || ''
    const span = [
      'instance_id',
      'instance_name',
      'screenshot_backend',
      'touch_backend',
      'game_package'
    ].includes(key)
      ? 1
      : 2
    return {
      key,
      label:
        key === 'installation_path' && (air || avd)
          ? air
            ? '应用路径'
            : 'Android SDK 目录'
          : key === 'config_path' && waydroid
            ? 'Waydroid 数据目录'
            : fieldLabels[key],
      value: key === 'game_package' ? confirmedPackage : (profile[key] ?? ''),
      options,
      kind: options ? 'select' : 'input',
      tag: key === 'last_serial',
      disabled: locked,
      placeholder,
      help,
      span
    }
  }
  const fields = [...new Set(visible)].filter(identityFieldShown).map(buildField)
  // The screenshot and touch backends, the recovery budget and the boss key hold
  // no device identity, so they stay visible instead of hiding behind the
  // advanced toggle that guards the identity fields.
  const connectionVisible = Boolean(profile.preset_id) || advanced || errors.length > 0
  const connectionFields = connectionVisible
    ? connectionBackendKeys.filter((key) => key in fieldLabels).map(buildField)
    : []
  return {
    hostLabel:
      { windows: 'Windows', win32: 'Windows', darwin: 'macOS', macos: 'macOS', linux: 'Linux' }[
        host
      ] || '正在读取主机平台',
    presetTitle: presetLabels[profile.preset_id] || profile.preset_id || '未配置设备',
    summary: [presetLabels[profile.preset_id], profile.instance_name, profile.last_serial]
      .filter(Boolean)
      .join(' · '),
    statusTagType: metadata.active
      ? 'success'
      : busy
        ? 'info'
        : discovery
          ? instances.options.length
            ? 'info'
            : 'error'
          : errors.length
            ? 'warning'
            : result?.ok
              ? 'success'
              : 'default',
    statusDisplayLabel: metadata.active
      ? '会话运行中'
      : busy
        ? '正在检测...'
        : discovery
          ? instances.options.length
            ? '请选择实例'
            : '未发现实例'
          : errors.length
            ? '需要配置 / 修复'
            : result?.ok
              ? '连接正常'
              : '尚未检测',
    message: messages.join('\n'),
    screenshotAlternativeMessage: screenshotAlternatives.length
      ? `可选截图后端：${screenshotAlternatives.join('、')}。如需更换，请手动选择截图后端并重新检测。`
      : '',
    touchAlternativeMessage: touchAlternatives.length
      ? `可选触控后端：${touchAlternatives.join('、')}。如需更换，请手动选择触控后端并重新检测。`
      : '',
    guidance: messages.includes(result?.guidance) ? '' : result?.guidance || '',
    compatibilityLabel: mumuPro || genymotion ? '兼容性记录' : waydroid ? '主要对象' : '',
    discoveryLabel: mumuPro
      ? '官方 mumutool'
      : genymotion
        ? '官方 gmtool'
        : waydroid
          ? '官方状态与 ADB 连接信息'
          : '',
    compatibilityNote: mumuPro
      ? profile.topology_fingerprint
        ? '所选实例由 mumutool 的实例文件路径核验，再读取当前 ADB 端口测试连接。检测可先打开 MuMu Pro 应用，再尝试启动已停止的所选实例；自动启停同样先核验实例文件路径。'
        : '检测可尝试打开 MuMu Pro 应用并列出实例，选定后尝试启动已停止的目标。也可在高级设置填写 ADB serial；此模式需手动启停，无法识别端口被其他实例复用。'
      : genymotion
        ? 'Genymotion 属于 Linux 兼容性记录，不代表永久支持承诺。发现能力取决于官方 gmtool 可确认的输出；管理工具缺失、版本不兼容或输出不完整时，请使用高级手动配置。'
        : '',
    bindingHelp: air
      ? 'BlueStacks Air 仅检测应用与 ADB 连接，请在应用中手动开启 ADB、启动或关闭模拟器。'
      : avd
        ? '检测实例或选择目标时，会尝试启动已停止的 AVD。此次选择仅授权本次启动，定时任务不复用此授权。普通退出不会关闭 AVD；在“任务结束后”选择“关闭模拟器”时，仅关闭 mower 启动的目标，再次启动仍需确认。'
        : redroid
          ? '仅发现本机 Docker 的 redroid 容器。检测或选择目标时尝试启动已停止的容器；定时任务不复用此次启动授权，新会话只读取同一容器的当前端口；退出保留容器。远程 Docker、Podman、Kubernetes、自定义镜像和非标准网络请使用高级手动配置。'
          : genymotion
            ? '仅使用官方 gmtool 发现和启动实例，检测或选择目标时尝试启动已停止的 VM；定时任务不复用此次启动授权。新会话只复核所选 VM，目标失效时不切换到其他 VM；连接经 ADB 只读检测通过后保存。退出 mower 保留 VM。'
            : waydroid
              ? '检测使用 waydroid status 与官方会话信息，已停止的所选会话可自动启动，通过 IP:5555 验证连接。新会话复核同一用户与数据目录；地址缺失或不唯一时，请核对官方状态并补充 serial，非标准环境可使用“其他模拟器”。'
              : '',
    // The status tag explains how a connection is verified and when the form is
    // written: the sentence that used to sit in the notice above the buttons.
    connectionHelp: managedStart
      ? '“启动并检测”核验所选实例，已停止时先启动再检测连接；运行中的实例直接检测连接，其他错误显示修复提示。多个实例需先选定目标，下拉“测试连接”只读取状态，不会启动或重启模拟器及其管理器。“启动并测试连接”按恢复策略处理所选实例。从检测结果选择的实例先保存编号和身份核验信息，连接失败不撤销选择；ADB 地址和游戏包在验证通过后保存。'
      : '“测试连接”只读取当前连接，不会启动或重启设备；请先确保目标设备已经启动。连接验证通过后，这份设备设置才会保存。',
    preparationMessage: messages.includes(preparationMessage) ? '' : preparationMessage,
    fields,
    connectionFields,
    connectionVisible,
    instances,
    locked,
    unrelatedLocked: false,
    actions: {
      manualFallback: {
        visible:
          (mumuPro || redroid || genymotion) && errors.some((error) => error.action === 'manual'),
        disabled: locked,
        preset: mumuPro ? 'macos.mumu_pro' : 'manual.other',
        label: mumuPro ? '手动填写连接地址' : '进入高级手动配置'
      },
      startBound: {
        visible: managedStart,
        disabled: locked || !managedStart,
        label: '启动并测试连接'
      },
      prepare: {
        visible: profile.preset_id === 'manual.physical',
        disabled: locked || !profile.last_serial?.trim(),
        serial: profile.last_serial || '',
        label: '仅本次临时整备并启动'
      },
      detect: {
        label:
          reconfirmInstance || discover || discovery
            ? '检测实例'
            : managedStart
              ? '启动并检测'
              : errors.length
                ? '重试连接'
                : '测试连接',
        disabled: locked,
        endpoint: discovery || discover || reconfirmInstance ? 'discover' : 'preflight',
        options: managedStart
          ? [
              {
                label: '启动并检测',
                key: 'detect',
                props: { title: '核验所选实例；已停止时先启动，再检测连接。' }
              },
              {
                label: '测试连接（只读）',
                key: 'preflight',
                props: { title: '只读取当前连接状态，不启动或重启模拟器及其管理器。' }
              },
              {
                label: '启动并测试连接',
                key: 'start',
                disabled: locked,
                props: { title: '按恢复策略启动或恢复所选实例，然后验证连接。' }
              }
            ]
          : [
              {
                label: errors.length ? '重试连接' : '测试连接',
                key: 'detect',
                props: { title: '只读取当前连接状态，不启动或重启模拟器及其管理器。' }
              }
            ]
      },
      discover: {
        label: '检测实例',
        visible: presetPrefix === 'windows' || avd || mumuPro || waydroid || redroid || genymotion,
        disabled: locked
      }
    }
  }
}
