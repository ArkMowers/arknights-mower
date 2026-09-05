<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { pendingSoftwarePackage } from '@/stores/updateUpload'
import { droppedUpdateFile } from '@/utils/manualUpdate'
import { confirmForceUpdate } from '@/utils/softwareUpdate'
import SourceVersionManager from './SourceVersionManager.vue'

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
const busy = ref(false)
const checking = ref(false)
const error = ref('')
const disconnected = ref(false)
const packageFiles = ref([])
const uploadPercent = ref(0)
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
let settingsRequest = Promise.resolve()

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
  if (checked.value || !result || result.channel !== channel.value) return
  if (result.ok) checked.value = result
  else if (result.message) error.value = result.message
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
    if (!data.ok) throw new Error(data.message)
    job.value = data
    showLastCheck(data.last_check)
    disconnected.value = false
    if (data.status === 'running' && !pendingSince) pendingSince = Date.now()
    const pending = sessionStorage.getItem(pendingKey)
    if (pending && pending === data.id && ['succeeded', 'failed'].includes(data.status)) {
      sessionStorage.removeItem(pendingKey)
      if (data.status === 'succeeded') {
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
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    checking.value = false
  }
}

async function install(manual = false, force = false, target = null) {
  if (running.value) return
  busy.value = true
  error.value = ''
  uploadPercent.value = 0
  try {
    await settingsRequest
    let response
    if (manual) {
      const form = new FormData()
      form.append('file', packageFiles.value[0].file)
      form.append('background', String(background.value))
      response = await axios.post(`${base}/manual`, form, {
        headers,
        onUploadProgress: (event) => {
          if (event.total) uploadPercent.value = Math.round((event.loaded / event.total) * 100)
        }
      })
    } else {
      if (!target && !checked.value?.check_id) {
        await checkUpdate()
        if ((!force && !checked.value?.available) || !checked.value?.check_id) return
      }
      response = await axios.post(
        `${base}/start`,
        {
          check_id: (target || checked.value).check_id,
          background: background.value,
          force
        },
        { headers }
      )
    }
    if (!response.data.ok) throw new Error(response.data.message)
    if (target) {
      autoUpdate.value = false
      channel.value = 'dev'
    }
    sessionStorage.setItem(pendingKey, response.data.id)
    pendingSince = Date.now()
    job.value = { ...response.data, status: 'running', phase: 'preparing' }
    clearTimeout(timer)
    await poll()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    busy.value = false
  }
}

function requestForceUpdate() {
  if (!info.value?.force_supported || running.value || checking.value || !checked.value?.check_id)
    return
  confirmForceUpdate(dialogs, checked.value.version, info.value.instances.length, () =>
    install(false, true)
  )
}

watch(channel, () => {
  checked.value = null
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
  } catch (err) {
    error.value = errorMessage(err)
  }
  await poll()
})
onUnmounted(() => {
  disposed = true
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
      <n-form-item :show-label="false">
        <n-checkbox
          :checked="autoUpdate"
          :disabled="!info || running"
          @update:checked="setAutoUpdate"
          >自动更新</n-checkbox
        >
        <span class="hint">发现更新后自动安装，重启同一安装目录下所有运行实例</span>
      </n-form-item>
      <n-form-item :show-label="false">
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
          <n-tag v-if="checked?.available === true" type="warning">可更新</n-tag>
          <n-tag v-else-if="checked?.available === false" type="success">已是最新</n-tag>
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
          <n-popconfirm
            style="max-width: min(360px, calc(100vw - 32px))"
            @positive-click="install(false)"
          >
            <template #trigger>
              <n-button
                size="small"
                type="primary"
                :disabled="blocked || running || checking || !checked?.available"
                :loading="busy"
              >
                下载并安装
              </n-button>
            </template>
            将保存任务并重启同一安装目录下的
            {{ info?.instances.length || 0 }} 个实例。安装失败时尝试恢复原版本。
          </n-popconfirm>
          <n-button
            v-if="source"
            size="small"
            type="warning"
            :disabled="!info?.force_supported || running || checking || !checked?.check_id"
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
      <n-form-item :show-label="false">
        <span class="hint"
          >更新后重启同一安装目录下所有运行实例；原本运行中的任务重置运行缓存后重新开始。在线更新与上传安装均使用上方的重启方式。</span
        >
      </n-form-item>
      <n-form-item v-if="source" :show-label="false">
        <SourceVersionManager
          :initial-branch="info.settings.source_branch"
          :running="running || checking"
          :blocked="blocked"
          :force-supported="info.force_supported"
          :instance-count="info.instances.length"
          @install="(target) => install(false, target.force, target)"
        />
      </n-form-item>
      <n-form-item label="手动应用">
        <span v-if="source" class="hint"
          >Release 安装包用于独立包部署，源码部署请使用上方在线更新。</span
        >
        <n-space v-else-if="info" vertical class="manual-upload" :size="8">
          <n-upload
            v-model:file-list="packageFiles"
            :default-upload="false"
            :max="1"
            accept=".zip,.gz,.dmg"
            :disabled="running"
          >
            <n-upload-dragger @dragover.prevent @drop.capture.stop.prevent="dropSoftwarePackage">
              <div>点击或拖入 Release 安装包</div>
              <div class="hint">Windows ZIP / Linux tar.gz / macOS DMG，保留原始文件名</div>
            </n-upload-dragger>
          </n-upload>
          <n-progress
            v-if="busy && packageFiles[0]?.file"
            type="line"
            :percentage="uploadPercent"
          />
          <n-popconfirm
            v-if="packageFiles[0]?.file"
            style="max-width: min(360px, calc(100vw - 32px))"
            @positive-click="install(true)"
          >
            <template #trigger>
              <n-button size="small" type="primary" :disabled="blocked || running" :loading="busy">
                安装并重启
              </n-button>
            </template>
            将安装选中的 Release 包并重启同一安装目录下所有运行实例。请从官方发布页下载安装包。
          </n-popconfirm>
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
      <n-form-item v-if="job.status !== 'idle' || disconnected" :show-label="false">
        <n-alert
          :type="
            job.status === 'failed' ? 'error' : job.status === 'succeeded' ? 'success' : 'info'
          "
          title="更新状态"
          aria-live="polite"
        >
          {{ disconnected ? '网页服务暂时断开，正在等待重启并重连。' : job.message }}
          <p v-if="job.current" class="version">
            已下载 {{ (job.current / 1048576).toFixed(1) }} MiB<span v-if="job.total">
              / {{ (job.total / 1048576).toFixed(1) }} MiB</span
            >
          </p>
          <p v-if="job.log_path" class="log-path">日志：{{ job.log_path }}</p>
        </n-alert>
      </n-form-item>
      <n-form-item v-if="job.log" :show-label="false">
        <n-collapse>
          <n-collapse-item title="安装日志" name="log">
            <pre class="notes">{{ job.log }}</pre>
          </n-collapse-item>
        </n-collapse>
      </n-form-item>
    </n-form>
  </n-card>
</template>

<style scoped>
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
