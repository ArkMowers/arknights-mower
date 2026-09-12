<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { pendingSoftwarePackage } from '@/stores/updateUpload'
import { droppedUpdateFile } from '@/utils/manualUpdate'
import { confirmForceUpdate, confirmSoftwareInstall } from '@/utils/softwareUpdate'
import SourceVersionManager from './SourceVersionManager.vue'
import SoftwareComponentUpdates from './SoftwareComponentUpdates.vue'
import { useUpdateProgress } from '@/composables/useUpdateProgress'

const axios = inject('axios')
const messages = useMessage()
const dialogs = useDialog()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/software-update`
const headers = { 'X-Mower-Update': '1' }
const card = ref(null)
const info = ref(null)
const channel = ref('beta')
const background = ref(true)
const autoCheck = ref(false)
const autoUpdate = ref(false)
const checked = ref(null)
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
const uploadPercent = ref(0)
const uploading = ref(false)
const source = computed(() => info.value?.deployment === 'source')
const running = computed(() => busy.value || job.value.status === 'running')
const blocked = computed(() => !info.value || info.value.blockers.length > 0)
const channelOptions = computed(() =>
  (info.value?.channels || []).map((item) => ({
    ...item,
    disabled: item.value === 'dev' && !source.value
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
defineExpose({ flushSettings: () => settingsRequest })

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
  return err.response?.data?.message || err.message || '操作失败，请重试'
}

function selectSoftwarePackage(file) {
  nextTick(() => card.value?.$el?.scrollIntoView({ block: 'center' }))
  if (running.value) {
    error.value = '正在更新，请等待当前任务完成'
    return
  }
  packageFiles.value = [{ id: 'release-upload', name: file.name, status: 'pending', file }]
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
      if (data.status === 'succeeded' && showProgress.value) {
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
    const { data } = await axios.post(`${base}/check`, { channel: channel.value }, { headers })
    if (!data.ok) throw new Error(data.message)
    checked.value = data
    lastCheckAt = data.checked_at || Date.now() / 1000
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    checking.value = false
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
  if (selection.downgrade) {
    confirmSoftwareInstall(
      dialogs,
      info.value.version,
      selection,
      info.value.instances.length,
      (confirmed) => install(true, null, confirmed)
    )
    return
  }
  confirmForceUpdate(dialogs, selection.version, info.value.instances.length, () =>
    install(true, null, selection)
  )
}

watch(channel, () => {
  checked.value = null
  lastCheckAt = 0
})
watch(
  pendingSoftwarePackage,
  (file) => {
    if (!file) return
    selectSoftwarePackage(file)
    pendingSoftwarePackage.value = null
  },
  { immediate: true }
)
onMounted(async () => {
  try {
    await loadInfo()
    if (autoCheck.value && !packageFiles.value.length)
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
  <n-card id="software-update" ref="card" title="软件更新">
    <n-form :show-feedback="false" label-placement="left" label-width="72">
      <n-form-item :show-label="false">
        <n-checkbox :checked="autoCheck" :disabled="!info || running" @update:checked="setAutoCheck"
          >自动检查更新</n-checkbox
        >
        <span class="hint">打开 Mower 时检查所选渠道的软件更新</span>
      </n-form-item>
      <n-form-item v-if="info?.capabilities?.auto_update !== false" :show-label="false">
        <n-checkbox
          :checked="autoUpdate"
          :disabled="!info || running"
          @update:checked="setAutoUpdate"
          >自动更新</n-checkbox
        >
        <span class="hint">升级自动安装并重启全部实例；回退需点击安装并确认</span>
      </n-form-item>
      <n-form-item v-if="info?.capabilities?.silent_restart !== false" :show-label="false">
        <div class="restart-option">
          <n-checkbox
            v-model:checked="background"
            :disabled="running || !info"
            @update:checked="saveSettings"
          >
            更新后后台静默重启
          </n-checkbox>
          <span class="hint">{{
            background ? '不打开窗口，在后台运行' : '重启后正常打开窗口'
          }}</span>
        </div>
      </n-form-item>
      <n-form-item label="当前版本">
        <div class="version-row">
          <span class="version">{{ info?.version || '—' }}</span>
          <span v-if="info" class="hint">（{{ source ? '源码部署' : 'Release 独立包' }}）</span>
        </div>
      </n-form-item>
      <n-form-item label="最新版本">
        <div class="version-row">
          <span class="version">{{ checked?.version || '—' }}</span>
          <n-tag v-if="checked?.available === true" type="warning">{{
            checked.downgrade ? '可回退' : '可更新'
          }}</n-tag>
          <n-tag v-else-if="checked?.available === false" type="success">已与渠道一致</n-tag>
        </div>
      </n-form-item>
      <n-form-item label="更新渠道">
        <n-select
          v-model:value="channel"
          size="small"
          :options="channelOptions"
          :disabled="running || checking || !info"
          :input-props="{ 'aria-label': '更新渠道' }"
          @update:value="saveSettings"
        />
      </n-form-item>
      <n-form-item v-if="selectedChannel" :show-label="false">
        <span class="hint">{{ selectedChannel.description }}</span>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-space>
          <n-button size="small" :loading="checking" :disabled="running" @click="checkUpdate">
            检查更新
          </n-button>
          <n-button
            size="small"
            type="primary"
            :disabled="blocked || running || checking || !checked?.available"
            :loading="busy"
            @click="requestInstall(false)"
          >
            {{ checked?.downgrade ? '回退并安装' : '下载并安装' }}
          </n-button>
          <n-button
            v-if="source"
            size="small"
            type="warning"
            :disabled="!info?.force_supported || running || checking || !checked"
            :loading="busy"
            @click="requestForceUpdate"
          >
            强制更新
          </n-button>
        </n-space>
      </n-form-item>
      <n-form-item v-if="checked?.message" :show-label="false">
        <span>{{ checked.message }}</span>
      </n-form-item>
      <n-form-item v-if="error" :show-label="false">
        <n-alert type="error" title="操作未完成" role="alert">{{ error }}</n-alert>
      </n-form-item>
      <n-form-item v-if="info?.blockers.length" :show-label="false">
        <n-alert type="warning" title="当前安装需要先处理">
          <p v-for="message in info.blockers" :key="message">{{ message }}</p>
        </n-alert>
      </n-form-item>
      <n-form-item v-if="info?.capabilities?.silent_restart !== false" :show-label="false">
        <span class="hint"
          >更新后重启同一安装目录下所有运行实例；原本运行中的任务重置运行缓存后重新开始。在线更新与上传安装均使用上方的重启方式。</span
        >
      </n-form-item>
      <n-form-item v-if="source" :show-label="false">
        <SourceVersionManager
          :initial-branch="info.settings.source_branch"
          :initial-remote="info.settings.source_remote"
          :remotes="info.source_remotes"
          :running="running || checking"
          :blocked="blocked"
          :force-supported="info.force_supported"
          :instance-count="info.instances.length"
          @install="(target) => install(target.force, target)"
        />
      </n-form-item>
      <SoftwareComponentUpdates
        v-for="component in info?.component_updates || []"
        :key="component.endpoint"
        :component="component"
        :disabled="running"
      />
      <n-form-item label="手动应用">
        <span v-if="source" class="hint"
          >Release 安装包用于独立包部署，源码部署请使用上方在线更新。</span
        >
        <n-space v-else-if="info" vertical class="manual-upload" :size="8">
          <n-upload
            v-model:file-list="packageFiles"
            :default-upload="false"
            :max="1"
            :disabled="running"
          >
            <n-upload-dragger @dragover.prevent @drop.capture.stop.prevent="dropSoftwarePackage">
              <div>{{ info.manual_label || '点击或拖入 Release 安装包' }}</div>
              <div class="hint">
                {{ info.manual_hint || '离线读取包内版本并校验完整性，文件名可任意修改' }}
              </div>
            </n-upload-dragger>
          </n-upload>
          <template v-if="uploading">
            <n-progress
              type="line"
              :percentage="uploadPercent < 100 ? uploadPercent : undefined"
              processing
            />
            <span class="hint">{{
              uploadPercent < 100 ? '正在上传安装包' : '正在读取包内版本并校验完整性'
            }}</span>
          </template>
          <n-button
            v-if="packageFiles[0]?.file"
            size="small"
            type="primary"
            :disabled="blocked || running"
            :loading="busy"
            @click="requestInstall(true)"
          >
            {{ info.install_label || '安装并重启' }}
          </n-button>
        </n-space>
        <span v-else>—</span>
      </n-form-item>
      <n-form-item v-if="!source && info?.platform === 'darwin'" :show-label="false">
        <span class="hint">若 macOS 拦截更新后启动，请在“隐私与安全性”中允许打开。</span>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-collapse>
          <n-collapse-item title="更新渠道与发布说明" name="channels">
            <p v-for="item in info?.channels || []" :key="item.value">
              <strong>{{ item.label }}</strong
              >：{{ item.description }}
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
                >查看发布记录</a
              >
            </p>
            <pre v-if="checked?.notes" class="notes">{{ checked.notes }}</pre>
          </n-collapse-item>
        </n-collapse>
      </n-form-item>
      <n-form-item v-if="showProgress || disconnected" :show-label="false">
        <div class="update-progress" aria-live="polite">
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
          <p v-if="showProgress">{{ job.message }}</p>
          <p v-if="showProgress && job.current">
            已下载 {{ (job.current / 1048576).toFixed(1) }} MiB<span v-if="job.total">
              / {{ (job.total / 1048576).toFixed(1) }} MiB</span
            >
          </p>
          <p v-if="disconnected">更新服务正在交接，稍后自动重试。</p>
        </div>
      </n-form-item>
      <n-form-item v-if="showProgress" :show-label="false">
        <n-space>
          <n-button
            size="small"
            tag="a"
            :href="progressUrl"
            target="_blank"
            rel="noopener noreferrer"
          >
            独立更新进度
          </n-button>
          <n-button
            v-if="job.status === 'running'"
            size="small"
            :disabled="!job.cancellable || cancelling"
            :loading="cancelling"
            @click="cancelUpdate"
            >取消更新</n-button
          >
        </n-space>
      </n-form-item>
      <n-form-item v-if="showProgress && (job.log || job.log_path)" :show-label="false">
        <n-collapse>
          <n-collapse-item title="安装日志" name="log">
            <p v-if="job.log_path" class="log-path">日志：{{ job.log_path }}</p>
            <pre v-if="job.log" class="notes">{{ job.log }}</pre>
          </n-collapse-item>
        </n-collapse>
      </n-form-item>
    </n-form>
  </n-card>
</template>

<style scoped>
.update-progress {
  width: 100%;
  min-width: 0;
  font-variant-numeric: tabular-nums;
}
.hint {
  margin-left: 8px;
  font-size: 12px;
  opacity: 0.6;
}
.restart-option,
.version-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}
.version-row {
  gap: 8px;
}
.version {
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.manual-upload {
  width: 100%;
  min-width: 0;
}
.notes {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 280px;
  overflow: auto;
  margin: 8px 0 0;
  font: inherit;
}
.log-path {
  overflow-wrap: anywhere;
}
p {
  margin: 8px 0 0;
  text-wrap: pretty;
}
</style>
