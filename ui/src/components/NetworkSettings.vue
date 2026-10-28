<script setup>
import { i18n } from '@/i18n'
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { copyMowerTestText } from '../utils/copyMowerTestText'

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
const copyStatus = ref('')
const dirty = computed(
  () =>
    httpProxy.value !== savedSettings.value.http_proxy ||
    githubProxy.value !== savedSettings.value.github_proxy
)
let timer
let saveRequest
let revision = 0

function errorMessage(err) {
  return (
    err.response?.data?.message ||
    err.message ||
    i18n.global.t('settings.network.operationFailedPleaseTryAgain')
  )
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
  copyStatus.value = ''
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
  copyStatus.value = ''
  let testedRevision = revision
  try {
    if (!(await save())) return
    testedRevision = revision
    // Direct GitHub and four stations each allow 10s to connect and 10s to read.
    const { data } = await axios.post(`${base}/test`, {}, { headers, timeout: 105000 })
    if (!data.ok) throw new Error(data.message)
    if (revision === testedRevision) {
      if (
        data.settings.http_proxy !== savedSettings.value.http_proxy ||
        data.settings.github_proxy !== savedSettings.value.github_proxy
      ) {
        throw new Error(
          i18n.global.t('settings.network.anotherInstanceChangedTheProxySettingsReload')
        )
      }
      results.value = data.results
    }
  } catch (err) {
    if (revision === testedRevision) error.value = errorMessage(err)
  } finally {
    testing.value = false
  }
}

async function copyResult() {
  const lines = [
    error.value,
    ...results.value.map((item) => `${item.label}：${item.message}（${item.elapsed_ms} ms）`)
  ].filter(Boolean)
  copyStatus.value = (await copyMowerTestText(lines.join('\n')))
    ? i18n.global.t('settings.network.copied')
    : i18n.global.t('settings.network.copyFailedSelectTheTextManually')
}

onMounted(load)
defineExpose({ save })
onBeforeUnmount(() => {
  clearTimeout(timer)
  void save()
})
</script>

<template>
  <n-card
    id="network-settings"
    :title="i18n.global.t('settings.network.networkDownloadProxies')"
    class="network-settings"
  >
    <div class="network-summary">
      <p>{{ i18n.global.t('settings.network.sharedByAllInstancesAppliesToSubsequent') }}</p>
      <span class="network-save-status" role="status">
        <template v-if="loading">{{ i18n.global.t('settings.network.loading') }}</template>
        <template v-else-if="saving">{{ i18n.global.t('settings.network.saving') }}</template>
        <template v-else-if="dirty && !error">{{
          i18n.global.t('settings.network.waitingToSave')
        }}</template>
        <span v-else-if="saved && !dirty && !error" class="network-saved">{{
          i18n.global.t('settings.network.appliedToSubsequentConnections')
        }}</span>
        <template v-else>{{ i18n.global.t('settings.network.changesSaveAutomatically') }}</template>
      </span>
    </div>
    <n-alert v-if="error" type="error" class="network-error" role="alert">{{ error }}</n-alert>
    <n-form class="network-form" label-placement="top" :show-feedback="false">
      <n-form-item :label="i18n.global.t('settings.network.globalNetworkProxy')">
        <n-input
          v-model:value="httpProxy"
          :input-props="{
            'aria-label': i18n.global.t('settings.network.globalNetworkProxy'),
            'aria-describedby': 'network-http-proxy-description',
            spellcheck: false
          }"
          :placeholder="i18n.global.t('settings.network.forExampleSocks5h127001')"
          :disabled="loading || !ready"
          clearable
          @update:value="changed"
          @blur="save"
        />
        <p id="network-http-proxy-description" class="network-description">
          {{ i18n.global.t('settings.network.usedForNetworkConnectionsSupportsHttpS') }}
        </p>
      </n-form-item>
      <n-form-item :label="i18n.global.t('settings.network.githubDownloadProxy')">
        <n-input
          v-model:value="githubProxy"
          :input-props="{
            'aria-label': i18n.global.t('settings.network.githubDownloadProxy'),
            'aria-describedby': 'network-github-proxy-description',
            spellcheck: false
          }"
          :placeholder="i18n.global.t('settings.network.leaveBlankToChooseADownloadMethod')"
          :disabled="loading || !ready"
          clearable
          @update:value="changed"
          @blur="save"
        />
        <p id="network-github-proxy-description" class="network-description">
          {{ i18n.global.t('settings.network.usedForMowerAndMaaDownloadsFrom') }}
        </p>
      </n-form-item>
    </n-form>
    <n-collapse class="network-help">
      <n-collapse-item
        :title="i18n.global.t('settings.network.proxyConfigurationHelp')"
        name="proxy-help"
        :data-settings-label="i18n.global.t('settings.network.proxyConfigurationHelp')"
      >
        <dl class="network-help-list">
          <div>
            <dt>{{ i18n.global.t('settings.network.globalNetworkProxy') }}</dt>
            <dd>
              {{ i18n.global.t('settings.network.supportsHttpHttpsSocks5AndSocks5hSocks') }}
            </dd>
          </div>
          <div>
            <dt>{{ i18n.global.t('settings.network.githubDownloadProxy') }}</dt>
            <dd>
              {{ i18n.global.t('settings.network.usedForInstallationPackagesResourcePackagesAnd') }}
            </dd>
          </div>
        </dl>
      </n-collapse-item>
    </n-collapse>
    <div
      class="network-test"
      :data-settings-label="i18n.global.t('settings.network.testConnection')"
    >
      <div class="network-test-heading">
        <span>{{ i18n.global.t('settings.network.connectionTest') }}</span>
        <p class="network-description">
          {{ i18n.global.t('settings.network.testTheGithubDownloadRoutesUsingThe') }}
        </p>
      </div>
      <div class="network-actions">
        <n-button
          type="primary"
          :loading="testing"
          :disabled="loading || !ready || testing"
          @click="testConnection"
          >{{ i18n.global.t('settings.network.testConnection') }}</n-button
        >
        <n-button v-if="!ready && !loading" @click="load">{{
          i18n.global.t('settings.network.reload')
        }}</n-button>
        <n-button v-if="error || results.length" :disabled="testing" @click="copyResult">{{
          i18n.global.t('settings.network.copyResults')
        }}</n-button>
        <span v-if="copyStatus" class="network-description" role="status">{{ copyStatus }}</span>
      </div>
    </div>
    <p v-if="testing" class="network-description network-testing" role="status">
      {{ i18n.global.t('settings.network.testingGithubDownloadRoutes') }}
    </p>
    <section
      v-if="results.length"
      class="network-results"
      :aria-label="i18n.global.t('settings.network.connectionTestResults')"
      aria-live="polite"
    >
      <div v-for="result in results" :key="result.label" class="network-result">
        <div class="network-result-heading">
          <strong>{{ result.label }}</strong>
          <n-tag size="small" :bordered="false" :type="result.ok ? 'success' : 'error'">{{
            result.ok
              ? i18n.global.t('settings.network.connected')
              : i18n.global.t('settings.network.connectionFailed')
          }}</n-tag>
          <span class="network-latency">{{ result.elapsed_ms }} ms</span>
        </div>
        <p>{{ result.message }}</p>
      </div>
    </section>
  </n-card>
</template>

<style>
.network-settings {
  container: network-settings / inline-size;
}

.network-summary,
.network-test,
.network-actions,
.network-result-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.network-summary {
  justify-content: space-between;
  margin-bottom: 20px;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.network-summary p,
.network-description,
.network-result p {
  margin: 0;
  overflow-wrap: anywhere;
  text-wrap: pretty;
}

.network-save-status {
  flex: none;
}

.network-saved {
  color: var(--mower-primary);
}

.network-error {
  margin-bottom: 18px;
}

.settings-page .network-settings .network-form > .n-form-item:has(> .n-form-item-label) {
  grid-template-columns: minmax(0, 1fr);
  grid-template-areas: 'label' 'blank' 'feedback';
  row-gap: 8px;
  padding: 0 0 20px;
  border-top: 0;
}

.settings-page .network-settings .network-form > .n-form-item > .n-form-item-label {
  min-height: 0;
  padding: 0;
  line-height: 1.5;
}

.settings-page .network-settings .network-form > .n-form-item > .n-form-item-blank {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  justify-self: stretch;
  width: 100%;
  max-width: none;
}

.settings-page .network-settings .network-form > .n-form-item > .n-form-item-blank > .n-input {
  width: 100%;
  max-width: none;
}

.network-description,
.network-result p,
.network-help-list dd {
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
}

.network-settings .network-help > .n-collapse-item {
  padding: 0;
  background: transparent;
}

.network-help-list {
  display: grid;
  gap: 12px;
  margin: 0 0 8px;
}

.network-help-list dt {
  margin-bottom: 4px;
  font-size: 13px;
}

.network-help-list dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.network-test {
  justify-content: space-between;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--settings-card-border);
}

.network-test-heading {
  flex: 1 1 240px;
  min-width: 0;
}

.network-test-heading > span {
  font-size: 14px;
}

.network-test-heading > p {
  margin-top: 4px;
}

.network-actions {
  gap: 8px;
}

.network-testing,
.network-results {
  margin-top: 16px;
}

.network-results {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 10px;
  background: var(--mower-control-surface);
}

.network-result-heading {
  gap: 6px 10px;
  margin-bottom: 6px;
  font-size: 13px;
}

.network-result-heading strong {
  font-weight: 500;
}

.network-latency {
  margin-left: auto;
  color: var(--mower-text-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

@container network-settings (max-width: 400px) {
  .network-test {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }

  .network-test-heading {
    flex-basis: auto;
  }
}
</style>
