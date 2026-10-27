import { i18n } from '@/i18n'
const { t } = i18n.global
import { configPatch } from './configPatch'

// DeviceProfile contains only scalar fields; key order has no identity meaning.
export function sameDeviceProfile(left, right) {
  const keys = Object.keys(left)
  return (
    keys.length === Object.keys(right).length &&
    keys.every((key) => Object.hasOwn(right, key) && left[key] === right[key])
  )
}

export const presetLabels = {
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

export function getPresetLabels() {
  return {
    ...presetLabels,
    'windows.ldplayer9': t('devices.ld9'),
    'windows.ldplayer14': t('devices.ld14'),
    'windows.nox': t('devices.nox'),
    'manual.other': t('devices.otherEmulator'),
    'manual.physical': t('devices.physical')
  }
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
  return backend === 'mumu_ipc' ? t('devices.mumuOnly') : t('devices.ldOnly')
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
    throw new Error(t('devices.avdChanged'))
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
    throw new Error(t('devices.redroidChanged'))
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
    throw new Error(t('devices.genymotionChanged'))
  }
  return {
    ...devicePreflightRequest(profile, draft, confirmedPackage),
    confirmed_instance: confirmedInstance
  }
}

export function deviceStartupRequest(profile, draft, metadata = {}, confirmedPackage = null) {
  if (!deviceSettingsState({ profile: draft, metadata }).actions.startBound.visible) {
    throw new Error(t('devices.unsupportedStart'))
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
  if (!candidate?.binding) throw new Error(t('devices.invalidInstance'))
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
    throw new Error(t('devices.physicalChanged'))
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
    throw new Error(t('devices.physicalChanged'))
  }
  const response = await axios.post(`${base}/start/0`, { preparation_serial: serial })
  if (response.data !== true && response.data !== 'true') {
    throw new Error(t('devices.startUnavailable'))
  }
}

function getFieldLabels() {
  return {
    preset_id: t('devices.emulator'),
    installation_path: t('devices.installationPath'),
    manager_path: t('devices.managerPath'),
    config_path: t('devices.configPath'),
    adb_path: t('devices.adbPath'),
    instance_id: t('devices.instanceId'),
    instance_name: t('devices.instanceName'),
    last_serial: t('devices.address'),
    screenshot_backend: t('devices.captureBackend'),
    touch_backend: t('devices.touchBackend'),
    game_package: t('devices.server')
  }
}

function getPresetPlaceholders() {
  return {
    'windows.mumu12': {
      installation_path: t('devices.example', { value: 'D:\\MuMuPlayer-12.0' }),
      manager_path: t('devices.example', {
        value: 'D:\\MuMuPlayer-12.0\\nx_main\\MuMuManager.exe'
      }),
      adb_path: t('devices.example', { value: 'D:\\MuMuPlayer-12.0\\shell\\adb.exe' }),
      instance_id: '0',
      instance_name: t('devices.optional'),
      last_serial: t('devices.example', { value: '127.0.0.1:16384' })
    },
    'windows.ldplayer9': {
      installation_path: t('devices.example', { value: 'C:\\leidian\\LDPlayer9' }),
      manager_path: t('devices.example', { value: 'C:\\leidian\\LDPlayer9\\dnconsole.exe' }),
      adb_path: t('devices.example', { value: 'C:\\leidian\\LDPlayer9\\adb.exe' }),
      instance_id: '0',
      instance_name: t('devices.optional'),
      last_serial: t('devices.example', { value: '127.0.0.1:5555' })
    },
    'windows.ldplayer14': {
      installation_path: t('devices.example', { value: 'C:\\leidian\\LDPlayer14' }),
      manager_path: t('devices.example', { value: 'C:\\leidian\\LDPlayer14\\dnconsole.exe' }),
      adb_path: t('devices.example', { value: 'C:\\leidian\\LDPlayer14\\adb.exe' }),
      instance_id: '0',
      instance_name: t('devices.optional'),
      last_serial: t('devices.example', { value: '127.0.0.1:5555' })
    },
    'windows.nox': {
      installation_path: t('devices.example', { value: 'C:\\Program Files\\Nox\\bin' }),
      manager_path: t('devices.example', { value: 'C:\\Program Files\\Nox\\bin\\Nox.exe' }),
      adb_path: t('devices.example', { value: 'C:\\Program Files\\Nox\\bin\\nox_adb.exe' }),
      instance_id: '0',
      instance_name: t('devices.optional'),
      last_serial: t('devices.example', { value: '127.0.0.1:62001' })
    },
    'windows.bluestacks5': {
      installation_path: t('devices.example', { value: 'C:\\Program Files\\BlueStacks_nxt' }),
      manager_path: t('devices.example', {
        value: 'C:\\Program Files\\BlueStacks_nxt\\HD-Player.exe'
      }),
      config_path: t('devices.example', {
        value: 'C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf'
      }),
      adb_path: t('devices.example', { value: 'C:\\Program Files\\BlueStacks_nxt\\HD-Adb.exe' }),
      instance_id: 'Pie64',
      instance_name: t('devices.optional'),
      last_serial: t('devices.example', { value: '127.0.0.1:5555' })
    },
    'macos.mumu_pro': {
      installation_path: t('devices.example', { value: '/Applications/MuMuPlayer.app' }),
      manager_path: t('devices.example', {
        value: '/Applications/MuMuPlayer.app/Contents/MacOS/mumutool'
      }),
      adb_path: t('devices.example', { value: '/Applications/MuMuPlayer.app/Contents/MacOS/adb' }),
      instance_id: '0',
      instance_name: t('devices.optional'),
      last_serial: t('devices.example', { value: '127.0.0.1:16384' })
    },
    'macos.bluestacks_air': {
      installation_path: t('devices.example', { value: '/Applications/BlueStacks.app' }),
      adb_path: t('devices.example', { value: 'adb' }),
      last_serial: t('devices.example', { value: '127.0.0.1:5555' })
    },
    'linux.waydroid': {
      installation_path: t('devices.example', { value: '/var/lib/waydroid' }),
      manager_path: t('devices.example', { value: 'waydroid' }),
      config_path: t('devices.example', { value: '/var/lib/waydroid' }),
      adb_path: t('devices.example', { value: 'adb' }),
      last_serial: t('devices.example', { value: '192.168.240.112:5555' })
    },
    'linux.redroid': {
      installation_path: t('devices.example', { value: 'docker' }),
      manager_path: t('devices.example', { value: 'docker' }),
      config_path: t('devices.example', { value: 'unix:///var/run/docker.sock' }),
      instance_id: t('devices.example', { value: 'redroid1' }),
      adb_path: t('devices.example', { value: 'adb' }),
      last_serial: t('devices.example', { value: '127.0.0.1:5555' })
    },
    'linux.genymotion': {
      installation_path: t('devices.example', { value: '/opt/genymobile/genymotion' }),
      manager_path: t('devices.example', { value: '/opt/genymobile/genymotion/gmtool' }),
      instance_id: t('devices.example', { value: '0' }),
      adb_path: t('devices.example', { value: 'adb' }),
      last_serial: t('devices.example', { value: '192.168.56.101:5555' })
    },
    'macos.avd': {
      installation_path: t('devices.example', { value: '/Users/username/Library/Android/sdk' }),
      manager_path: t('devices.example', { value: 'emulator' }),
      instance_id: t('devices.example', { value: 'Pixel_6_API_33' }),
      adb_path: t('devices.example', { value: 'adb' }),
      last_serial: t('devices.example', { value: 'emulator-5554' })
    },
    'linux.avd': {
      installation_path: t('devices.example', { value: '/home/username/Android/Sdk' }),
      manager_path: t('devices.example', { value: 'emulator' }),
      instance_id: t('devices.example', { value: 'Pixel_6_API_33' }),
      adb_path: t('devices.example', { value: 'adb' }),
      last_serial: t('devices.example', { value: 'emulator-5554' })
    },
    default: {
      installation_path: t('devices.installationPlaceholder'),
      manager_path: t('devices.managerPlaceholder'),
      config_path: t('devices.configPlaceholder'),
      adb_path: t('devices.adbPlaceholder'),
      instance_id: '0',
      instance_name: t('devices.optional'),
      last_serial: t('devices.example', { value: '127.0.0.1:5555' })
    }
  }
}

function getFieldHelpTexts() {
  return {
    installation_path: t('devices.installationHelp'),
    manager_path: t('devices.managerHelp'),
    config_path: t('devices.configHelp'),
    adb_path: t('devices.adbHelp'),
    instance_id: t('devices.instanceHelp'),
    instance_name: t('devices.instanceNameHelp'),
    last_serial: t('devices.addressHelp'),
    screenshot_backend: t('devices.captureHelp'),
    touch_backend: t('devices.touchHelp'),
    game_package: t('devices.serverHelp')
  }
}

function getBackendOptions() {
  return {
    screenshot_backend: [
      { label: 'ADB gzip', value: 'adb_gzip' },
      { label: 'DroidCast', value: 'droidcast' },
      { label: t('devices.mumuCapture'), value: 'mumu_ipc' },
      { label: t('devices.ldCapture'), value: 'ld_native' },
      { label: t('devices.customCommand'), value: 'custom' }
    ],
    touch_backend: [
      { label: 'scrcpy 1.21', value: 'scrcpy' },
      { label: 'MaaTouch', value: 'maatouch' },
      { label: t('devices.mumuTouch'), value: 'mumu_ipc' }
    ]
  }
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
  const presetLabels = getPresetLabels()
  const fieldLabels = getFieldLabels()
  const presetPlaceholders = getPresetPlaceholders()
  const fieldHelpTexts = getFieldHelpTexts()
  const backendOptions = getBackendOptions()
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
                ? t('devices.instanceNumber', { id: candidate.instance_id })
                : '',
            {
              running: t('devices.running'),
              starting: t('devices.starting'),
              stopped: t('devices.stopped'),
              error: t('devices.operationFailed')
            }[candidate.state],
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
        ? capability.reason || t('devices.unsupportedTouch')
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
    label: value === 'com.hypergryph.arknights' ? t('devices.official') : t('devices.bilibili')
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
          installation_path: t('devices.mumuAppHelp'),
          manager_path: t('devices.mumuToolHelp'),
          instance_id: t('devices.mumuInstanceHelp'),
          last_serial: profile.topology_fingerprint
            ? t('devices.mumuBoundAddress')
            : t('devices.mumuManualAddress')
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
            ? t('devices.appPath')
            : t('devices.sdkPath')
          : key === 'config_path' && waydroid
            ? t('devices.waydroidPath')
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
      ] || t('devices.loadingHost'),
    presetTitle: presetLabels[profile.preset_id] || profile.preset_id || t('devices.noDevice'),
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
      ? t('devices.sessionRunning')
      : busy
        ? t('devices.detecting')
        : discovery
          ? instances.options.length
            ? t('devices.chooseInstance')
            : t('devices.noInstances')
          : errors.length
            ? t('devices.needsRepair')
            : result?.ok
              ? t('devices.connected')
              : t('devices.notTested'),
    message: messages.join('\n'),
    screenshotAlternativeMessage: screenshotAlternatives.length
      ? t('devices.captureAlternatives', {
          backends: screenshotAlternatives.join(i18n.global.locale.value === 'en-US' ? ', ' : '、')
        })
      : '',
    touchAlternativeMessage: touchAlternatives.length
      ? t('devices.touchAlternatives', {
          backends: touchAlternatives.join(i18n.global.locale.value === 'en-US' ? ', ' : '、')
        })
      : '',
    guidance: messages.includes(result?.guidance) ? '' : result?.guidance || '',
    compatibilityLabel:
      mumuPro || genymotion
        ? t('devices.compatibilityRecord')
        : waydroid
          ? t('devices.primaryTarget')
          : '',
    discoveryLabel: mumuPro
      ? t('devices.officialMumuTool')
      : genymotion
        ? t('devices.officialGmtool')
        : waydroid
          ? t('devices.officialStatus')
          : '',
    compatibilityNote: mumuPro
      ? profile.topology_fingerprint
        ? t('devices.mumuVerifiedHelp')
        : t('devices.mumuDiscoveryHelp')
      : genymotion
        ? t('devices.genymotionCompatibility')
        : '',
    bindingHelp: air
      ? t('devices.airHelp')
      : avd
        ? t('devices.avdHelp')
        : redroid
          ? t('devices.redroidHelp')
          : genymotion
            ? t('devices.genymotionHelp')
            : waydroid
              ? t('devices.waydroidHelp')
              : '',
    // The status tag explains how a connection is verified and when the form is
    // written: the sentence that used to sit in the notice above the buttons.
    connectionHelp: managedStart
      ? t('devices.managedConnectionHelp')
      : t('devices.readOnlyConnectionHelp'),
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
        label: mumuPro ? t('devices.manualAddress') : t('devices.manualAdvanced')
      },
      startBound: {
        visible: managedStart,
        disabled: locked || !managedStart,
        label: t('devices.startTest')
      },
      prepare: {
        visible: profile.preset_id === 'manual.physical',
        disabled: locked || !profile.last_serial?.trim(),
        serial: profile.last_serial || '',
        label: t('devices.prepareStart')
      },
      detect: {
        label:
          reconfirmInstance || discover || discovery
            ? t('devices.detectInstances')
            : managedStart
              ? t('devices.startDetect')
              : errors.length
                ? t('devices.retryConnection')
                : t('devices.testConnection'),
        disabled: locked,
        endpoint: discovery || discover || reconfirmInstance ? 'discover' : 'preflight',
        options: managedStart
          ? [
              {
                label: t('devices.startDetect'),
                key: 'detect',
                props: { title: t('devices.startDetectHelp') }
              },
              {
                label: t('devices.testReadOnly'),
                key: 'preflight',
                props: { title: t('devices.testReadOnlyHelp') }
              },
              {
                label: t('devices.startTest'),
                key: 'start',
                disabled: locked,
                props: { title: t('devices.startTestHelp') }
              }
            ]
          : [
              {
                label: errors.length ? t('devices.retryConnection') : t('devices.testConnection'),
                key: 'detect',
                props: { title: t('devices.testReadOnlyHelp') }
              }
            ]
      },
      discover: {
        label: t('devices.detectInstances'),
        visible: presetPrefix === 'windows' || avd || mumuPro || waydroid || redroid || genymotion,
        disabled: locked
      }
    }
  }
}
