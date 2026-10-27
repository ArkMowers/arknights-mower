<script setup>
import { i18n } from '@/i18n'
import { computed, inject, onMounted, onUnmounted, ref, shallowRef, unref, watch } from 'vue'
import { softwareUpdateMessage } from '@/utils/softwareUpdatePresentation'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { useMowerStore } from '@/stores/mower'
import { useUpdateProgress } from '@/composables/useUpdateProgress'
import SoftwareComponentUpdates from './SoftwareComponentUpdates.vue'

function localizedMessage(key = '', params = {}) {
  const replacement = shallowRef(undefined)
  return computed({
    get: () =>
      replacement.value !== undefined
        ? unref(replacement.value)
        : typeof key === 'function'
          ? key()
          : key
            ? i18n.global.t(key, typeof params === 'function' ? params() : params)
            : '',
    set: (value) => {
      replacement.value = value
    }
  })
}

const axios = inject('axios')
const { updates_enabled } = storeToRefs(useMowerStore())
const updatesAllowed = computed(() => updates_enabled.value === true)
const {
  runtime_platform,
  maa_path,
  maa_mirrorchyan_token,
  maa_update_channel,
  maa_auto_check_update,
  maa_auto_update,
  maa_resource_auto_check_update,
  maa_resource_auto_update
} = storeToRefs(useConfigStore())

const maa_update_supported = ref(false)
const maa_update_platform = ref('')
const maa_update_platform_label = computed(() =>
  runtime_platform.value === 'android'
    ? 'Android'
    : { linux: 'Linux', darwin: 'macOS', windows: 'Windows' }[maa_update_platform.value] || ''
)
const maa_update_arch = ref('')
const maa_update_source = ref('github')
const maa_resource_source = ref('github')
let maa_update_source_initialized = false
const maa_latest_version = ref('')
const maa_installed = ref(false)
const maa_installed_version = ref('')
const maa_backup_path = ref('')
const maa_update_info_msg = localizedMessage()
const maa_component_updates = ref([])
const maa_component_controls = ref([])
const maa_combined_checking = ref(false)
const maa_update_check = ref({
  status: 'idle',
  message: '',
  available: false,
  id: ''
})
const maa_update_job = ref({
  status: 'idle',
  phase: 'idle',
  message: '',
  progress: null,
  current: 0,
  total: 0,
  version: '',
  operation: '',
  result: null
})
let maa_update_timer = null
let maa_update_info_request_id = 0
const maa_resource_update_supported = ref(false)
const maa_resource_current_version = ref('')
const maa_resource_latest_version = ref('')
const maa_resource_release_note = ref('')
const maa_resource_backup_path = ref('')
const maa_resource_update_info_msg = localizedMessage()
const maa_resource_update_check = ref({
  status: 'idle',
  message: '',
  available: false,
  id: ''
})
const maa_resource_update_job = ref({
  status: 'idle',
  phase: 'idle',
  message: '',
  progress: null,
  current: 0,
  total: 0,
  version: '',
  target: '',
  result: null
})
const show_maa_update_progress = useUpdateProgress(maa_update_job)
const show_maa_resource_update_progress = useUpdateProgress(maa_resource_update_job)

let maa_resource_update_timer = null
let maa_resource_update_info_request_id = 0
let maa_path_refresh_timer = null
let maa_auto_check_timer = null
let maa_update_check_request_id = 0
let maa_resource_check_request_id = 0
let disposed = false
const mirrorchyan_cdk_status = ref({
  loading: false,
  checked_token: '',
  valid: false,
  expired: false,
  code: null,
  expires_at: 0,
  message: ''
})
let mirrorchyan_cdk_timer = null
let mirrorchyan_cdk_request_id = 0

function reset_mirrorchyan_cdk_status(message = '') {
  mirrorchyan_cdk_status.value = {
    loading: false,
    checked_token: '',
    valid: false,
    expired: false,
    code: null,
    expires_at: 0,
    message
  }
}

async function check_mirrorchyan_cdk(token = maa_mirrorchyan_token.value) {
  if (!updatesAllowed.value) return
  if (mirrorchyan_cdk_timer) {
    window.clearTimeout(mirrorchyan_cdk_timer)
    mirrorchyan_cdk_timer = null
  }
  const normalized_token = String(token || '').trim()
  if (normalized_token.length !== 24) {
    reset_mirrorchyan_cdk_status(
      normalized_token
        ? localizedMessage('settings.maa.enterTheComplete24CharacterMirrorchyanCdk')
        : ''
    )
    return false
  }

  const request_id = ++mirrorchyan_cdk_request_id
  mirrorchyan_cdk_status.value = {
    ...mirrorchyan_cdk_status.value,
    loading: true,
    checked_token: normalized_token,
    message: localizedMessage('settings.maa.checkingMirrorchyanCdk')
  }
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/maa-update/mirrorchyan-status`,
      {
        mirror_token: normalized_token,
        channel: maa_update_channel.value
      }
    )
    if (
      request_id !== mirrorchyan_cdk_request_id ||
      normalized_token !== String(maa_mirrorchyan_token.value || '').trim()
    ) {
      return false
    }
    const data = response.data
    mirrorchyan_cdk_status.value = {
      loading: false,
      checked_token: normalized_token,
      valid: Boolean(data.ok && data.valid),
      expired: Boolean(data.expired),
      code: data.code ?? null,
      expires_at: Number(data.expires_at || 0),
      message: data.message || localizedMessage('settings.maa.mirrorchyanCdkStatusUnknown')
    }
  } catch (error) {
    if (request_id !== mirrorchyan_cdk_request_id) return false
    mirrorchyan_cdk_status.value = {
      loading: false,
      checked_token: normalized_token,
      valid: false,
      expired: false,
      code: null,
      expires_at: 0,
      message:
        error.response?.data?.message ||
        localizedMessage('settings.maa.mirrorchyanCdkCheckFailed', { value0: error.message })
    }
  }
  return mirrorchyan_cdk_status.value.valid
}

function schedule_mirrorchyan_cdk_check(token) {
  if (!updatesAllowed.value) return
  if (runtime_platform.value === 'android') return
  if (mirrorchyan_cdk_timer) window.clearTimeout(mirrorchyan_cdk_timer)
  mirrorchyan_cdk_request_id++
  const normalized_token = String(token || '').trim()
  if (!normalized_token) {
    reset_mirrorchyan_cdk_status()
    return
  }
  if (normalized_token.length !== 24) {
    reset_mirrorchyan_cdk_status(
      localizedMessage('settings.maa.enterTheComplete24CharacterMirrorchyanCdk')
    )
    return
  }
  reset_mirrorchyan_cdk_status(localizedMessage('settings.maa.waitingForMirrorchyanCdkValidation'))
  mirrorchyan_cdk_timer = window.setTimeout(() => check_mirrorchyan_cdk(normalized_token), 500)
}

function reset_maa_update_check(clear_latest = true) {
  maa_update_check_request_id++
  maa_update_check.value = {
    status: 'idle',
    message: '',
    available: false,
    id: ''
  }
  if (clear_latest) maa_latest_version.value = ''
}

function reset_maa_resource_update_check(clear_latest = true) {
  maa_resource_check_request_id++
  maa_resource_update_check.value = {
    status: 'idle',
    message: '',
    available: false,
    id: ''
  }
  if (clear_latest) {
    maa_resource_latest_version.value = ''
    maa_resource_release_note.value = ''
  }
}

function normalize_maa_version(value) {
  return String(value || '')
    .trim()
    .replace(/^v/i, '')
    .toLowerCase()
}

function versions_are_equal(left, right, normalizer = (value) => String(value || '').trim()) {
  const normalized_left = normalizer(left)
  const normalized_right = normalizer(right)
  return Boolean(normalized_left && normalized_right && normalized_left === normalized_right)
}

watch(
  maa_mirrorchyan_token,
  (token, previousToken = '') => {
    if (runtime_platform.value !== 'android' && token.trim() && !previousToken.trim())
      maa_update_source.value = 'mirrorchyan'
    if (token !== previousToken) {
      if (maa_update_source.value === 'mirrorchyan') reset_maa_update_check()
      if (maa_resource_source.value === 'mirrorchyan') reset_maa_resource_update_check()
    }
    if (maa_update_supported.value) {
      schedule_mirrorchyan_cdk_check(token)
    }
    schedule_auto_check_updates(900)
  },
  { immediate: true }
)

watch(maa_update_channel, async (channel, previous_channel) => {
  if (channel === previous_channel) return
  reset_maa_update_check()
  if (maa_update_supported.value) {
    schedule_mirrorchyan_cdk_check(maa_mirrorchyan_token.value)
    await get_maa_update_info()
  }
  schedule_auto_check_updates()
})

watch(maa_update_source, async (source, previous_source) => {
  if (source === previous_source) return
  reset_maa_update_check()
  await get_maa_update_info()
  schedule_auto_check_updates()
})

watch(maa_resource_source, async () => {
  reset_maa_resource_update_check()
  await get_maa_resource_update_info()
  schedule_auto_check_updates()
})

watch([maa_auto_check_update, maa_auto_update], ([check, install]) => {
  if (install && !check) maa_auto_check_update.value = true
  reset_maa_update_check()
  schedule_auto_check_updates(0)
})

watch([maa_resource_auto_check_update, maa_resource_auto_update], ([check, install]) => {
  if (install && !check) maa_resource_auto_check_update.value = true
  reset_maa_resource_update_check()
  schedule_auto_check_updates(0)
})

const maa_updating = computed(() => maa_update_job.value.status === 'running')
const maa_resource_updating = computed(() => maa_resource_update_job.value.status === 'running')
const maa_update_checking = computed(() => maa_update_check.value.status === 'checking')
const maa_resource_update_checking = computed(
  () => maa_resource_update_check.value.status === 'checking'
)
const maa_path_missing = computed(() => !String(maa_path.value || '').trim())
const maa_update_versions_equal = computed(() =>
  versions_are_equal(maa_latest_version.value, maa_installed_version.value, normalize_maa_version)
)
const maa_resource_versions_equal = computed(() =>
  versions_are_equal(maa_resource_latest_version.value, maa_resource_current_version.value)
)
const maa_managed_operation_label = computed(() =>
  maa_installed.value
    ? i18n.global.t('settings.maa.update')
    : i18n.global.t('settings.maa.download')
)
const maa_job_operation_label = computed(() =>
  maa_update_job.value.operation === 'update'
    ? i18n.global.t('settings.maa.update')
    : i18n.global.t('settings.maa.download')
)
const maa_update_channel_label = computed(() =>
  maa_update_channel.value === 'beta'
    ? i18n.global.t('settings.maa.beta')
    : i18n.global.t('settings.maa.stable')
)
const mirrorchyan_cdk_remaining_days = computed(() => {
  if (!mirrorchyan_cdk_status.value.expires_at) return null
  return (mirrorchyan_cdk_status.value.expires_at * 1000 - Date.now()) / 86_400_000
})
const mirrorchyan_cdk_message = computed(() => {
  const status = mirrorchyan_cdk_status.value
  if (!String(maa_mirrorchyan_token.value || '').trim()) return ''
  if (status.loading) return status.message
  if (!status.valid || !status.expires_at) return status.message
  const remaining_days = Math.max(0, mirrorchyan_cdk_remaining_days.value).toFixed(1)
  const expires_at = new Date(status.expires_at * 1000).toLocaleString(i18n.global.locale.value, {
    hour12: false
  })
  return i18n.global.t('settings.maa.mirrorchyanCdkExpiresInDays', {
    value0: remaining_days,
    value1: expires_at
  })
})
const mirrorchyan_cdk_message_class = computed(() => {
  const status = mirrorchyan_cdk_status.value
  const token = String(maa_mirrorchyan_token.value || '').trim()
  if (token && token.length !== 24) return 'update-error'
  if (status.loading || status.checked_token === '') return 'update-hint'
  if (!status.valid || status.expired) return 'update-error'
  if (mirrorchyan_cdk_remaining_days.value !== null && mirrorchyan_cdk_remaining_days.value <= 7) {
    return 'update-warning'
  }
  return 'update-success'
})
const mirrorchyan_cdk_ready = computed(() => {
  const token = String(maa_mirrorchyan_token.value || '').trim()
  const status = mirrorchyan_cdk_status.value
  return (
    token.length === 24 &&
    !status.loading &&
    status.checked_token === token &&
    status.valid &&
    !status.expired
  )
})
const maa_update_check_message_class = computed(() =>
  maa_update_check.value.status === 'error' ? 'update-error' : 'update-success'
)
const maa_resource_update_check_message_class = computed(() =>
  maa_resource_update_check.value.status === 'error' ? 'update-error' : 'update-success'
)
const maa_update_action_disabled = computed(() => {
  if (maa_updating.value || maa_resource_updating.value || maa_update_checking.value) return true
  if (maa_update_source.value === 'mirrorchyan' && !mirrorchyan_cdk_ready.value) return true
  if (!maa_installed.value) return false
  if (maa_update_versions_equal.value) return true
  return !maa_update_check.value.available || !maa_update_check.value.id
})
const maa_resource_update_action_disabled = computed(
  () =>
    maa_resource_updating.value ||
    maa_resource_update_checking.value ||
    maa_updating.value ||
    maa_resource_versions_equal.value ||
    !maa_resource_update_check.value.available ||
    !maa_resource_update_check.value.id ||
    (maa_resource_source.value === 'mirrorchyan' &&
      runtime_platform.value !== 'android' &&
      !mirrorchyan_cdk_ready.value)
)
const maa_update_progress_status = computed(() => {
  if (maa_update_job.value.status === 'error') return 'error'
  if (maa_update_job.value.status === 'success') return 'success'
  return 'default'
})
const maa_resource_update_progress_status = computed(() => {
  if (maa_resource_update_job.value.status === 'error') return 'error'
  if (maa_resource_update_job.value.status === 'success') return 'success'
  return 'default'
})

async function auto_check_updates() {
  if (!updatesAllowed.value) return
  if (disposed || maa_path_missing.value || maa_updating.value || maa_resource_updating.value)
    return

  if (maa_auto_check_update.value && maa_installed.value && maa_update_supported.value) {
    const checked = await check_maa_update()
    if (
      checked &&
      !disposed &&
      maa_auto_update.value &&
      maa_auto_check_update.value &&
      !maa_update_action_disabled.value
    )
      await start_maa_update()
  }
  if (
    !disposed &&
    maa_resource_auto_check_update.value &&
    !maa_updating.value &&
    !maa_resource_updating.value &&
    maa_resource_update_supported.value
  ) {
    const checked = await check_maa_resource_update()
    if (
      checked &&
      !disposed &&
      maa_resource_auto_update.value &&
      maa_resource_auto_check_update.value &&
      !maa_resource_update_action_disabled.value
    )
      await start_maa_resource_update()
  }
}

function schedule_auto_check_updates(delay = 400) {
  if (maa_auto_check_timer) window.clearTimeout(maa_auto_check_timer)
  maa_auto_check_timer = null
  if (
    !updatesAllowed.value ||
    disposed ||
    (!maa_auto_check_update.value && !maa_resource_auto_check_update.value)
  )
    return
  maa_auto_check_timer = window.setTimeout(() => {
    maa_auto_check_timer = null
    auto_check_updates()
  }, delay)
}

function format_bytes(value) {
  const size = Number(value || 0)
  if (!size) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1)
  return `${(size / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

function apply_maa_update_job(job, apply_install_info = true) {
  if (!job) return
  maa_update_job.value = { ...maa_update_job.value, ...job }
  if (apply_install_info && job.result?.backup) maa_backup_path.value = job.result.backup
}

async function poll_maa_update() {
  if (disposed || !updatesAllowed.value) return
  if (maa_update_timer) window.clearTimeout(maa_update_timer)
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-update/status`)
    if (disposed || !updatesAllowed.value) return
    apply_maa_update_job(response.data.job, false)
    if (maa_update_job.value.status === 'running') {
      maa_update_timer = window.setTimeout(poll_maa_update, 800)
    } else if (maa_update_job.value.status === 'success') {
      reset_maa_update_check(false)
      reset_maa_resource_update_check(false)
      await get_maa_update_info()
      await get_maa_resource_update_info()
      schedule_auto_check_updates()
    }
  } catch (error) {
    maa_update_job.value.status = 'error'
    maa_update_job.value.message = localizedMessage('settings.maa.failedToReadMaaProgress', () => ({
      value0: maa_job_operation_label.value,
      value1: error.message
    }))
  }
}

async function get_maa_update_info() {
  if (disposed || !updatesAllowed.value) return
  const request_id = ++maa_update_info_request_id
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-update/info`, {
      params: {
        channel: maa_update_channel.value,
        maa_path: maa_path.value,
        source: maa_update_source.value
      }
    })
    if (request_id !== maa_update_info_request_id) return
    const data = response.data
    maa_component_updates.value =
      runtime_platform.value === 'android' ? data.component_updates || [] : []
    maa_update_supported.value = Boolean(data.supported)
    maa_update_platform.value = data.platform || ''
    maa_update_arch.value = data.arch || ''
    maa_installed.value = Boolean(data.installed)
    if (maa_update_supported.value) {
      schedule_mirrorchyan_cdk_check(maa_mirrorchyan_token.value)
    } else {
      reset_mirrorchyan_cdk_status()
    }
    if (!maa_update_source_initialized) {
      maa_update_source.value =
        runtime_platform.value !== 'android' && data.default_source === 'mirrorchyan'
          ? 'mirrorchyan'
          : 'github'
      maa_update_source_initialized = true
    }
    if (data.latest?.tag) maa_latest_version.value = data.latest.tag
    maa_installed_version.value = data.installed_version || ''
    maa_backup_path.value = data.backup || ''
    maa_update_info_msg.value = data.ok
      ? ''
      : data.message ||
        localizedMessage('settings.maa.failedToReadMaaVersion', () => ({
          value0: maa_managed_operation_label.value
        }))
    apply_maa_update_job(data.job, data.job?.result?.target === data.target)
    if (maa_update_job.value.status === 'running') poll_maa_update()
  } catch (error) {
    if (request_id !== maa_update_info_request_id) return
    maa_update_info_msg.value = localizedMessage('settings.maa.failedToReadMaaVersion2', () => ({
      value0: maa_managed_operation_label.value,
      value1: error.message
    }))
  }
}

function apply_maa_resource_update_job(job, apply_install_info = true) {
  if (!job) return
  maa_resource_update_job.value = { ...maa_resource_update_job.value, ...job }
  if (apply_install_info && job.status === 'success' && job.result?.installed) {
    maa_resource_current_version.value = job.result.installed.version || ''
    if (job.result.backup) maa_resource_backup_path.value = job.result.backup
  }
}

async function poll_maa_resource_update() {
  if (disposed || !updatesAllowed.value) return
  if (maa_resource_update_timer) window.clearTimeout(maa_resource_update_timer)
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-resource-update/status`)
    if (disposed || !updatesAllowed.value) return
    apply_maa_resource_update_job(response.data.job)
    if (maa_resource_update_job.value.status === 'running') {
      maa_resource_update_timer = window.setTimeout(poll_maa_resource_update, 800)
    } else if (maa_resource_update_job.value.status === 'success') {
      reset_maa_resource_update_check(false)
      await get_maa_resource_update_info()
      schedule_auto_check_updates()
    }
  } catch (error) {
    maa_resource_update_job.value.status = 'error'
    maa_resource_update_job.value.message = localizedMessage(
      'settings.maa.failedToReadMaaResourceUpdateProgress',
      { value0: error.message }
    )
  }
}

async function get_maa_resource_update_info() {
  if (disposed || !updatesAllowed.value) return
  const request_id = ++maa_resource_update_info_request_id
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-resource-update/info`, {
      params: { maa_path: maa_path.value, source: maa_resource_source.value }
    })
    if (request_id !== maa_resource_update_info_request_id) return
    const data = response.data
    maa_resource_update_supported.value = Boolean(data.supported)
    maa_resource_current_version.value = data.current?.version || ''
    if (data.latest?.version) {
      maa_resource_latest_version.value = data.latest.version
      maa_resource_release_note.value = data.latest.release_note || ''
    }
    maa_resource_backup_path.value = data.backup || ''
    maa_resource_update_info_msg.value =
      data.current?.error ||
      (data.ok
        ? ''
        : data.message || localizedMessage('settings.maa.failedToReadTheMaaResourceVersion'))
    if (data.job?.target === data.target) {
      apply_maa_resource_update_job(data.job)
      if (maa_resource_update_job.value.status === 'running') poll_maa_resource_update()
    } else {
      maa_resource_update_job.value = {
        status: 'idle',
        phase: 'idle',
        message: '',
        progress: null,
        current: 0,
        total: 0,
        version: '',
        target: data.target || '',
        result: null
      }
    }
  } catch (error) {
    if (request_id !== maa_resource_update_info_request_id) return
    maa_resource_update_info_msg.value = localizedMessage(
      'settings.maa.failedToReadTheMaaResourceVersion2',
      { value0: error.message }
    )
  }
}

async function check_maa_update() {
  if (!updatesAllowed.value) return
  if (
    maa_combined_checking.value ||
    maa_update_checking.value ||
    maa_updating.value ||
    !maa_installed.value
  )
    return
  maa_combined_checking.value = true
  try {
    // Keep the MAA result and check_id separate from optional Android components.
    // A failed check must not hide an available update in the other component.
    const [core] = await Promise.allSettled([
      check_maa_core_update(),
      ...(runtime_platform.value === 'android'
        ? maa_component_controls.value.map((component) => component.check())
        : [])
    ])
    return core.status === 'fulfilled' && core.value
  } finally {
    maa_combined_checking.value = false
  }
}

async function check_maa_core_update() {
  if (!updatesAllowed.value) return
  if (maa_update_checking.value || maa_updating.value || !maa_installed.value) return
  reset_maa_update_check(false)
  const request_id = maa_update_check_request_id
  maa_update_info_msg.value = ''
  if (maa_path_missing.value) {
    maa_update_check.value.status = 'error'
    maa_update_check.value.message = localizedMessage('settings.maa.setTheMaaDirectoryFirst')
    return
  }
  maa_update_check.value.status = 'checking'
  if (maa_update_source.value === 'mirrorchyan') {
    const valid = await check_mirrorchyan_cdk()
    if (disposed || request_id !== maa_update_check_request_id) {
      schedule_auto_check_updates()
      return
    }
    if (!valid) {
      maa_update_check.value.status = 'error'
      maa_update_check.value.message = localizedMessage(
        () =>
          mirrorchyan_cdk_status.value.message ||
          i18n.global.t('settings.maa.checkYourMirrorchyanCdk')
      )
      return
    }
  }
  maa_update_check.value.status = 'checking'
  maa_update_check.value.message = localizedMessage('settings.maa.checkingForMaaUpdates')
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/maa-update/check`, {
      maa_path: maa_path.value,
      source: maa_update_source.value,
      mirror_token: maa_update_source.value === 'mirrorchyan' ? maa_mirrorchyan_token.value : '',
      channel: maa_update_channel.value
    })
    if (disposed || request_id !== maa_update_check_request_id) return
    const data = response.data
    if (!data.ok) {
      maa_update_check.value.status = 'error'
      maa_update_check.value.message =
        data.message || localizedMessage('settings.maa.maaUpdateCheckFailed')
      return
    }
    maa_installed_version.value = data.installed_version || maa_installed_version.value
    maa_latest_version.value = data.latest?.tag || ''
    const available = Boolean(data.available) && !maa_update_versions_equal.value
    maa_update_check.value = {
      status: 'success',
      message:
        !available && maa_update_versions_equal.value
          ? localizedMessage('settings.maa.maaIsUpToDate')
          : data.message ||
            (available
              ? localizedMessage('settings.maa.aNewMaaVersionIsAvailable')
              : localizedMessage('settings.maa.maaIsUpToDate')),
      available,
      id: available ? data.check_id || '' : ''
    }
    return true
  } catch (error) {
    if (disposed || request_id !== maa_update_check_request_id) return
    maa_update_check.value.status = 'error'
    maa_update_check.value.message =
      error.response?.data?.message ||
      localizedMessage('settings.maa.maaUpdateCheckFailed2', { value0: error.message })
  } finally {
    if (request_id !== maa_update_check_request_id) schedule_auto_check_updates()
  }
}

async function check_maa_resource_update() {
  if (!updatesAllowed.value) return
  if (maa_resource_update_checking.value || maa_resource_updating.value || maa_updating.value)
    return
  reset_maa_resource_update_check(false)
  const request_id = maa_resource_check_request_id
  maa_resource_update_info_msg.value = ''
  if (maa_path_missing.value) {
    maa_resource_update_check.value.status = 'error'
    maa_resource_update_check.value.message = localizedMessage(
      'settings.maa.setTheMaaDirectoryFirst'
    )
    return
  }
  maa_resource_update_check.value.status = 'checking'
  if (maa_resource_source.value === 'mirrorchyan' && runtime_platform.value !== 'android') {
    const valid = await check_mirrorchyan_cdk()
    if (disposed || request_id !== maa_resource_check_request_id) {
      schedule_auto_check_updates()
      return
    }
    if (!valid) {
      maa_resource_update_check.value.status = 'error'
      maa_resource_update_check.value.message = localizedMessage(
        () =>
          mirrorchyan_cdk_status.value.message ||
          i18n.global.t('settings.maa.checkYourMirrorchyanCdk')
      )
      return
    }
  }
  maa_resource_update_check.value.status = 'checking'
  maa_resource_update_check.value.message = localizedMessage(
    'settings.maa.checkingForMaaResourceUpdates'
  )
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/maa-resource-update/check`,
      {
        maa_path: maa_path.value,
        source: maa_resource_source.value,
        mirror_token: maa_resource_source.value === 'mirrorchyan' ? maa_mirrorchyan_token.value : ''
      }
    )
    if (disposed || request_id !== maa_resource_check_request_id) return
    const data = response.data
    maa_resource_update_info_msg.value = data.current?.error || ''
    if (!data.ok) {
      maa_resource_update_check.value.status = 'error'
      maa_resource_update_check.value.message =
        data.message || localizedMessage('settings.maa.maaResourceUpdateCheckFailed')
      return
    }
    maa_resource_current_version.value = data.current?.version ?? ''
    maa_resource_latest_version.value = data.latest?.version || ''
    maa_resource_release_note.value = data.latest?.release_note || ''
    const available = Boolean(data.available) && !maa_resource_versions_equal.value
    maa_resource_update_check.value = {
      status: 'success',
      message:
        !available && maa_resource_versions_equal.value
          ? localizedMessage('settings.maa.maaResourcesAreUpToDate')
          : data.message ||
            (available
              ? localizedMessage('settings.maa.newMaaResourcesAreAvailable')
              : localizedMessage('settings.maa.maaResourcesAreUpToDate')),
      available,
      id: available ? data.check_id || '' : ''
    }
    return true
  } catch (error) {
    if (disposed || request_id !== maa_resource_check_request_id) return
    maa_resource_update_check.value.status = 'error'
    maa_resource_update_check.value.message =
      error.response?.data?.message ||
      localizedMessage('settings.maa.maaResourceUpdateCheckFailed2', { value0: error.message })
  } finally {
    if (request_id !== maa_resource_check_request_id) schedule_auto_check_updates()
  }
}

async function start_maa_update() {
  if (!updatesAllowed.value) return
  if (maa_updating.value) return
  maa_update_info_msg.value = ''
  maa_update_job.value = {
    ...maa_update_job.value,
    id: '',
    status: 'running',
    progress: null,
    message: localizedMessage('settings.maa.preparingUpdate')
  }
  if (maa_path_missing.value) {
    maa_update_job.value.status = 'error'
    maa_update_job.value.message = localizedMessage('settings.maa.setTheMaaDirectoryFirst')
    return
  }
  if (maa_update_source.value === 'mirrorchyan') {
    const valid = await check_mirrorchyan_cdk()
    if (!valid) {
      maa_update_job.value.status = 'error'
      maa_update_job.value.message = localizedMessage(
        () =>
          mirrorchyan_cdk_status.value.message ||
          i18n.global.t('settings.maa.checkYourMirrorchyanCdk')
      )
      return
    }
  }
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/maa-update/start`, {
      maa_path: maa_path.value,
      source: maa_update_source.value,
      mirror_token: maa_update_source.value === 'mirrorchyan' ? maa_mirrorchyan_token.value : '',
      channel: maa_update_channel.value,
      check_id: maa_update_check.value.id
    })
    if (!response.data.ok) {
      maa_update_job.value.status = 'error'
      maa_update_job.value.message =
        response.data.message ||
        localizedMessage('settings.maa.failedToStartMaa', () => ({
          value0: maa_managed_operation_label.value
        }))
      return
    }
    reset_maa_update_check(false)
    apply_maa_update_job(response.data.job)
    poll_maa_update()
  } catch (error) {
    maa_update_job.value.status = 'error'
    maa_update_job.value.message =
      error.response?.data?.message ||
      localizedMessage('settings.maa.failedToStartMaa2', () => ({
        value0: maa_managed_operation_label.value,
        value1: error.message
      }))
  }
}

async function start_maa_resource_update() {
  if (!updatesAllowed.value) return
  if (maa_resource_updating.value || maa_updating.value) return
  maa_resource_update_info_msg.value = ''
  maa_resource_update_job.value = {
    ...maa_resource_update_job.value,
    id: '',
    status: 'running',
    progress: null,
    message: localizedMessage('settings.maa.preparingUpdate')
  }
  if (maa_path_missing.value) {
    maa_resource_update_job.value.status = 'error'
    maa_resource_update_job.value.message = localizedMessage('settings.maa.setTheMaaDirectoryFirst')
    return
  }
  if (maa_resource_source.value === 'mirrorchyan' && runtime_platform.value !== 'android') {
    const valid = await check_mirrorchyan_cdk()
    if (!valid) {
      maa_resource_update_job.value.status = 'error'
      maa_resource_update_job.value.message = localizedMessage(
        () =>
          mirrorchyan_cdk_status.value.message ||
          i18n.global.t('settings.maa.checkYourMirrorchyanCdk')
      )
      return
    }
  }
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/maa-resource-update/start`,
      {
        maa_path: maa_path.value,
        source: maa_resource_source.value,
        mirror_token:
          maa_resource_source.value === 'mirrorchyan' ? maa_mirrorchyan_token.value : '',
        check_id: maa_resource_update_check.value.id
      }
    )
    if (!response.data.ok) {
      maa_resource_update_job.value.status = 'error'
      maa_resource_update_job.value.message =
        response.data.message || localizedMessage('settings.maa.failedToStartTheMaaResourceUpdate')
      return
    }
    reset_maa_resource_update_check(false)
    apply_maa_resource_update_job(response.data.job)
    poll_maa_resource_update()
  } catch (error) {
    maa_resource_update_job.value.status = 'error'
    maa_resource_update_job.value.message =
      error.response?.data?.message ||
      localizedMessage('settings.maa.failedToStartTheMaaResourceUpdate2', { value0: error.message })
  }
}

watch(maa_path, (value, previous_value) => {
  if (value === previous_value) return
  reset_maa_update_check()
  reset_maa_resource_update_check()
  if (maa_path_refresh_timer) window.clearTimeout(maa_path_refresh_timer)
  maa_path_refresh_timer = window.setTimeout(async () => {
    await Promise.all([get_maa_update_info(), get_maa_resource_update_info()])
    schedule_auto_check_updates()
  }, 400)
})

onMounted(async () => {
  await Promise.all([get_maa_update_info(), get_maa_resource_update_info()])
  schedule_auto_check_updates()
})

function stop_maa_background_tasks() {
  if (maa_update_timer) window.clearTimeout(maa_update_timer)
  if (maa_resource_update_timer) window.clearTimeout(maa_resource_update_timer)
  if (maa_path_refresh_timer) window.clearTimeout(maa_path_refresh_timer)
  if (maa_auto_check_timer) window.clearTimeout(maa_auto_check_timer)
  if (mirrorchyan_cdk_timer) window.clearTimeout(mirrorchyan_cdk_timer)
  mirrorchyan_cdk_request_id++
  maa_update_info_request_id++
  maa_resource_update_info_request_id++
  maa_update_check_request_id++
  maa_resource_check_request_id++
}

watch(updatesAllowed, async (allowed) => {
  if (!allowed) {
    stop_maa_background_tasks()
    maa_update_supported.value = false
    maa_resource_update_supported.value = false
    return
  }
  await Promise.all([get_maa_update_info(), get_maa_resource_update_info()])
  schedule_auto_check_updates()
})

onUnmounted(() => {
  disposed = true
  stop_maa_background_tasks()
})
</script>

<template>
  <n-card v-if="updatesAllowed" id="maa-update" :title="i18n.global.t('settings.maa.maaUpdates')">
    <template v-if="updatesAllowed && maa_update_supported">
      <div class="maa-updater">
        <div class="update-title">
          {{ maa_update_platform_label }}
          {{
            maa_installed
              ? i18n.global.t('settings.maa.updateMaa')
              : i18n.global.t('settings.maa.downloadMaa')
          }}
        </div>
        <div class="update-meta">
          <span>
            {{
              i18n.global.t('settings.maa.latestPackage', {
                operation: maa_managed_operation_label,
                channel: maa_update_channel_label,
                version: maa_latest_version || i18n.global.t('settings.maa.notChecked')
              })
            }}
          </span>
          <span
            >{{ i18n.global.t('settings.maa.installed')
            }}{{
              maa_installed_version || i18n.global.t('settings.maa.unknownManuallyInstalled')
            }}</span
          >
        </div>
        <div class="update-option">
          <span class="update-option-label">{{
            i18n.global.t('settings.maa.automaticallyCheckForUpdates')
          }}</span>
          <n-switch v-model:value="maa_auto_check_update" :disabled="maa_auto_update" />
          <span class="update-hint">{{
            i18n.global.t('settings.maa.checkForMaaCoreUpdatesWhenThis')
          }}</span>
        </div>
        <div class="update-option">
          <span class="update-option-label">{{
            i18n.global.t('settings.maa.automaticallyUpdateMaaCore')
          }}</span>
          <n-switch v-model:value="maa_auto_update" />
          <span class="update-hint">{{
            i18n.global.t('settings.maa.tryUpdatingWhenANewVersionIs')
          }}</span>
        </div>
        <div class="update-option">
          <span class="update-option-label">{{
            i18n.global.t('settings.maa.operationChannel', {
              operation: maa_managed_operation_label
            })
          }}</span>
          <n-radio-group v-model:value="maa_update_channel">
            <n-space>
              <n-radio value="stable">{{ i18n.global.t('settings.maa.stable') }}</n-radio>
              <n-radio value="beta">{{ i18n.global.t('settings.maa.beta') }}</n-radio>
            </n-space>
          </n-radio-group>
        </div>
        <div class="update-option">
          <span class="update-option-label">{{
            maa_installed
              ? i18n.global.t('settings.maa.updateSource')
              : i18n.global.t('settings.maa.downloadSource')
          }}</span>
          <n-radio-group v-model:value="maa_update_source">
            <n-space>
              <n-radio value="github">GitHub</n-radio>
              <n-radio v-if="runtime_platform !== 'android'" value="mirrorchyan">{{
                i18n.global.t('settings.maa.mirrorchyan')
              }}</n-radio>
            </n-space>
          </n-radio-group>
        </div>
        <template v-if="maa_update_source === 'mirrorchyan'">
          <n-input
            v-model:value="maa_mirrorchyan_token"
            type="password"
            show-password-on="mousedown"
            :placeholder="i18n.global.t('settings.maa.mirrorchyanCdk')"
            :disabled="maa_updating"
          />
          <div
            v-if="mirrorchyan_cdk_message"
            :class="mirrorchyan_cdk_message_class"
            aria-live="polite"
          >
            {{ mirrorchyan_cdk_message }}
          </div>
          <div class="update-hint">
            {{ i18n.global.t('settings.maa.theCdkIsSavedInTheMower') }}
            <n-a href="https://mirrorchyan.com/" target="_blank" rel="noopener noreferrer">
              {{ i18n.global.t('settings.maa.getACdk') }}
            </n-a>
          </div>
          <div v-if="maa_update_platform === 'windows'" class="update-hint">
            <template v-if="maa_installed && maa_update_arch === 'x64'">
              {{ i18n.global.t('settings.maa.mirrorWindowsOta', { arch: maa_update_arch }) }}
            </template>
            <template v-else-if="maa_installed">
              {{ i18n.global.t('settings.maa.windowsArm64HasNoOtaPackageAs') }}
            </template>
            <template v-else>
              {{
                i18n.global.t('settings.maa.mirrorWindowsInstall', {
                  channel: maa_update_channel_label,
                  arch: maa_update_arch
                })
              }}
            </template>
          </div>
          <div v-else-if="maa_update_platform === 'android'" class="update-hint">
            {{ i18n.global.t('settings.maa.useTheOfficialMaaAndroidArm64Component') }}
          </div>
          <div v-else-if="maa_update_platform === 'linux'" class="update-hint">
            {{
              i18n.global.t('settings.maa.mirrorLinuxPackage', {
                operation: maa_managed_operation_label,
                channel: maa_update_channel_label,
                arch: maa_update_arch
              })
            }}
          </div>
          <div v-else-if="maa_update_platform === 'darwin'" class="update-hint">
            {{
              i18n.global.t('settings.maa.mirrorMacPackage', {
                operation: maa_managed_operation_label,
                channel: maa_update_channel_label,
                arch: maa_update_arch
              })
            }}
          </div>
        </template>
        <div v-else-if="maa_update_platform === 'windows'" class="update-hint">
          <template v-if="maa_installed && maa_update_arch === 'x64'">
            {{ i18n.global.t('settings.maa.githubWindowsOta', { arch: maa_update_arch }) }}
          </template>
          <template v-else-if="maa_installed">
            {{ i18n.global.t('settings.maa.windowsArm64HasNoOtaPackageGithub') }}
          </template>
          <template v-else>
            {{
              i18n.global.t('settings.maa.githubWindowsInstall', {
                channel: maa_update_channel_label,
                arch: maa_update_arch
              })
            }}
          </template>
        </div>
        <div v-else-if="maa_update_platform === 'android'" class="update-hint">
          {{ i18n.global.t('settings.maa.useTheOfficialMaaAndroidArm64Component2') }}
        </div>
        <div v-else-if="maa_update_platform === 'linux'" class="update-hint">
          {{
            i18n.global.t('settings.maa.githubLinuxPackage', {
              operation: maa_managed_operation_label,
              channel: maa_update_channel_label,
              arch: maa_update_arch
            })
          }}
        </div>
        <div v-else-if="maa_update_platform === 'darwin'" class="update-hint">
          {{
            i18n.global.t('settings.maa.githubMacPackage', {
              operation: maa_managed_operation_label,
              channel: maa_update_channel_label,
              arch: maa_update_arch
            })
          }}
        </div>
        <div v-if="!maa_installed && maa_backup_path" class="update-hint">
          {{ i18n.global.t('settings.maa.newInstallationBackup', { path: maa_backup_path }) }}
        </div>
        <div v-else-if="maa_backup_path" class="update-hint">
          {{ i18n.global.t('settings.maa.installationBackup', { path: maa_backup_path }) }}
        </div>
        <n-progress
          v-if="show_maa_update_progress && maa_update_job.progress !== null"
          type="line"
          :percentage="maa_update_job.progress"
          :status="maa_update_progress_status"
          :indicator-placement="'inside'"
          :processing="maa_updating"
        />
        <div v-if="show_maa_update_progress && maa_update_job.message" class="update-message">
          {{ softwareUpdateMessage(maa_update_job.message) }}
          <template v-if="maa_update_job.total">
            （{{ format_bytes(maa_update_job.current) }} /
            {{ format_bytes(maa_update_job.total) }}）
          </template>
        </div>
        <div v-if="maa_update_info_msg" class="update-error">{{ maa_update_info_msg }}</div>
        <div
          v-if="maa_update_check.message"
          :class="maa_update_check_message_class"
          aria-live="polite"
        >
          {{ softwareUpdateMessage(maa_update_check.message) }}
        </div>
        <n-space>
          <n-button
            v-if="maa_installed"
            :loading="maa_update_checking || maa_combined_checking"
            :disabled="
              maa_updating || maa_resource_updating || maa_update_checking || maa_combined_checking
            "
            @click="check_maa_update"
          >
            {{ i18n.global.t('settings.maa.checkForMaaUpdates') }}
          </n-button>
          <n-button
            type="primary"
            :loading="maa_updating"
            :disabled="maa_update_action_disabled"
            @click="start_maa_update"
          >
            {{
              maa_installed
                ? i18n.global.t('settings.maa.updateMaa')
                : i18n.global.t('settings.maa.downloadMaa')
            }}
          </n-button>
        </n-space>
        <SoftwareComponentUpdates
          v-for="component in maa_component_updates"
          :key="component.endpoint"
          ref="maa_component_controls"
          :component="component"
          :disabled="maa_updating || maa_resource_updating"
        />
      </div>
    </template>
    <template v-else-if="updatesAllowed && maa_update_info_msg">
      <n-divider />
      <div class="maa-updater">
        <div class="update-title">
          {{ maa_update_platform_label }}
          {{
            maa_installed
              ? i18n.global.t('settings.maa.updateMaa')
              : i18n.global.t('settings.maa.downloadMaa')
          }}
        </div>
        <div class="update-error">{{ maa_update_info_msg }}</div>
      </div>
    </template>
    <template v-if="updatesAllowed && maa_resource_update_supported">
      <n-divider v-if="maa_update_supported || maa_update_info_msg" />
      <div class="maa-updater">
        <div class="update-title">
          {{ maa_update_platform_label }} {{ i18n.global.t('settings.maa.updateMaaResources') }}
        </div>
        <div class="update-meta">
          <span
            >{{ i18n.global.t('settings.maa.currentResources')
            }}{{ maa_resource_current_version || i18n.global.t('settings.maa.unknown') }}</span
          >
          <span
            >{{ i18n.global.t('settings.maa.latestResources')
            }}{{ maa_resource_latest_version || i18n.global.t('settings.maa.notChecked') }}</span
          >
        </div>
        <div v-if="maa_resource_release_note" class="update-hint">
          {{ i18n.global.t('settings.maa.latestEventResources') }}{{ maa_resource_release_note }}
        </div>
        <div class="update-option">
          <span class="update-option-label">{{
            i18n.global.t('settings.maa.automaticallyCheckResources')
          }}</span>
          <n-switch
            v-model:value="maa_resource_auto_check_update"
            :disabled="maa_resource_auto_update"
          />
          <span class="update-hint">{{
            i18n.global.t('settings.maa.checkForMaaResourceUpdatesWhenThis')
          }}</span>
        </div>
        <div class="update-option">
          <span class="update-option-label">{{
            i18n.global.t('settings.maa.automaticallyUpdateResources')
          }}</span>
          <n-switch v-model:value="maa_resource_auto_update" />
          <span class="update-hint">{{
            i18n.global.t('settings.maa.tryUpdatingWhenNewResourcesAreFound')
          }}</span>
        </div>
        <div class="update-option">
          <span class="update-option-label">{{
            i18n.global.t('settings.maa.resourceUpdateSource')
          }}</span>
          <n-radio-group v-model:value="maa_resource_source">
            <n-space>
              <n-radio value="github">GitHub</n-radio>
              <n-radio value="mirrorchyan">{{ i18n.global.t('settings.maa.mirrorchyan') }}</n-radio>
            </n-space>
          </n-radio-group>
        </div>
        <n-input
          v-if="maa_resource_source === 'mirrorchyan'"
          v-model:value="maa_mirrorchyan_token"
          type="password"
          show-password-on="mousedown"
          :placeholder="i18n.global.t('settings.maa.mirrorchyanCdk')"
          :disabled="maa_resource_updating"
        />
        <div class="update-hint">
          {{
            i18n.global.t('settings.maa.resourceSourceDetails', {
              source:
                maa_resource_source === 'mirrorchyan'
                  ? i18n.global.t('settings.maa.mirrorchyan')
                  : 'GitHub'
            })
          }}
          <template v-if="runtime_platform === 'android'">
            {{ i18n.global.t('settings.maa.onAndroidOcrModelsArePreparedAutomatically') }}
          </template>
        </div>
        <div v-if="maa_resource_backup_path" class="update-hint">
          {{ i18n.global.t('settings.maa.resourceBackup', { path: maa_resource_backup_path }) }}
        </div>
        <n-progress
          v-if="show_maa_resource_update_progress && maa_resource_update_job.progress !== null"
          type="line"
          :percentage="maa_resource_update_job.progress"
          :status="maa_resource_update_progress_status"
          :indicator-placement="'inside'"
          :processing="maa_resource_updating"
        />
        <div
          v-if="show_maa_resource_update_progress && maa_resource_update_job.message"
          class="update-message"
        >
          {{ softwareUpdateMessage(maa_resource_update_job.message) }}
          <template v-if="maa_resource_update_job.total">
            （{{ format_bytes(maa_resource_update_job.current) }} /
            {{ format_bytes(maa_resource_update_job.total) }}）
          </template>
        </div>
        <div v-if="maa_resource_update_info_msg" class="update-error">
          {{ maa_resource_update_info_msg }}
        </div>
        <div
          v-if="maa_resource_update_check.message"
          :class="maa_resource_update_check_message_class"
          aria-live="polite"
        >
          {{ softwareUpdateMessage(maa_resource_update_check.message) }}
        </div>
        <n-space>
          <n-button
            :loading="maa_resource_update_checking"
            :disabled="maa_resource_updating || maa_updating || maa_resource_update_checking"
            @click="check_maa_resource_update"
          >
            {{ i18n.global.t('settings.maa.checkForMaaResourceUpdates') }}
          </n-button>
          <n-button
            type="primary"
            :loading="maa_resource_updating"
            :disabled="maa_resource_update_action_disabled"
            @click="start_maa_resource_update"
          >
            {{ i18n.global.t('settings.maa.updateMaaResources') }}
          </n-button>
        </n-space>
      </div>
    </template>
    <div v-else-if="maa_resource_update_info_msg" class="update-error" role="status">
      {{ maa_resource_update_info_msg }}
    </div>
  </n-card>
</template>

<style scoped>
.maa-updater {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.update-title {
  font-size: 16px;
  font-weight: 600;
}

.update-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}

.update-option {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}

.update-option-label {
  min-width: 72px;
  color: var(--n-text-color-2);
}

.update-hint {
  color: var(--n-text-color-3);
  line-height: 1.6;
}

.update-message {
  line-height: 1.6;
  word-break: break-all;
}

.update-error {
  color: var(--n-color-error);
}

.update-warning {
  color: var(--n-color-warning);
}

.update-success {
  color: var(--n-color-success);
}
</style>
