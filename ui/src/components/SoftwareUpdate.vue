<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { pendingSoftwarePackage } from '@/stores/updateUpload'
import { droppedUpdateFile } from '@/utils/manualUpdate'

const axios = inject('axios')
const messages = useMessage()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/software-update`
const headers = { 'X-Mower-Update': '1' }
const show = ref(false)
const activeTab = ref('online')
const info = ref(null)
const channel = ref('beta')
const background = ref(true)
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

function errorMessage(err) {
  return err.response?.data?.message || err.message || '操作失败，请重试'
}

function selectSoftwarePackage(file) {
  show.value = true
  activeTab.value = 'manual'
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
  info.value = data
  channel.value = data.settings.channel
  background.value = data.settings.background
}

async function poll() {
  try {
    const { data } = await axios.get(`${base}/status`, { timeout: 5000 })
    if (!data.ok) throw new Error(data.message)
    job.value = data
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
  if (disposed || !show.value) return
  // Keep retrying through backend shutdown, but do not spin forever after a crash.
  if (pendingSince && Date.now() - pendingSince > 45 * 60 * 1000) return
  timer = setTimeout(poll, 2000)
}

async function checkUpdate() {
  checking.value = true
  checked.value = null
  error.value = ''
  try {
    const { data } = await axios.post(`${base}/check`, { channel: channel.value }, { headers })
    if (!data.ok) throw new Error(data.message)
    checked.value = data
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    checking.value = false
  }
}

async function install(manual = false) {
  busy.value = true
  error.value = ''
  uploadPercent.value = 0
  try {
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
      response = await axios.post(
        `${base}/start`,
        {
          check_id: checked.value.check_id,
          background: background.value
        },
        { headers }
      )
    }
    if (!response.data.ok) throw new Error(response.data.message)
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

watch(channel, () => {
  checked.value = null
})
watch(show, async (value) => {
  clearTimeout(timer)
  if (!value) return
  pendingSince = 0
  error.value = ''
  try {
    await loadInfo()
  } catch (err) {
    error.value = errorMessage(err)
  }
  await poll()
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
  } catch {
    /* Opening the dialog exposes errors and retry. */
  }
})
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <n-card title="软件更新">
    <n-space vertical :size="12">
      <div class="summary">
        <span class="version">{{ info?.version || 'Mower' }}</span>
        <n-tag v-if="info" size="small" :bordered="false">{{
          source ? '源码部署' : 'Release 独立包'
        }}</n-tag>
      </div>
      <n-text depth="3">检查完整程序更新，更新后恢复本次运行的实例。</n-text>
      <n-button class="update-action" @click="show = true">打开软件更新</n-button>
      <n-upload
        v-if="info && !source"
        v-model:file-list="packageFiles"
        :default-upload="false"
        :max="1"
        accept=".zip,.gz,.dmg"
        :disabled="running"
        @change="({ file }) => file.file && selectSoftwarePackage(file.file)"
      >
        <n-upload-dragger @dragover.prevent @drop.capture.stop.prevent="dropSoftwarePackage">
          点击或拖入 Release 安装包
        </n-upload-dragger>
      </n-upload>
    </n-space>
  </n-card>
  <n-modal
    v-model:show="show"
    preset="card"
    title="软件更新"
    class="software-update-modal"
    :mask-closable="!busy"
  >
    <n-space vertical :size="18">
      <div v-if="info" class="summary">
        <span
          >当前版本 <strong class="version">{{ info.version }}</strong></span
        >
        <n-tag :bordered="false">{{ source ? '源码部署' : 'Release 独立包' }}</n-tag>
      </div>
      <n-alert v-if="error" type="error" title="操作未完成" role="alert">{{ error }}</n-alert>
      <n-alert v-if="info?.blockers.length" type="warning" title="当前安装需要先处理">
        <p v-for="message in info.blockers" :key="message">{{ message }}</p>
      </n-alert>
      <n-space vertical :size="8">
        <n-checkbox v-model:checked="background" :disabled="running || !info">
          更新后后台静默重启
        </n-checkbox>
        <n-text v-if="background" depth="3">
          不打开启动画面和网页窗口，保留托盘入口；macOS 后台进程不占用
          Dock。适用于在线更新和上传安装。
        </n-text>
        <n-text v-else depth="3">更新后正常打开窗口，恢复更新前的实例运行状态。</n-text>
      </n-space>
      <n-alert v-if="!source && info?.platform === 'darwin'" type="info" title="macOS 安装说明">
        当前发布包只有 ad-hoc 签名，尚未经 Apple
        公证。系统若拦截启动，需要在“隐私与安全性”中手动允许；后台静默重启也受此限制。
      </n-alert>
      <n-tabs v-model:value="activeTab" type="line" animated>
        <n-tab-pane name="online" tab="在线更新">
          <n-space vertical :size="16">
            <n-form-item label="更新渠道" :show-feedback="false">
              <n-select
                v-model:value="channel"
                :options="channelOptions"
                :disabled="running || checking"
              />
            </n-form-item>
            <n-text depth="3">{{ selectedChannel?.description }}</n-text>
            <n-collapse>
              <n-collapse-item title="正式版、公测版与开发版有什么区别？" name="channels">
                <p v-for="item in info?.channels || []" :key="item.value">
                  <strong>{{ item.label }}</strong
                  >：{{ item.description }}
                </p>
              </n-collapse-item>
            </n-collapse>
            <n-text depth="3">使用设置页中填写的网络与下载代理。</n-text>
            <n-text v-if="source" depth="3">代理同时用于 Git、Python 依赖和 npm 下载。</n-text>
            <n-button
              class="update-action"
              :loading="checking"
              :disabled="running || !info"
              @click="checkUpdate"
              >检查更新</n-button
            >
            <n-alert
              v-if="checked"
              :type="checked.available ? 'info' : 'success'"
              :title="checked.version"
            >
              {{ checked.message }}
              <p>
                <a :href="checked.url" target="_blank" rel="noopener noreferrer">查看发布记录</a>
              </p>
            </n-alert>
            <n-collapse v-if="checked?.notes">
              <n-collapse-item title="更新说明" name="notes">
                <pre class="notes">{{ checked.notes }}</pre>
              </n-collapse-item>
            </n-collapse>
            <n-popconfirm v-if="checked?.available" @positive-click="install(false)">
              <template #trigger>
                <n-button
                  type="primary"
                  class="update-action"
                  :disabled="blocked || running"
                  :loading="busy"
                >
                  更新并重启 {{ info?.instances.length || 0 }} 个实例
                </n-button>
              </template>
              将保存任务并关闭同一安装目录下的实例。更新成功后恢复运行状态，安装失败尝试恢复原版本。
            </n-popconfirm>
          </n-space>
        </n-tab-pane>
        <n-tab-pane name="manual" tab="上传 Release 安装包">
          <n-space vertical :size="16">
            <n-alert v-if="source" type="info" title="源码部署使用 Git 更新">
              Release 安装包适用于独立包部署。当前源码部署可在“在线更新”中选择正式版或公测版，按对应
              Release 标签更新；开发版跟随 alpha 分支。
            </n-alert>
            <template v-else>
              <n-text
                >选择对应系统和架构的官方安装包：Windows ZIP、Linux tar.gz、macOS
                DMG。保留原始文件名。</n-text
              >
              <n-upload
                v-model:file-list="packageFiles"
                :default-upload="false"
                :max="1"
                accept=".zip,.gz,.dmg"
                :disabled="running"
              >
                <n-upload-dragger
                  @dragover.prevent
                  @drop.capture.stop.prevent="dropSoftwarePackage"
                >
                  点击或拖入 Release 安装包
                </n-upload-dragger>
              </n-upload>
              <n-text depth="3">上传安装包即可离线安装，完成后按上方选择的方式重启。</n-text>
              <n-progress v-if="busy" type="line" :percentage="uploadPercent" />
              <n-popconfirm @positive-click="install(true)">
                <template #trigger>
                  <n-button
                    type="primary"
                    class="update-action"
                    :disabled="blocked || running || !packageFiles[0]?.file"
                    :loading="busy"
                    >安装并重启</n-button
                  >
                </template>
                将安装选中的 Release 包并重启当前实例。请从官方发布页下载安装包。
              </n-popconfirm>
            </template>
            <a
              :href="info?.releases_url || 'https://github.com/ArkMowers/arknights-mower/releases'"
              target="_blank"
              rel="noopener noreferrer"
              >打开 Mower 官方 Releases</a
            >
          </n-space>
        </n-tab-pane>
      </n-tabs>
      <n-alert
        v-if="job.status !== 'idle' || disconnected"
        :type="job.status === 'failed' ? 'error' : job.status === 'succeeded' ? 'success' : 'info'"
        title="更新状态"
        aria-live="polite"
      >
        {{
          disconnected
            ? '网页服务暂时断开，正在等待重启并重连。可以重新打开此窗口查看结果。'
            : job.message
        }}
        <p v-if="job.current" class="version">
          已下载 {{ (job.current / 1048576).toFixed(1) }} MiB<span v-if="job.total">
            / {{ (job.total / 1048576).toFixed(1) }} MiB</span
          >
        </p>
        <p v-if="job.log_path" class="log-path">日志：{{ job.log_path }}</p>
      </n-alert>
      <n-collapse v-if="job.log">
        <n-collapse-item title="安装日志" name="log">
          <pre class="notes">{{ job.log }}</pre>
        </n-collapse-item>
      </n-collapse>
    </n-space>
  </n-modal>
</template>

<style>
.software-update-modal {
  width: min(720px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
}
.software-update-modal > .n-card__content {
  overflow-y: auto;
  min-height: 0;
}
</style>
<style scoped>
.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.version {
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.update-action {
  min-height: 40px;
}
.notes {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 280px;
  overflow: auto;
  margin: 0;
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
