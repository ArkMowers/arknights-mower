<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'

const axios = inject('axios')
const base = `${import.meta.env.VITE_HTTP_URL || ''}/network`
const headers = { 'X-Mower-Settings': '1' }
const httpProxy = ref('')
const githubProxy = ref('')
const savedSettings = ref({ http_proxy: '', github_proxy: '' })
const loading = ref(true)
const ready = ref(false)
const saving = ref(false)
const testing = ref(false)
const error = ref('')
const saved = ref(false)
const results = ref([])
const dirty = computed(
  () =>
    httpProxy.value !== savedSettings.value.http_proxy ||
    githubProxy.value !== savedSettings.value.github_proxy
)
let timer
let saveRequest
let revision = 0

function errorMessage(err) {
  return err.response?.data?.message || err.message || '操作失败，请重试'
}

function values() {
  return { http_proxy: httpProxy.value, github_proxy: githubProxy.value }
}

function apply(data) {
  httpProxy.value = data.http_proxy
  githubProxy.value = data.github_proxy
  savedSettings.value = { http_proxy: data.http_proxy, github_proxy: data.github_proxy }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await axios.get(`${base}/settings`)
    if (!data.ok) throw new Error(data.message)
    apply(data)
    ready.value = true
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

function changed() {
  revision += 1
  clearTimeout(timer)
  error.value = ''
  results.value = []
  saved.value = false
  timer = setTimeout(save, 600)
}

async function save() {
  clearTimeout(timer)
  if (!ready.value) return false
  if (saveRequest) {
    await saveRequest
    return dirty.value ? save() : true
  }
  if (!dirty.value) return true
  const submittedRevision = revision
  const submitted = values()
  saving.value = true
  saveRequest = (async () => {
    try {
      const { data } = await axios.post(`${base}/settings`, submitted, { headers })
      if (!data.ok) throw new Error(data.message)
      savedSettings.value = { http_proxy: data.http_proxy, github_proxy: data.github_proxy }
      // A slower response must never overwrite text entered after it was sent.
      if (revision === submittedRevision) {
        apply(data)
        saved.value = true
        error.value = ''
      }
      return true
    } catch (err) {
      if (revision === submittedRevision) error.value = errorMessage(err)
      return false
    }
  })()
  const success = await saveRequest
  saveRequest = null
  saving.value = false
  if (revision !== submittedRevision && dirty.value) return save()
  return success
}

async function testConnection() {
  testing.value = true
  results.value = []
  let testedRevision = revision
  try {
    if (!(await save())) return
    testedRevision = revision
    const { data } = await axios.post(`${base}/test`, {}, { headers, timeout: 20000 })
    if (!data.ok) throw new Error(data.message)
    if (revision === testedRevision) {
      if (
        data.settings.http_proxy !== savedSettings.value.http_proxy ||
        data.settings.github_proxy !== savedSettings.value.github_proxy
      ) {
        throw new Error('代理设置已被其他实例修改，请重新加载后测试')
      }
      results.value = data.results
    }
  } catch (err) {
    if (revision === testedRevision) error.value = errorMessage(err)
  } finally {
    testing.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(timer)
  void save()
})
</script>

<template>
  <n-card title="网络与下载代理">
    <n-space vertical :size="16">
      <n-form-item label="全局网络代理" :show-feedback="false">
        <n-input
          v-model:value="httpProxy"
          :input-props="{ 'aria-label': '全局网络代理' }"
          placeholder="例如 http://127.0.0.1:7897；留空沿用启动环境"
          :disabled="loading || !ready"
          clearable
          @update:value="changed"
          @blur="save"
        />
      </n-form-item>
      <n-text depth="3">用于全局网络连接。</n-text>
      <n-form-item label="GitHub 下载代理站点" :show-feedback="false">
        <n-input
          v-model:value="githubProxy"
          :input-props="{ 'aria-label': 'GitHub 下载代理站点' }"
          placeholder="例如 https://ghfast.top/；留空直连 GitHub"
          :disabled="loading || !ready"
          clearable
          @update:value="changed"
          @blur="save"
        />
      </n-form-item>
      <n-text depth="3">
        用于 Mower 和 MAA 的 GitHub 安装包、资源包、热更包及原始文件。支持“站点地址/原始下载链接”
        格式；GitHub API 和 Git / Git LFS 使用上方网络代理。
      </n-text>
      <n-text depth="3">填写后自动保存，所有实例共享，后续连接使用新的设置。</n-text>
      <n-space align="center">
        <n-button
          :loading="testing"
          :disabled="loading || !ready || testing"
          @click="testConnection"
        >
          测试连接
        </n-button>
        <n-button v-if="!ready && !loading" @click="load">重新加载</n-button>
        <n-text v-if="saving" depth="3" aria-live="polite">正在应用…</n-text>
        <n-text v-else-if="saved && !dirty && !error" type="success" aria-live="polite">
          已应用到后续连接
        </n-text>
      </n-space>
      <n-text depth="3">测试 GitHub 下载接口是否可达。</n-text>
      <n-alert v-if="error" type="error" aria-live="polite">{{ error }}</n-alert>
      <n-alert
        v-for="result in results"
        :key="result.label"
        :type="result.ok ? 'success' : 'error'"
        :title="result.label"
        aria-live="polite"
      >
        {{ result.message }} · <span class="latency">{{ result.elapsed_ms }} ms</span>
      </n-alert>
    </n-space>
  </n-card>
</template>

<style scoped>
.latency {
  font-variant-numeric: tabular-nums;
}
</style>
