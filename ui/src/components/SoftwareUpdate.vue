<script setup>
import { i18n } from '@/i18n'
import { softwareUpdateMessage } from '@/utils/softwareUpdatePresentation'
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { NCard, useDialog, useMessage } from 'naive-ui'
import { pendingSoftwarePackage } from '@/stores/updateUpload'
import { droppedUpdateFile } from '@/utils/manualUpdate'
import {
  confirmForceUpdate,
  confirmSoftwareInstall,
  requestSoftwareUpdateCheck
} from '@/utils/softwareUpdate'
import SourceVersionManager from './SourceVersionManager.vue'
import SoftwareComponentUpdates from './SoftwareComponentUpdates.vue'
import { useUpdateProgress } from '@/composables/useUpdateProgress'
import '@/styles/updates.css'
import UpdatePreview from './UpdatePreview.vue'
import { showSoftwareUpdateDialog } from '@/utils/updateDialog'

const props = defineProps({ compact: Boolean, preview: Object })

const axios = inject('axios')
const messages = useMessage()
const dialogs = useDialog()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/software-update`
const headers = { 'X-Mower-Update': '1' }
const card = ref(null)
const info = ref(null)
const channel = ref('beta')
const background = ref(false)
const autoCheck = ref(false)
const autoUpdate = ref(false)
const checked = ref(null)
const rollbackOptions = ref([])
const rollbackVersion = ref(null)
const rollbackLoading = ref(false)
const job = ref({ status: 'idle' })
const showProgress = useUpdateProgress(job)
const busy = ref(false)
const checking = ref(false)
const error = ref('')
const disconnected = ref(false)
const cancelling = ref(false)
const progressUrl = computed(() => {
  const token = axios.defaults.headers.common.token || ''
  return `${base}/progress#${new URLSearchParams({ token }).toString()}`
})
const packageFiles = ref([])
const expandedDetails = ref([])
const uploadPercent = ref(0)
const uploading = ref(false)
const source = computed(() => info.value?.deployment === 'source')
const running = computed(() => busy.value || job.value.status === 'running')
const blocked = computed(() => !info.value || info.value.blockers.length > 0)
function channelLabel(item) {
  const key = `settings.software.${item.value}`
  return i18n.global.te(key) ? i18n.global.t(key) : item.label
}
function channelDescription(item) {
  const key = `settings.software.${item.value}Help`
  return i18n.global.te(key) ? i18n.global.t(key) : item.description
}
const channelOptions = computed(() =>
  (info.value?.channels || []).map((item) => ({
    ...item,
    label: channelLabel(item),
    disabled:
      item.value === 'dev' &&
      !source.value &&
      info.value?.platform !== 'win32' &&
      info.value?.capabilities?.dev_update !== true
  }))
)
const selectedChannel = computed(() =>
  info.value?.channels.find((item) => item.value === channel.value)
)
const pendingKey = `mower-software-update:${base}`
let timer
let disposed = false
let pendingSince = 0
let lastCheckAt = 0
let settingsRequest = Promise.resolve()
let previewCheckId = ''
defineExpose({ flushSettings: () => settingsRequest, installCheckedUpdate })

async function installCheckedUpdate(selection) {
  await settingsRequest
  await loadInfo()
  if (blocked.value) throw new Error(info.value.blockers.join('；'))
  return install(false, null, selection)
}

function saveSettings() {
  const settings = {
    channel: channel.value,
    background: background.value,
    auto_check: autoCheck.value,
    auto_update: autoUpdate.value
  }
  settingsRequest = settingsRequest
    .catch(() => {})
    .then(async () => {
      const { data } = await axios.post(`${base}/settings`, settings, { headers })
      if (!data.ok) throw new Error(data.message)
      if (settings.auto_check && !packageFiles.value.length)
        await axios.post(`${base}/auto-check`, {}, { headers })
    })
  settingsRequest.catch((err) => {
    error.value = errorMessage(err)
  })
  return settingsRequest
}

function setAutoCheck(value) {
  autoCheck.value = value
  if (!value) autoUpdate.value = false
  saveSettings()
}

function setAutoUpdate(value) {
  autoUpdate.value = value
  if (value) autoCheck.value = true
  saveSettings()
}

function showLastCheck(result) {
  if (
    checking.value ||
    !result ||
    result.channel !== channel.value ||
    (result.checked_at || 0) <= lastCheckAt
  )
    return
  lastCheckAt = result.checked_at
  if (result.ok) {
    checked.value = result
    error.value = ''
  } else if (result.message) {
    checked.value = null
    error.value = result.message
  }
}

function errorMessage(err) {
  return (
    err.response?.data?.message ||
    err.message ||
    i18n.global.t('settings.software.operationFailedPleaseTryAgain')
  )
}

function selectSoftwarePackage(file) {
  if (running.value) {
    error.value = i18n.global.t('settings.software.anUpdateIsInProgressWaitFor')
    return
  }
  packageFiles.value = [{ id: 'release-upload', name: file.name, status: 'pending', file }]
  if (!expandedDetails.value.includes('manual')) expandedDetails.value.push('manual')
}

function dropSoftwarePackage(event) {
  try {
    selectSoftwarePackage(droppedUpdateFile(event))
  } catch (err) {
    messages.error(err.message)
  }
}

async function loadInfo() {
  const { data } = await axios.get(`${base}/info`)
  if (!data.ok) throw new Error(data.message)
  if (!info.value) {
    channel.value = data.settings.channel
    background.value = data.settings.background
    autoCheck.value = data.settings.auto_check
    autoUpdate.value = data.settings.auto_update
  }
  info.value = data
  showLastCheck(data.last_check)
}

async function poll() {
  if (disposed) return
  try {
    const { data } = await axios.get(`${base}/status`, { timeout: 5000 })
    if (disposed) return
    if (!data.ok) throw new Error(data.message)
    if (job.value.id !== data.id || data.status !== 'running') cancelling.value = false
    job.value = data
    showLastCheck(data.last_check)
    disconnected.value = false
    if (data.status === 'running' && !pendingSince) pendingSince = Date.now()
    const pending = sessionStorage.getItem(pendingKey)
    if (
      pending &&
      pending === data.id &&
      ['succeeded', 'failed', 'cancelled'].includes(data.status)
    ) {
      sessionStorage.removeItem(pendingKey)
      if (
        data.status === 'succeeded' &&
        showProgress.value &&
        (info.value?.capabilities?.silent_restart !== false || data.restarted === true)
      ) {
        window.location.reload()
        return
      }
      await loadInfo()
    }
  } catch {
    disconnected.value = true
  }
  if (disposed) return
  // Keep retrying through backend shutdown, but do not spin forever after a crash.
  if (pendingSince && Date.now() - pendingSince > 45 * 60 * 1000) return
  timer = setTimeout(poll, 2000)
}

async function checkUpdate() {
  checking.value = true
  checked.value = null
  error.value = ''
  try {
    await settingsRequest
    await loadInfo()
    const data = await requestSoftwareUpdateCheck(axios, channel.value)
    checked.value = data
    lastCheckAt = data.checked_at || Date.now() / 1000
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    checking.value = false
  }
}

async function loadRollbackOptions() {
  const requestedChannel = channel.value
  rollbackLoading.value = true
  rollbackOptions.value = []
  rollbackVersion.value = null
  error.value = ''
  try {
    const { data } = await axios.get(`${base}/release/rollback-options`, {
      params: { channel: requestedChannel }
    })
    if (!data.ok) throw new Error(data.message)
    if (channel.value !== requestedChannel) return
    rollbackOptions.value = data.options.map((item) => ({
      label: item.version,
      value: item.version
    }))
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    rollbackLoading.value = false
  }
}

async function requestRollback() {
  if (!rollbackVersion.value || running.value || rollbackLoading.value || blocked.value) return
  const requestedChannel = channel.value
  const requestedVersion = rollbackVersion.value
  rollbackLoading.value = true
  error.value = ''
  try {
    await settingsRequest
    const { data } = await axios.post(
      `${base}/release/rollback-check`,
      { channel: requestedChannel, version: requestedVersion },
      { headers }
    )
    if (!data.ok) throw new Error(data.message)
    if (channel.value !== requestedChannel || rollbackVersion.value !== requestedVersion) return
    confirmSoftwareInstall(
      dialogs,
      info.value.version,
      data,
      info.value.instances.length,
      (confirmed) => install(false, null, confirmed)
    )
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    rollbackLoading.value = false
  }
}

async function requestInstall(manual = false) {
  if (running.value || (!manual && checking.value) || blocked.value) return
  let selection
  if (manual) {
    const file = packageFiles.value[0]?.file
    if (!file) return
    busy.value = true
    uploading.value = true
    uploadPercent.value = 0
    error.value = ''
    try {
      const form = new FormData()
      form.append('file', file)
      const { data } = await axios.post(`${base}/manual/inspect`, form, {
        headers,
        onUploadProgress: (event) => {
          if (event.total) uploadPercent.value = Math.round((event.loaded / event.total) * 100)
        }
      })
      if (!data.ok) throw new Error(data.message)
      if (disposed) {
        discardPreview(data.check_id)
        return
      }
      selection = data
      previewCheckId = data.check_id
    } catch (err) {
      error.value = errorMessage(err)
      return
    } finally {
      busy.value = false
      uploading.value = false
    }
  } else {
    // Automatic checks are shared across instances without an in-memory check ID.
    // Resolve a fresh target before asking the user to confirm that target.
    if (!checked.value?.check_id) await checkUpdate()
    if (!checked.value?.available || !checked.value?.check_id) return
    selection = { ...checked.value }
    await settingsRequest
    showSoftwareUpdateDialog(dialogs, info.value, selection)
    return
  }
  confirmSoftwareInstall(
    dialogs,
    info.value.version,
    selection,
    info.value.instances.length,
    (confirmed) => {
      previewCheckId = ''
      return install(false, null, confirmed)
    },
    () => discardPreview(selection.manual ? selection.check_id : '')
  )
}

function discardPreview(checkId) {
  if (!checkId) return
  if (previewCheckId === checkId) previewCheckId = ''
  return axios.post(`${base}/manual/discard`, { check_id: checkId }, { headers }).catch(() => {})
}

async function install(force = false, target = null, selection = {}) {
  if (running.value) return
  busy.value = true
  error.value = ''
  uploadPercent.value = 0
  try {
    await settingsRequest
    const response = await axios.post(
      `${base}/start`,
      {
        check_id: (target || selection).check_id,
        background: background.value,
        force,
        confirm_downgrade: selection.confirm_downgrade === true
      },
      { headers }
    )
    if (!response.data.ok) throw new Error(response.data.message)
    if (target) {
      autoUpdate.value = false
      if (!target.source_pr) channel.value = 'dev'
    }
    sessionStorage.setItem(pendingKey, response.data.id)
    pendingSince = Date.now()
    cancelling.value = false
    job.value = { ...response.data, status: 'running', phase: 'preparing', cancellable: true }
    clearTimeout(timer)
    await poll()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    if (selection.manual) discardPreview(selection.check_id)
    busy.value = false
  }
}

async function cancelUpdate() {
  if (!job.value.cancellable || cancelling.value) return
  cancelling.value = true
  try {
    const { data } = await axios.post(
      `${base}/cancel`,
      { id: job.value.id },
      { headers, timeout: 5000 }
    )
    if (!data.ok) throw new Error(data.message)
    messages.info(data.message)
  } catch (err) {
    cancelling.value = false
    error.value = errorMessage(err)
  }
}

async function requestForceUpdate() {
  if (!info.value?.force_supported || running.value || checking.value || !checked.value) return
  if (!checked.value.check_id) await checkUpdate()
  if (!checked.value?.check_id) return
  const selection = { ...checked.value, force: true }
  confirmForceUpdate(dialogs, selection.version, info.value.instances.length, () =>
    install(true, null, selection)
  )
}

watch(channel, () => {
  checked.value = null
  rollbackOptions.value = []
  rollbackVersion.value = null
  lastCheckAt = 0
})
watch(
  [info, () => packageFiles.value[0]?.file],
  async ([currentInfo, file]) => {
    if (!currentInfo || !file) return
    await nextTick()
    card.value?.$el?.querySelector('.update-manual')?.scrollIntoView({ block: 'nearest' })
  },
  { flush: 'post' }
)
watch(
  pendingSoftwarePackage,
  (file) => {
    if (!file || props.compact) return
    selectSoftwarePackage(file)
    pendingSoftwarePackage.value = null
  },
  { immediate: true }
)
onMounted(async () => {
  try {
    await loadInfo()
    if (!props.compact && autoCheck.value && !packageFiles.value.length)
      await axios.post(`${base}/auto-check`, {}, { headers })
  } catch (err) {
    error.value = errorMessage(err)
  }
  await poll()
})
onUnmounted(() => {
  disposed = true
  discardPreview(previewCheckId)
  clearTimeout(timer)
})
</script>

<template>
  <component
    :is="compact ? 'div' : NCard"
    :id="compact ? undefined : 'software-update'"
    ref="card"
    :title="compact ? undefined : i18n.global.t('settings.software.softwareUpdates')"
    class="update-card"
  >
    <UpdatePreview v-if="compact" v-bind="preview" />
    <div v-if="!compact" class="update-overview">
      <div class="update-installed">
        <span
          class="update-caption"
          :data-settings-label="i18n.global.t('settings.software.currentVersion')"
          >{{ i18n.global.t('settings.software.currentVersion') }}</span
        >
        <strong class="update-version">{{
          info?.version || i18n.global.t('settings.software.loading')
        }}</strong>
        <span v-if="info" class="update-caption">{{
          source
            ? i18n.global.t('settings.software.sourceDeployment')
            : i18n.global.t('settings.software.standaloneRelease')
        }}</span>
      </div>
      <div class="update-actions">
        <n-button :loading="checking" :disabled="running" @click="checkUpdate">
          {{ i18n.global.t('settings.software.checkForUpdates') }}
        </n-button>
        <n-button
          v-if="checked?.available"
          type="primary"
          :disabled="blocked || running || checking"
          :loading="busy"
          @click="requestInstall(false)"
        >
          {{ i18n.global.t('settings.software.downloadInstall') }}
        </n-button>
      </div>
    </div>
    <div
      v-if="!compact"
      class="update-status"
      role="status"
      :data-settings-label="i18n.global.t('settings.software.latestVersion')"
    >
      <template v-if="checking">{{
        i18n.global.t('settings.software.checkingTheLatestVersionInTheSelected')
      }}</template>
      <template v-else-if="checked">
        <n-tag v-if="checked.available" size="small" :bordered="false" type="warning">
          {{ i18n.global.t('settings.software.updateAvailable') }}
        </n-tag>
        <n-tag v-else size="small" :bordered="false" type="success">{{
          i18n.global.t('settings.software.matchesSelectedChannel')
        }}</n-tag>
        <span v-if="checked.version"
          >{{ i18n.global.t('settings.software.latestVersion') }}
          <span class="update-version-value">{{ checked.version }}</span></span
        >
        <span v-if="checked.message" class="update-caption">{{ checked.message }}</span>
      </template>
      <span v-else class="update-caption">{{
        i18n.global.t('settings.software.checkForUpdatesToFindTheLatest')
      }}</span>
    </div>

    <n-alert
      v-if="error"
      type="error"
      :title="i18n.global.t('settings.software.operationIncomplete')"
      role="alert"
      >{{ error }}</n-alert
    >
    <n-alert
      v-if="info?.blockers.length"
      type="warning"
      :title="i18n.global.t('settings.software.thisInstallationNeedsAttention')"
    >
      <p v-for="message in info.blockers" :key="message">{{ message }}</p>
    </n-alert>

    <div v-if="showProgress || disconnected" class="update-progress" aria-live="polite">
      <n-progress
        v-if="showProgress"
        type="line"
        :percentage="job.progress ?? 100"
        :show-indicator="job.progress != null"
        :processing="job.status === 'running' && !disconnected"
        :status="
          job.status === 'failed'
            ? 'error'
            : job.status === 'cancelled'
              ? 'warning'
              : job.status === 'succeeded'
                ? 'success'
                : 'default'
        "
      />
      <p v-if="showProgress">{{ softwareUpdateMessage(job.message) }}</p>
      <p v-if="showProgress && job.current" class="update-caption">
        {{ i18n.global.t('settings.software.downloaded') }}
        {{ (job.current / 1048576).toFixed(1) }} MiB<span v-if="job.total">
          / {{ (job.total / 1048576).toFixed(1) }} MiB</span
        >
      </p>
      <p v-if="disconnected">
        {{ i18n.global.t('settings.software.theUpdateServiceIsHandingOverReconnecting') }}
      </p>
      <div v-if="showProgress && !compact" class="update-actions">
        <n-button
          size="small"
          tag="a"
          :href="progressUrl"
          target="_blank"
          rel="noopener noreferrer"
          >{{ i18n.global.t('settings.software.openUpdateProgress') }}</n-button
        >
        <n-button
          v-if="job.status === 'running'"
          size="small"
          :disabled="!job.cancellable || cancelling"
          :loading="cancelling"
          @click="cancelUpdate"
          >{{ i18n.global.t('settings.software.cancelUpdate') }}</n-button
        >
      </div>
      <n-collapse v-if="!compact && showProgress && (job.log || job.log_path)">
        <n-collapse-item :title="i18n.global.t('settings.software.installationLog')" name="log">
          <p v-if="job.log_path" class="update-caption">
            {{ i18n.global.t('settings.software.log') }}{{ job.log_path }}
          </p>
          <pre v-if="job.log" class="update-notes">{{ job.log }}</pre>
        </n-collapse-item>
      </n-collapse>
    </div>

    <n-form
      v-if="!compact"
      class="update-preferences"
      :show-feedback="false"
      label-placement="left"
    >
      <n-form-item class="update-channel">
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.software.updateChannel') }}</span>
            <span v-if="selectedChannel" class="settings-row-description">{{
              channelDescription(selectedChannel)
            }}</span>
          </span>
        </template>
        <n-select
          v-model:value="channel"
          :consistent-menu-width="false"
          size="small"
          :options="channelOptions"
          :disabled="running || checking || !info"
          :input-props="{ 'aria-label': i18n.global.t('settings.software.updateChannel') }"
          @update:value="saveSettings"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.software.automaticallyCheckForUpdates') }}</span>
            <span class="settings-row-description">{{
              i18n.global.t('settings.software.checkTheSelectedSoftwareChannelWhenMower')
            }}</span>
          </span>
        </template>
        <n-switch
          :value="autoCheck"
          :disabled="!info || running"
          :aria-label="i18n.global.t('settings.software.automaticallyCheckForUpdates')"
          @update:value="setAutoCheck"
        />
      </n-form-item>
      <n-form-item v-if="info?.capabilities?.auto_update !== false">
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.software.automaticallyUpdate') }}</span>
            <span class="settings-row-description">{{
              i18n.global.t('settings.software.installADifferentVersionFromTheSelected')
            }}</span>
          </span>
        </template>
        <n-switch
          :value="autoUpdate"
          :disabled="!info || running"
          :aria-label="i18n.global.t('settings.software.automaticallyUpdate')"
          @update:value="setAutoUpdate"
        />
      </n-form-item>
      <n-form-item v-if="info?.capabilities?.silent_restart !== false">
        <template #label>
          <span class="settings-row-copy">
            <span>{{ i18n.global.t('settings.software.restartSilentlyAfterUpdates') }}</span>
            <span class="settings-row-description">{{
              background
                ? i18n.global.t('settings.software.keepRunningInTheBackgroundWithoutOpening')
                : i18n.global.t('settings.software.openTheWindowNormallyAfterRestarting')
            }}</span>
          </span>
        </template>
        <n-switch
          v-model:value="background"
          :disabled="running || !info"
          :aria-label="i18n.global.t('settings.software.restartSilentlyAfterUpdates')"
          @update:value="saveSettings"
        />
      </n-form-item>
    </n-form>
    <p v-if="!compact && info?.capabilities?.silent_restart !== false" class="update-footnote">
      {{ i18n.global.t('settings.software.softwareUpdatesRestartAllRunningInstancesIn') }}
    </p>

    <n-collapse
      v-if="!compact"
      class="update-details"
      :expanded-names="expandedDetails"
      @update:expanded-names="expandedDetails = $event"
    >
      <n-collapse-item
        :title="i18n.global.t('settings.software.updateChannelsReleaseNotes')"
        name="channels"
      >
        <p v-for="item in info?.channels || []" :key="item.value">
          <strong>{{ channelLabel(item) }}</strong
          >: {{ channelDescription(item) }}
        </p>
        <p>
          <a
            :href="
              checked?.url ||
              info?.releases_url ||
              'https://github.com/ArkMowers/arknights-mower/releases'
            "
            target="_blank"
            rel="noopener noreferrer"
            >{{ i18n.global.t('settings.software.viewReleases') }}</a
          >
        </p>
        <pre v-if="checked?.notes" class="update-notes">{{ checked.notes }}</pre>
      </n-collapse-item>
      <n-collapse-item
        v-if="!source"
        id="software-update-manual"
        :title="i18n.global.t('settings.software.updateFromALocalPackage')"
        name="manual"
        :data-settings-label="i18n.global.t('settings.software.updateFromALocalPackage')"
      >
        <div v-if="info" class="update-manual">
          <n-upload
            v-model:file-list="packageFiles"
            :default-upload="false"
            :max="1"
            :disabled="running"
          >
            <n-upload-dragger @dragover.prevent @drop.capture.stop.prevent="dropSoftwarePackage">
              <div>
                {{
                  info.manual_label ||
                  (info.manual_ota_supported
                    ? i18n.global.t('settings.software.clickOrDropAReleasePackageOr')
                    : i18n.global.t('settings.software.clickOrDropAReleasePackage'))
                }}
              </div>
              <p class="update-caption">
                {{
                  info.manual_hint ||
                  (info.manual_ota_supported
                    ? i18n.global.t('settings.software.theOtaPatchMustStartFromThe')
                    : i18n.global.t('settings.software.versionDetailsAreReadFromThePackage'))
                }}
              </p>
            </n-upload-dragger>
          </n-upload>
          <template v-if="uploading">
            <n-progress
              type="line"
              :percentage="uploadPercent < 100 ? uploadPercent : undefined"
              processing
            />
            <span class="update-caption">{{
              uploadPercent < 100
                ? i18n.global.t('settings.software.uploadingPackage')
                : i18n.global.t('settings.software.readingPackageVersion')
            }}</span>
          </template>
          <n-button
            v-if="packageFiles[0]?.file"
            size="small"
            type="primary"
            :disabled="blocked || running"
            :loading="busy"
            @click="requestInstall(true)"
            >{{ info.install_label || i18n.global.t('settings.software.installRestart') }}</n-button
          >
          <p v-if="info.platform === 'darwin'" class="update-caption">
            {{ i18n.global.t('settings.software.ifMacosBlocksStartupAfterAnUpdate') }}
          </p>
        </div>
      </n-collapse-item>
      <n-collapse-item
        v-if="info?.rollback_supported"
        :title="i18n.global.t('settings.software.rollBackToAnEarlierVersion')"
        name="rollback"
        :data-settings-label="i18n.global.t('settings.software.versionRollback')"
      >
        <p class="update-caption">
          {{ i18n.global.t('settings.software.chooseFromTheThreeMostRecentCompatible') }}
        </p>
        <div class="update-rollback">
          <n-button
            size="small"
            :loading="rollbackLoading"
            :disabled="running || checking"
            @click="loadRollbackOptions"
            >{{ i18n.global.t('settings.software.findRollbackVersions') }}</n-button
          >
          <n-select
            v-model:value="rollbackVersion"
            :consistent-menu-width="false"
            size="small"
            :placeholder="i18n.global.t('settings.software.selectAnEarlierVersion')"
            :options="rollbackOptions"
            :disabled="running || rollbackLoading || !rollbackOptions.length"
            :input-props="{
              'aria-label': i18n.global.t('settings.software.rollbackTargetVersion')
            }"
          />
          <n-button
            size="small"
            type="warning"
            :disabled="blocked || running || rollbackLoading || !rollbackVersion"
            @click="requestRollback"
            >{{ i18n.global.t('settings.software.rollBackInstall') }}</n-button
          >
        </div>
      </n-collapse-item>
      <n-collapse-item
        v-if="source"
        :title="i18n.global.t('settings.software.forceUpdate')"
        name="force"
      >
        <p class="update-caption">
          {{ i18n.global.t('settings.software.aForcedUpdateOverwritesLocalSourceChanges') }}
        </p>
        <n-button
          size="small"
          type="warning"
          :disabled="!info?.force_supported || running || checking || !checked"
          :loading="busy"
          @click="requestForceUpdate"
          >{{ i18n.global.t('settings.software.forceUpdate') }}</n-button
        >
      </n-collapse-item>
    </n-collapse>
    <SourceVersionManager
      v-if="!compact && source"
      :initial-branch="info.settings.source_branch"
      :initial-remote="info.settings.source_remote"
      :remotes="info.source_remotes"
      :running="running || checking"
      :blocked="blocked"
      :force-supported="info.force_supported"
      :instance-count="info.instances.length"
      @install="(target) => install(target.force, target)"
    />
    <SoftwareComponentUpdates
      v-for="component in compact ? [] : info?.component_updates || []"
      :key="component.endpoint"
      :component="component"
      :disabled="running"
    />
  </component>
</template>
