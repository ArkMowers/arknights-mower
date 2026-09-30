<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'
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

const config = useConfigStore()
const axios = inject('axios')
const dialog = useDialog()
const message = useMessage()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/device`
const draft = ref({ ...config.device_profile })
const metadata = ref({})
const result = ref(null)
const busy = ref(false)
const advanced = ref(false)
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
    advanced: advanced.value,
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
  } catch (error) {
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

function flashSaved() {
  savedHint.value = true
  clearTimeout(savedHintTimer)
  savedHintTimer = setTimeout(() => {
    savedHint.value = false
  }, 2400)
}

function edit(key, value) {
  if (state.value.locked) return
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
      message?.success(response.data.message || '已触发模拟器老板键')
    } else {
      message?.warning(response.data?.message || '未能触发模拟器老板键')
    }
  } catch (error) {
    message?.error(error.response?.data?.message || error.message || '触发模拟器老板键失败')
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
    if (!disposed)
      statusError.value = error.response?.data?.message || '无法读取设备会话状态，请重试'
  } finally {
    readingStatus = false
  }
}

async function acceptPreflight(data) {
  result.value = data
  if (data.host_platform) metadata.value.host_platform = data.host_platform
  if (data.preset_id && data.preset_id !== draft.value.preset_id) dirty.value = true
  draft.value = deviceDetectionDraft(draft.value, data)
  if (!data.ok) return
  draft.value = await savePreflightDevice({ config, profile: draft.value, result: data })
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
  requestError.value = ''
  try {
    await config.flush_config_saves()
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
    else requestError.value = detail?.message || error.message || '设备检测失败，请重试'
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
      requestError.value = detail?.message || error.message || '启动并测试连接失败，请重试'
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
    title: '授权本次临时尺寸覆盖',
    content: `保存并启动实体设备 ${action.serial}。本次运行允许 mower 临时修改该设备的显示尺寸，并验证横屏 1920×1080。结束、取消或失败时恢复原尺寸；离线时保留恢复记录，重连后先恢复。若其他程序修改了尺寸，将停止并提示恢复冲突。此授权不会保存到下次运行。`,
    positiveText: '授权本次并启动',
    negativeText: '取消',
    onPositiveClick: async () => {
      if (
        state.value.locked ||
        !sameDeviceProfile(draft.value, profile) ||
        confirmedPackage.value !== packageChoice
      ) {
        requestError.value = '设备设置已变化，请重新确认本次授权。'
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
        preparationNotice.value = `已发起 ${action.serial} 的本次整备启动，请查看连接状态与运行日志。`
      } catch (error) {
        requestError.value = error.response?.data?.message || error.message || '临时整备启动失败'
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

onMounted(() => {
  updateStatusPolling()
  document.addEventListener('visibilitychange', updateStatusPolling)
})
onUnmounted(() => {
  disposed = true
  document.removeEventListener('visibilitychange', updateStatusPolling)
  clearInterval(timer)
  clearTimeout(savedHintTimer)
})
</script>

<template>
  <section class="device-settings" aria-label="设备连接">
    <div class="device-card">
      <div class="device-card-header">
        <div class="device-title-row">
          <span class="device-title">{{ state.presetTitle || '尚未绑定设备' }}</span>
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
            实例：{{ draft.instance_name || draft.instance_id }}
          </span>
          <span v-if="draft.last_serial" class="sub-item"> ADB 地址：{{ draft.last_serial }} </span>
          <span class="sub-item">{{ state.hostLabel }}</span>
          <span v-if="dirty" class="sub-dirty">（已修改，测试连接后保存）</span>
          <span v-else-if="savedHint" class="sub-saved">（设置已保存）</span>
        </div>
      </div>
    </div>

    <n-form-item :label-width="158" v-if="state.compatibilityLabel" label="兼容层级">
      {{ state.compatibilityLabel }}
    </n-form-item>
    <n-form-item :label-width="158" v-if="state.discoveryLabel" label="发现能力">
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

      <n-button quaternary @click="advanced = !advanced">
        {{ advanced ? '收起高级设置' : '高级设置' }}
      </n-button>
    </n-space>

    <n-alert v-if="state.bindingHelp" type="info" :show-icon="false" class="device-notice">
      {{ state.bindingHelp }}
    </n-alert>

    <n-alert v-if="metadata.active" :show-icon="false" class="device-notice">
      设备会话运行中，目标与后端设置已锁定。其他设置仍可保存。
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
        <n-text>
          默认只检查显示尺寸。临时整备只授权本次运行，结束时确认尺寸仍为 mower 写入值后还原。
          请先将设备手动切到横屏；mower 不修改旋转、密度或导航栏。
        </n-text>
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
      当前截图：{{ draft.screenshot_backend }}；触控：{{
        draft.touch_backend
      }}。可在下方“连接与恢复”修改。
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
              <span>选择实例</span>
              <help-text>从当前主机上检测到的模拟器列表中，选择要绑定的目标实例。</help-text>
            </template>
            <n-select
              :value="state.instances.value"
              :options="state.instances.options"
              :disabled="state.instances.disabled"
              placeholder="请选择要绑定的模拟器实例"
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
              :placeholder="field.placeholder || '请选择明确目标'"
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
                :placeholder="field.placeholder || '请选择明确目标'"
                @update:value="(value) => edit(field.key, value)"
              />
            </n-form-item>
          </n-gi>
          <n-gi v-if="draft.screenshot_backend === 'droidcast'" :span="2">
            <n-form-item :label-width="158">
              <template #label>
                <span>旋转截图</span>
                <help-text>部分模拟器横屏画面可能出现 180 度颠倒，开启后自动纠正旋转。</help-text>
              </template>
              <n-switch v-model:value="config.droidcast.rotate" :disabled="state.locked" />
            </n-form-item>
          </n-gi>
          <n-gi v-if="draft.screenshot_backend === 'custom'" :span="2">
            <n-form-item :label-width="158">
              <template #label>
                <span>截图命令</span>
                <help-text>向 STDOUT 打印图像原始数据的自定义命令行。</help-text>
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

    <template v-if="advanced">
      <div class="advanced-divider">
        <n-divider dashed title-placement="left">超时保护与高级控制</n-divider>
      </div>
      <n-grid cols="1 s:2 m:3" :x-gap="14" :y-gap="6">
        <n-gi v-if="draft.preset_id !== 'manual.physical'" :span="1">
          <n-form-item :label-width="158">
            <template #label>
              <span>启动保护时间 (秒)</span>
              <help-text>
                模拟器启动后，在这段时间内等待设备就绪，不再次自动重启。设备提前就绪即可继续；等待仍受连接超时限制。保留原“模拟器启动时间”设置的值。
              </help-text>
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
              <span>连接超时 (秒)</span>
              <help-text>
                开始连接设备（或中途掉线尝试恢复）时，从模拟器启动、建立连接到异常重试全过程允许的最大总等待时间（超时后终止本次连接流程，避免无限等待）。
              </help-text>
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
              <span>最大重试次数</span>
              <help-text> ADB 断连或设备异常时的最大重试轮次。 </help-text>
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
              <span>重试间隔 (秒)</span>
              <help-text> 每次发送重连指令后等待设备重新响应的时间。 </help-text>
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
              <span>关停上限 (秒)</span>
              <help-text>
                执行模拟器完整重启时，等待模拟器进程及多开实例完全退出停止的最长时间。若超过该时间仍未退出，则取消本次重启以保护环境。
              </help-text>
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
              <span>状态检测超时 (秒)</span>
              <help-text>
                检测多开实例运行状态（如是否已启动/已停止）时的单次最大等待时间。若多开较多或模拟器卡顿导致频繁误报未响应，可适当调大。
              </help-text>
            </template>
            <n-input-number
              :value="draft.manager_query_timeout ?? 3"
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
              <span>老板键延迟 (秒)</span>
              <help-text>
                启动模拟器后，等待窗口完全显示再按下老板键的延时时间。电脑性能较好或冷启动较快可设为
                1~2 秒；若启动较慢导致老板键未生效，可适当调大。
              </help-text>
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
              <span>模拟器老板键</span>
              <help-text>
                <div>启动模拟器后自动触发此快捷键以隐藏窗口。</div>
                <div>请先在模拟器自身设置中配置相同的老板键（如 alt+q、ctrl+alt+w）。</div>
                <div>若不需要此功能，请留空；组合键用“+”连接，不要空格。</div>
              </help-text>
            </template>
            <n-input
              :value="draft.simulator_hotkey ?? ''"
              placeholder="留空表示不启用（如 alt+q、ctrl+alt+w）"
              :disabled="state.locked"
              @update:value="(v) => edit('simulator_hotkey', v)"
            />
            <n-button
              class="dialog-btn"
              :disabled="state.locked || !draft.simulator_hotkey"
              :loading="testingBossKey"
              @click="testBossKey"
            >
              测试老板键
            </n-button>
          </n-form-item>
        </n-gi>
      </n-grid>
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
