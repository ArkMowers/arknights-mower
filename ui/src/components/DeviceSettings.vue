<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
import { deviceConnectionNavigationKey } from '@/composables/deviceConnectionNavigation'
import PerformanceSettings from './PerformanceSettings.vue'
import {
  deviceSettingsState,
  sameDeviceProfile,
  devicePreflightRequest,
  deviceStartupRequest,
  deviceDetectionDraft,
  savePreflightDevice,
  saveDiscoveredDevice,
  deviceStatusResult,
  editDeviceDraft,
  manualDeviceDraft,
  startPhysicalPreparation,
  editedDevicePatch,
  isImmediateDeviceField
} from '@/utils/deviceSettings'

import { file_dialog, folder_dialog } from '@/utils/dialog'

const props = defineProps({ expanded: { type: Boolean, default: false } })
const config = useConfigStore()
const axios = inject('axios')
const connectionNavigation = inject(deviceConnectionNavigationKey, null)
const dialog = useDialog()
const message = useMessage()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/device`
const draft = ref({ ...config.device_profile })
const metadata = ref({})
const managerOwned = computed(() => config.manager_owned_device || metadata.value.manager_owned)
const result = ref(null)
const performanceObservation = ref(null)
const busy = ref(false)
const advanced = ref(false)
const showAdvanced = computed(() => props.expanded || advanced.value)
const manual = ref(false)
const selectedKey = ref(null)
const dirty = ref(false)
const confirmedPackage = ref(null)
const requestError = ref('')
const statusError = ref('')
const preparationNotice = ref('')
const state = computed(() =>
  deviceSettingsState({
    profile: draft.value,
    metadata: metadata.value,
    result: result.value,
    busy: busy.value,
    advanced: showAdvanced.value,
    manual: manual.value,
    selectedKey: selectedKey.value,
    confirmedPackage: confirmedPackage.value
  })
)
const startupWait = computed({
  get: () => config.simulator.wait_time ?? 30,
  set: (value) => {
    if (state.value.locked || !Number.isInteger(value) || value < 0) return
    config.simulator.wait_time = value
  }
})
const pathFields = ['installation_path', 'manager_path', 'config_path', 'adb_path']

async function browsePath(key) {
  if (state.value.locked) return
  try {
    const selected = key === 'installation_path' ? await folder_dialog() : await file_dialog()
    if (selected) {
      edit(key, selected)
    }
  } catch {
    // ignore dialog cancel
  }
}
let timer
let disposed = false
let readingStatus = false
let detectionRevision = 0
let savedHintTimer

const savedHint = ref(false)

watch(
  () => config.device_profile,
  (profile) => {
    if (!dirty.value && !busy.value) draft.value = { ...profile }
  },
  { deep: true }
)

watch(
  () =>
    JSON.stringify(
      [
        'preset_id',
        'installation_path',
        'manager_path',
        'config_path',
        'adb_path',
        'instance_id',
        'instance_name',
        'instance_uuid',
        'topology_fingerprint',
        'last_serial',
        'game_package'
      ].map((key) => draft.value[key])
    ),
  () => {
    performanceObservation.value = null
  },
  { flush: 'sync' }
)

function flashSaved() {
  savedHint.value = true
  clearTimeout(savedHintTimer)
  savedHintTimer = setTimeout(() => {
    savedHint.value = false
  }, 2400)
}

function edit(key, value) {
  if (state.value.locked || managerOwned.value) return
  if (key === 'game_package') confirmedPackage.value = value
  else if (
    isImmediateDeviceField(key) &&
    config.device_profile &&
    (!['screenshot_backend', 'touch_backend'].includes(key) ||
      draft.value.preset_id === config.device_profile.preset_id)
  ) {
    // Backend coupling uses the persisted pair. Pending identity edits remain
    // in the draft while this edit and its coupled backend are saved.
    const patch = editedDevicePatch(config.device_profile, key, value)
    draft.value = editDeviceDraft(draft.value, key, value)
    config.device_profile = { ...config.device_profile, ...patch }
    config
      .save_config()
      .then(flashSaved)
      .catch(() => {
        // The store reports the failure; the draft keeps the user's value.
      })
    return
  } else {
    draft.value = editDeviceDraft(draft.value, key, value)
    if (
      [
        'preset_id',
        'installation_path',
        'manager_path',
        'config_path',
        'instance_id',
        'last_serial'
      ].includes(key)
    ) {
      confirmedPackage.value = null
    }
  }
  dirty.value = true
  if (result.value?.ok) result.value = null
}

function enterManual(preset, showAdvanced = false) {
  if (state.value.locked) return
  draft.value = manualDeviceDraft(draft.value, preset)
  confirmedPackage.value = null
  dirty.value = true
  manual.value = true
  advanced.value = showAdvanced
  result.value = null
  selectedKey.value = null
  requestError.value = ''
}

const testingBossKey = ref(false)

async function testBossKey() {
  if (!draft.value.simulator_hotkey) return
  testingBossKey.value = true
  try {
    const response = await axios.post(`${base}/boss_key`, {
      hotkey: draft.value.simulator_hotkey
    })
    if (response.data?.ok) {
      message?.success(response.data.message || t('devices.bossTriggered'))
    } else {
      message?.warning(response.data?.message || t('devices.bossNotTriggered'))
    }
  } catch (error) {
    message?.error(error.response?.data?.message || error.message || t('devices.bossFailed'))
  } finally {
    testingBossKey.value = false
  }
}

async function readStatus() {
  if (disposed || readingStatus) return
  readingStatus = true
  const revision = detectionRevision
  const draftWasProtected = busy.value || dirty.value
  try {
    const response = await axios.get(`${base}/status`)
    if (!disposed) {
      result.value = deviceStatusResult(
        result.value,
        metadata.value.preflight,
        response.data.preflight,
        draftWasProtected || busy.value || dirty.value || revision !== detectionRevision
      )
      metadata.value = response.data
      statusError.value = ''
    }
  } catch (error) {
    if (!disposed) statusError.value = error.response?.data?.message || t('devices.statusFailed')
  } finally {
    readingStatus = false
  }
}

async function acceptPreflight(data) {
  result.value = data
  if (managerOwned.value) {
    performanceObservation.value = data.observations?.performance || null
    return
  }
  if (data.host_platform) metadata.value.host_platform = data.host_platform
  if (data.preset_id && data.preset_id !== draft.value.preset_id) dirty.value = true
  draft.value = deviceDetectionDraft(draft.value, data)
  if (!data.ok) {
    performanceObservation.value = data.observations?.performance || null
    return
  }
  draft.value = await savePreflightDevice({ config, profile: draft.value, result: data })
  performanceObservation.value = data.observations?.performance || null
  dirty.value = false
  manual.value = false
  advanced.value = false
  confirmedPackage.value = null
}

async function acceptOrStart(data, autoStart) {
  if (
    autoStart &&
    state.value.actions.startBound.visible &&
    ['instance_stopped', 'start_confirmation_required'].includes(data?.error?.code)
  ) {
    const { endpoint, payload } = deviceStartupRequest(
      config.device_profile || {},
      draft.value,
      metadata.value,
      confirmedPackage.value
    )
    const response = await axios.post(`${base}/${endpoint}`, payload)
    await acceptPreflight(response.data)
  } else await acceptPreflight(data)
}

async function preflight(autoStart = false) {
  if (managerOwned.value) {
    const response = await axios.post(`${base}/preflight`, { device: {} })
    await acceptPreflight(response.data)
    return
  }
  const response = await axios.post(`${base}/preflight`, {
    ...devicePreflightRequest(config.device_profile || {}, draft.value, confirmedPackage.value),
    ...(autoStart &&
    state.value.actions.startBound.visible &&
    draft.value.preset_id === 'macos.mumu_pro'
      ? { start_manager: true }
      : {})
  })
  await acceptOrStart(response.data, autoStart)
}

async function bindInstance(key, autoStart = true) {
  const candidate =
    result.value?.kind === 'discovery' && result.value.candidates?.find((item) => item.key === key)
  if (!candidate?.binding) return
  selectedKey.value = key
  dirty.value = true
  draft.value = await saveDiscoveredDevice({
    config,
    profile: draft.value,
    result: result.value,
    key
  })
  dirty.value = false
  flashSaved()
  manual.value = false
  confirmedPackage.value = null
  result.value = null
  await preflight(autoStart)
}

async function detect(
  endpoint = state.value.actions.detect.endpoint,
  key = null,
  autoStart = true
) {
  if (state.value.locked) return
  detectionRevision += 1
  busy.value = true
  performanceObservation.value = null
  requestError.value = ''
  try {
    await config.flush_config_saves()
    if (managerOwned.value) {
      await preflight(false)
      return
    }
    if (key) await bindInstance(key, autoStart)
    else if (endpoint === 'discover') {
      const response = await axios.post(`${base}/discover`, {
        ...devicePreflightRequest(config.device_profile || {}, draft.value),
        ...(autoStart && draft.value.preset_id === 'macos.mumu_pro' ? { start_manager: true } : {})
      })
      result.value = response.data
      selectedKey.value = null
      manual.value = false
      confirmedPackage.value = null
      if (response.data.host_platform) metadata.value.host_platform = response.data.host_platform
      if (response.data.kind === 'preflight') await acceptOrStart(response.data, autoStart)
      else if (response.data.selected_key) await bindInstance(response.data.selected_key, autoStart)
    } else await preflight(autoStart)
  } catch (error) {
    const detail = error.response?.data
    if (detail?.error?.code) result.value = detail
    else requestError.value = detail?.message || error.message || t('devices.detectionFailed')
  } finally {
    busy.value = false
    void readStatus()
  }
}

function selectDetect(key) {
  if (key === 'start') return startBound()
  if (key === 'preflight') return detect('preflight', null, false)
  return detect()
}

async function startBound() {
  if (state.value.locked || !state.value.actions.startBound.visible) return
  detectionRevision += 1
  busy.value = true
  performanceObservation.value = null
  requestError.value = ''
  try {
    await config.flush_config_saves()
    const { endpoint, payload } = deviceStartupRequest(
      config.device_profile || {},
      draft.value,
      metadata.value,
      confirmedPackage.value
    )
    const response = await axios.post(`${base}/${endpoint}`, payload)
    await acceptPreflight(response.data)
  } catch (error) {
    const detail = error.response?.data
    if (detail?.error?.code) result.value = detail
    else {
      requestError.value = detail?.message || error.message || t('devices.startupFailed')
    }
  } finally {
    busy.value = false
    void readStatus()
  }
}

function prepare() {
  const action = state.value.actions.prepare
  if (!action.visible || action.disabled) return
  const profile = { ...draft.value }
  const packageChoice = confirmedPackage.value
  dialog.warning({
    title: t('devices.authorizeSize'),
    content: t('devices.physicalAuthorization', { serial: action.serial }),
    positiveText: t('devices.authorizeStart'),
    negativeText: t('devices.cancel'),
    onPositiveClick: async () => {
      if (
        state.value.locked ||
        !sameDeviceProfile(draft.value, profile) ||
        confirmedPackage.value !== packageChoice
      ) {
        requestError.value = t('devices.authorizationChanged')
        return
      }
      busy.value = true
      requestError.value = ''
      preparationNotice.value = ''
      try {
        await startPhysicalPreparation({
          axios,
          config,
          profile,
          serial: action.serial,
          confirmedPackage: packageChoice,
          base: import.meta.env.VITE_HTTP_URL || ''
        })
        draft.value = { ...config.device_profile }
        dirty.value = false
        manual.value = false
        confirmedPackage.value = null
        preparationNotice.value = t('devices.preparationStarted', { serial: action.serial })
      } catch (error) {
        requestError.value =
          error.response?.data?.message || error.message || t('devices.preparationFailed')
      } finally {
        busy.value = false
        void readStatus()
      }
    }
  })
}

function updateStatusPolling() {
  clearInterval(timer)
  if (document.visibilityState === 'hidden' || disposed) return
  void readStatus()
  timer = setInterval(readStatus, 3000)
}

if (connectionNavigation) {
  watch(
    () => state.value.locked,
    (locked) => {
      connectionNavigation.locked.value = locked
    },
    { immediate: true, flush: 'sync' }
  )
  watch(
    connectionNavigation.request,
    (request) => {
      if (!request || !connectionNavigation.consume(request)) return
      if (request.action === 'settings') advanced.value = true
      else if (request.action === 'select') advanced.value = false
      else if (request.action === 'test') void selectDetect('preflight')
    },
    { immediate: true, flush: 'post' }
  )
}

onMounted(() => {
  updateStatusPolling()
  document.addEventListener('visibilitychange', updateStatusPolling)
})
onUnmounted(() => {
  disposed = true
  if (connectionNavigation) connectionNavigation.locked.value = false
  document.removeEventListener('visibilitychange', updateStatusPolling)
  clearInterval(timer)
  clearTimeout(savedHintTimer)
})
</script>

<template>
  <section class="device-settings" :aria-label="t('devices.connection')">
    <template v-if="managerOwned">
      <n-alert type="info" :show-icon="false"> {{ t('devices.managedHelp') }} </n-alert>
      <p>
        {{ config.device_profile?.preset_id }} ·
        {{ config.device_profile?.instance_name || config.device_profile?.instance_id }} ·
        {{ config.device_profile?.last_serial || t('devices.noAddress') }}
      </p>
      <n-space align="center"
        ><n-tag>{{ state.statusDisplayLabel }}</n-tag
        ><n-button
          :disabled="busy || state.locked"
          :loading="busy"
          @click="detect('preflight', null, false)"
        >
          {{ t('devices.testConfigured') }}
        </n-button></n-space
      >
      <n-alert v-if="requestError || statusError" type="error">{{
        requestError || statusError
      }}</n-alert>
      <n-alert v-if="result?.error" type="warning">{{ result.error.message }}</n-alert>
      <PerformanceSettings :observation="performanceObservation" :test-enabled="!state.locked" />
    </template>
    <template v-else>
      <div class="device-card">
        <div class="device-card-header">
          <div class="device-title-row">
            <span class="device-title">{{ state.presetTitle || t('devices.noBinding') }}</span>
            <n-tag :type="state.statusTagType" size="small" round :bordered="false">
              {{ state.statusDisplayLabel }}
            </n-tag>
            <help-text>{{ state.connectionHelp }}</help-text>
          </div>
          <div class="device-sub-row">
            <span
              v-if="
                (draft.instance_name || draft.instance_id) &&
                (draft.preset_id !== 'macos.mumu_pro' || draft.topology_fingerprint)
              "
              class="sub-item"
            >
              {{ t('devices.instancePrefix') }} {{ draft.instance_name || draft.instance_id }}
            </span>
            <span v-if="draft.last_serial" class="sub-item">
              {{ t('devices.adbPrefix') }} {{ draft.last_serial }}
            </span>
            <span class="sub-item">{{ state.hostLabel }}</span>
            <span v-if="dirty" class="sub-dirty"> {{ t('devices.dirty') }} </span>
            <span v-else-if="savedHint" class="sub-saved"> {{ t('devices.saved') }} </span>
          </div>
        </div>
      </div>

      <n-form-item
        :label-width="158"
        v-if="state.compatibilityLabel"
        :label="t('devices.compatibility')"
      >
        {{ state.compatibilityLabel }}
      </n-form-item>
      <n-form-item :label-width="158" v-if="state.discoveryLabel" :label="t('devices.discovery')">
        {{ state.discoveryLabel }}
      </n-form-item>
      <n-text v-if="state.compatibilityNote" depth="3">{{ state.compatibilityNote }}</n-text>

      <n-space class="device-actions" align="center">
        <drop-down
          v-if="state.actions.detect.options.length > 1"
          :select="selectDetect"
          :options="state.actions.detect.options"
          type="primary"
        >
          <n-button
            type="primary"
            :loading="busy"
            :disabled="state.actions.detect.disabled"
            @click="detect()"
          >
            {{ state.actions.detect.label }}
          </n-button>
        </drop-down>
        <n-button
          v-else
          type="primary"
          :loading="busy"
          :disabled="state.actions.detect.disabled"
          @click="detect()"
        >
          {{ state.actions.detect.label }}
        </n-button>
        <n-button
          v-if="state.actions.discover.visible && state.actions.detect.endpoint !== 'discover'"
          :disabled="state.actions.discover.disabled"
          @click="detect('discover')"
        >
          {{ state.actions.discover.label }}
        </n-button>

        <n-button v-if="!expanded" quaternary @click="advanced = !advanced">
          {{ advanced ? t('devices.collapseAdvanced') : t('devices.advanced') }}
        </n-button>
      </n-space>

      <n-alert v-if="state.bindingHelp" type="info" :show-icon="false" class="device-notice">
        {{ state.bindingHelp }}
      </n-alert>

      <n-alert v-if="metadata.active" :show-icon="false" class="device-notice">
        {{ t('devices.sessionLocked') }}
      </n-alert>
      <n-alert v-if="state.message" type="warning" class="device-notice" :show-icon="false">
        {{ state.message }}
      </n-alert>
      <n-alert
        v-if="state.screenshotAlternativeMessage"
        type="info"
        class="device-notice"
        :show-icon="false"
      >
        {{ state.screenshotAlternativeMessage }}
      </n-alert>
      <n-alert
        v-if="state.touchAlternativeMessage"
        type="info"
        class="device-notice"
        :show-icon="false"
      >
        {{ state.touchAlternativeMessage }}
      </n-alert>
      <n-button
        v-if="state.actions.manualFallback.visible"
        :disabled="state.actions.manualFallback.disabled"
        @click="enterManual(state.actions.manualFallback.preset, true)"
      >
        {{ state.actions.manualFallback.label }}
      </n-button>
      <n-alert v-if="state.guidance" type="info" class="device-notice" :show-icon="false">
        {{ state.guidance }}
      </n-alert>

      <n-alert
        v-if="state.actions.prepare.visible"
        type="info"
        class="device-notice"
        :show-icon="false"
      >
        <n-space vertical>
          <n-text> {{ t('devices.physicalHelp') }} </n-text>
          <n-button :disabled="state.actions.prepare.disabled" @click="prepare">
            {{ state.actions.prepare.label }}
          </n-button>
        </n-space>
      </n-alert>
      <n-alert
        v-if="state.preparationMessage"
        type="warning"
        class="device-notice"
        :show-icon="false"
      >
        {{ state.preparationMessage }}
      </n-alert>
      <n-text v-if="preparationNotice" role="status">{{ preparationNotice }}</n-text>
      <n-text v-if="manual" depth="3">
        {{ t('devices.capturePrefix') }} {{ draft.screenshot_backend }}
        {{ t('devices.touchPrefix') }} {{ draft.touch_backend }} {{ t('devices.backendSuffix') }}
      </n-text>
      <n-alert v-if="requestError" type="error" class="device-notice" :show-icon="false">
        {{ requestError }}
      </n-alert>
      <n-alert v-if="statusError" type="error" class="device-notice" :show-icon="false">
        {{ statusError }}
      </n-alert>

      <div
        v-if="state.instances?.options.length || state.fields.length || state.connectionVisible"
        class="device-fields"
      >
        <n-grid cols="1 s:2 m:2" :x-gap="14" :y-gap="6">
          <n-gi v-if="state.instances?.options.length" :span="2">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.selectInstance') }} </span>
                <help-text> {{ t('devices.selectHelp') }} </help-text>
              </template>
              <n-select
                :value="state.instances.value"
                :options="state.instances.options"
                :disabled="state.instances.disabled"
                :placeholder="t('devices.selectBound')"
                @update:value="(key) => detect('preflight', key)"
              />
            </n-form-item>
          </n-gi>

          <n-gi v-for="field in state.fields" :key="field.key" :span="field.span || 1">
            <n-form-item :label-width="158">
              <template #label>
                <span>{{ field.label }}</span>
                <help-text v-if="field.help">
                  <div style="white-space: pre-line">{{ field.help }}</div>
                </help-text>
              </template>
              <n-select
                v-if="field.kind === 'select'"
                :value="field.value || null"
                :options="field.options"
                :disabled="field.disabled"
                :tag="field.tag"
                :filterable="field.tag"
                :placeholder="field.placeholder || t('devices.selectTarget')"
                @update:value="(value) => edit(field.key, value)"
              />
              <template v-else-if="pathFields.includes(field.key)">
                <n-input
                  :value="field.value"
                  :disabled="field.disabled"
                  :placeholder="field.placeholder"
                  @update:value="(value) => edit(field.key, value)"
                />
                <n-button
                  :disabled="field.disabled"
                  class="dialog-btn"
                  @click="browsePath(field.key)"
                >
                  ...
                </n-button>
              </template>
              <n-input
                v-else
                :value="field.value"
                :disabled="field.disabled"
                :placeholder="field.placeholder"
                @update:value="(value) => edit(field.key, value)"
              />
            </n-form-item>
          </n-gi>

          <!-- 截图后端与触控后端是日常会换的选择项，且在“高级设置”之外修改即保存；
             超时、重试与老板键属于调参，仍随“高级设置”折叠。三行同处一个网格，
             行距才一致：拆成两个网格时“旋转截图”的上边距会比上面两行小。 -->
          <template v-if="state.connectionVisible">
            <n-gi v-for="field in state.connectionFields" :key="field.key" :span="field.span || 1">
              <n-form-item :label-width="158">
                <template #label>
                  <span>{{ field.label }}</span>
                  <help-text v-if="field.help">
                    <div style="white-space: pre-line">{{ field.help }}</div>
                  </help-text>
                </template>
                <n-select
                  :value="field.value || null"
                  :options="field.options"
                  :disabled="field.disabled"
                  :placeholder="field.placeholder || t('devices.selectTarget')"
                  @update:value="(value) => edit(field.key, value)"
                />
              </n-form-item>
            </n-gi>
            <n-gi v-if="draft.screenshot_backend === 'droidcast'" :span="2">
              <n-form-item :label-width="158">
                <template #label>
                  <span> {{ t('devices.rotate') }} </span>
                  <help-text> {{ t('devices.rotateHelp') }} </help-text>
                </template>
                <n-switch v-model:value="config.droidcast.rotate" :disabled="state.locked" />
              </n-form-item>
            </n-gi>
            <n-gi v-if="draft.screenshot_backend === 'custom'" :span="2">
              <n-form-item :label-width="158">
                <template #label>
                  <span> {{ t('devices.captureCommand') }} </span>
                  <help-text> {{ t('devices.captureCommandHelp') }} </help-text>
                </template>
                <n-input
                  v-model:value="config.custom_screenshot.command"
                  type="textarea"
                  :disabled="state.locked"
                  :autosize="true"
                />
              </n-form-item>
            </n-gi>
          </template>
        </n-grid>
      </div>

      <PerformanceSettings
        :observation="performanceObservation"
        :disabled="busy"
        :test-enabled="!dirty && !state.locked"
      />

      <template v-if="showAdvanced">
        <div class="advanced-divider">
          <n-divider dashed title-placement="left"> {{ t('devices.advancedBudget') }} </n-divider>
        </div>
        <n-grid cols="1 s:2 m:3" :x-gap="14" :y-gap="6">
          <n-gi v-if="draft.preset_id !== 'manual.physical'" :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.startupWait') }} </span>
                <help-text> {{ t('devices.startupWaitHelp') }} </help-text>
              </template>
              <n-input-number
                v-model:value="startupWait"
                :min="0"
                :precision="0"
                :disabled="state.locked"
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.connectionTimeout') }} </span>
                <help-text> {{ t('devices.connectionTimeoutHelp') }} </help-text>
              </template>
              <n-input-number
                :value="draft.recovery_timeout ?? 180"
                :min="10"
                :max="600"
                :step="10"
                :disabled="state.locked"
                @update:value="(v) => edit('recovery_timeout', v)"
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.attempts') }} </span>
                <help-text> {{ t('devices.attemptsHelp') }} </help-text>
              </template>
              <n-input-number
                :value="draft.recovery_attempts ?? 3"
                :min="1"
                :max="10"
                :disabled="state.locked"
                @update:value="(v) => edit('recovery_attempts', v)"
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.retryInterval') }} </span>
                <help-text> {{ t('devices.retryHelp') }} </help-text>
              </template>
              <n-input-number
                :value="draft.recovery_local_wait ?? 10"
                :min="1"
                :max="60"
                :disabled="state.locked"
                @update:value="(v) => edit('recovery_local_wait', v)"
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.shutdownTimeout') }} </span>
                <help-text> {{ t('devices.shutdownHelp') }} </help-text>
              </template>
              <n-input-number
                :value="draft.recovery_shutdown_wait ?? 30"
                :min="5"
                :max="120"
                :step="5"
                :disabled="state.locked"
                @update:value="(v) => edit('recovery_shutdown_wait', v)"
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.queryTimeout') }} </span>
                <help-text> {{ t('devices.queryHelp') }} </help-text>
              </template>
              <n-input-number
                :value="draft.manager_query_timeout ?? 10"
                :min="1"
                :max="30"
                :step="0.5"
                :disabled="state.locked"
                @update:value="(v) => edit('manager_query_timeout', v)"
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.bossDelay') }} </span>
                <help-text> {{ t('devices.bossDelayHelp') }} </help-text>
              </template>
              <n-input-number
                :value="draft.simulator_hotkey_delay ?? 3"
                :min="0.5"
                :max="30"
                :step="0.5"
                :disabled="state.locked"
                @update:value="(v) => edit('simulator_hotkey_delay', v)"
              />
            </n-form-item>
          </n-gi>
          <n-gi :span="1">
            <n-form-item :label-width="158">
              <template #label>
                <span> {{ t('devices.bossKey') }} </span>
                <help-text>
                  <div>{{ t('devices.bossHelp') }}</div>
                  <div>{{ t('devices.bossMatch') }}</div>
                  <div>{{ t('devices.bossEmpty') }}</div>
                </help-text>
              </template>
              <n-input
                :value="draft.simulator_hotkey ?? ''"
                :placeholder="t('devices.bossPlaceholder')"
                :disabled="state.locked"
                @update:value="(v) => edit('simulator_hotkey', v)"
              />
              <n-button
                class="dialog-btn"
                :disabled="state.locked || !draft.simulator_hotkey"
                :loading="testingBossKey"
                @click="testBossKey"
              >
                {{ t('devices.testBoss') }}
              </n-button>
            </n-form-item>
          </n-gi>
        </n-grid>
      </template>
    </template>
  </section>
</template>

<style scoped>
.device-settings {
  margin-bottom: 16px;
}
:deep(.n-form-item-label__text) {
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  max-width: 100%;
}
:deep(.n-form-item-label__text) .help {
  margin-left: 4px;
}
.device-card {
  padding: 12px 14px;
  background-color: rgba(128, 128, 128, 0.08);
  border-radius: 8px;
  margin-bottom: 14px;
}
.device-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.device-title {
  font-size: 15px;
  font-weight: 600;
}
.device-sub-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #888;
}
.sub-item:not(:last-child)::after {
  content: '·';
  margin-left: 8px;
}
.sub-dirty {
  color: #e6a23c;
}
.sub-saved {
  color: #18a058;
}
.device-actions {
  margin-bottom: 12px;
}
.device-notice {
  margin: 10px 0;
}
.device-fields {
  margin-top: 12px;
}
.advanced-divider {
  margin: 16px 0 8px 0;
}
</style>
