<script setup>
import { inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { pendingSoftwarePackage } from '@/stores/updateUpload'
const axios = inject('axios')
const base = `${import.meta.env.VITE_HTTP_URL || ''}/android/update`
const info = ref(null), channel = ref('beta'), repository = ref(''), busy = ref(false), message = ref(''), error = ref(''), selected = ref(null), result = ref(null), release = ref(null), progress = ref(0)
let timer, disposed = false
function fail(e) { error.value = e.response?.data?.message || e.message || '操作失败' }
async function refresh() {
  try {
    const { data } = await axios.get(`${base}/info`)
    if (disposed) return
    if (!info.value) { channel.value = data.settings.channel; repository.value = data.settings.repository || '' }
    info.value = data
    if (data.job.status === 'success') result.value = data.job.result
    if (data.job.status === 'error') error.value = data.job.message
  } catch (e) { if (!disposed) fail(e) }
}
async function run(fn) {
  busy.value = true; error.value = ''; message.value = ''
  try { await fn() } catch (e) { fail(e) } finally { busy.value = false }
}
async function check() {
  await run(async () => {
    await axios.post(`${base}/settings`, { channel: channel.value, ...(info.value.debug ? { repository: repository.value } : {}) })
    const { data } = await axios.post(`${base}/check`, {})
    release.value = data; message.value = data.message || `发行版 ${data.version}`
  })
}
async function upload() {
  if (!selected.value) return
  await run(async () => {
    const form = new FormData(); form.append('file', selected.value)
    const { data } = await axios.post(`${base}/upload`, form, { timeout: 300000, onUploadProgress: (event) => { if (event.total) progress.value = Math.round(event.loaded / event.total * 100) } })
    result.value = data; message.value = data.message || `APK ${data.version} 已通过包名、签名和版本检查`
    selected.value = null; await refresh()
  })
}
function drop(e) {
  if (e.dataTransfer.files.length !== 1) { error.value = '请一次导入一个更新包'; return }
  selected.value = e.dataTransfer.files[0]; result.value = null; progress.value = 0
}
async function download(asset) {
  await run(async () => { const { data } = await axios.post(`${base}/download`, { id: asset.id }); message.value = data.message; result.value = null; await refresh() })
}
async function install() {
  await run(async () => { const { data } = await axios.post(`${base}/install-apk`, { id: result.value.id }); message.value = data.message })
}
async function reset() {
  await run(async () => { const { data } = await axios.post(`${base}/reset-python`, {}); message.value = data.message; await refresh() })
}
watch(pendingSoftwarePackage, file => { if (file) { selected.value = file; result.value = null; pendingSoftwarePackage.value = null } }, { immediate: true })
onMounted(async () => { await refresh(); timer = setInterval(refresh, 3000) })
onUnmounted(() => { disposed = true; clearInterval(timer) })
</script>
<template>
  <n-card id="software-update" title="Mower Android 更新" class="android-update">
    <n-space vertical :size="16">
      <div>独立 APK 发行版 · 由 Mower Android 仓库构建</div>
      <n-descriptions v-if="info" :column="1" label-placement="left">
        <n-descriptions-item label="Android">{{ info.apk_version }}（{{ info.debug ? 'Debug' : '发行包' }}）</n-descriptions-item>
        <n-descriptions-item label="内置 Mower">{{ info.mower_version }}</n-descriptions-item>
        <n-descriptions-item label="MAA Python 接口">{{ info.python.version }} · {{ info.python.bundled ? 'APK 内置' : '独立导入' }}</n-descriptions-item>
      </n-descriptions>
      <n-flex align="center"><n-select v-model:value="channel" aria-label="Android 更新渠道" :options="[{label:'公测版',value:'beta'},{label:'正式版',value:'stable'}]" style="width: 160px" :disabled="busy" /><n-button :loading="busy" :disabled="!info" @click="check">检查 Android 更新</n-button></n-flex>
      <n-input v-if="info?.debug" v-model:value="repository" placeholder="Debug 发行仓库：owner/repo" :disabled="busy" />
      <n-alert v-if="error" type="error" title="操作未完成">{{ error }}</n-alert>
      <n-alert v-if="message" type="info">{{ message }}</n-alert>
      <n-flex v-if="release?.assets"><n-button v-for="asset in release.assets" :key="asset.id" :disabled="busy || info?.job.status === 'running'" @click="download(asset)">下载 {{ asset.name }}</n-button></n-flex>
      <n-progress v-if="info?.job.status === 'running'" type="line" :percentage="info.job.progress" processing />
      <div class="dropzone" data-update-dropzone @dragover.prevent @drop.stop.prevent="drop">
        <strong>导入 APK、MAA 核心或兼容 Python 包</strong>
        <p>拖入文件，或从手机选择。APK 经签名检查后交给系统安装。官方 Android MAA 核心包重启服务后生效；兼容 Python 接口从下一次创建 MAA 实例时生效。</p>
        <input type="file" accept=".apk,.zip,.tar.gz" aria-label="选择 Android 更新包" :disabled="busy" @change="selected = $event.target.files[0]; result = null; progress = 0" />
      </div>
      <div v-if="selected">{{ selected.name }} <n-button :loading="busy" @click="upload">确认上传并导入</n-button></div>
      <n-progress v-if="busy && progress > 0" type="line" :percentage="progress" />
      <n-button v-if="result?.kind === 'apk'" type="primary" :disabled="busy" @click="install">在手机上安装 {{ result.version }}</n-button>
      <n-button v-if="info && !info.python.bundled" :disabled="busy" @click="reset">恢复内置 MAA Python 接口</n-button>
      <p class="hint">Android 只接受正式版和公测版，不使用 Git 或桌面源码更新。MAA 核心与资源更新请前往 MAA 设置；Python 包必须适配 Android 桥接协议。</p>
    </n-space>
  </n-card>
</template>
<style scoped>
.android-update :deep(.n-button) { min-height: 40px; }
.dropzone { padding: 20px; border-radius: 12px; background: var(--mower-control-surface); }
.dropzone p, .hint { opacity: .7; line-height: 1.7; }
input { display: block; min-height: 40px; margin-top: 12px; max-width: 100%; }
</style>
