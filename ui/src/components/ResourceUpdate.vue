<script setup>
import axios from 'axios'
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import { useUpdateProgress } from '@/composables/useUpdateProgress'
import { getDroppedFile, postManualUpdate } from '@/utils/manualUpdate'
import '@/styles/updates.css'

const manual_url = `${import.meta.env.VITE_HTTP_URL}/resource-update/manual`

const config_store = useConfigStore()
const { resource_update_enable, resource_update_auto_update } = storeToRefs(config_store)
const { load_item, load_shop } = config_store

const plan_store = usePlanStore()
const { load_operators } = plan_store

const resource_store = useResourceVersionStore()
const { canInstall, info, loading, installing, install_message, job, progress_error } =
  storeToRefs(resource_store)
const { loadResourceVersion, loadResourceVersionLocal, installResource, loadResourceJob } =
  resource_store
const showProgress = useUpdateProgress(job)

const manual_result = ref('')
const manual_installing = ref(false)

async function refresh_resource_options() {
  try {
    await Promise.all([load_item(), load_shop(), load_operators()])
  } catch (error) {
    console.error('failed to refresh resource-backed options', error)
  }
}

onMounted(() => {
  loadResourceJob()
  // 当前版本常驻显示；开启「启动时检查更新」时才顺带拉远端最新版本。
  if (resource_update_enable.value) {
    loadResourceVersion()
  } else {
    loadResourceVersionLocal()
  }
})

async function show_manual_result(data) {
  manual_result.value = data && typeof data.message === 'string' ? data.message : '更新包应用失败'
  if (data?.ok && data.kind === 'resource') {
    await refresh_resource_options()
    if (resource_update_enable.value) {
      await loadResourceVersion(true)
    } else {
      await loadResourceVersionLocal()
    }
  }
}

async function install_resource() {
  if (await installResource()) {
    await refresh_resource_options()
  }
}

async function upload_manual_file(file, onProgress) {
  if (!file || manual_installing.value || installing.value) return false
  manual_installing.value = true
  manual_result.value = '正在应用更新包…'
  try {
    const data = await postManualUpdate(axios, manual_url, file, onProgress)
    await show_manual_result(data)
    return data?.ok === true
  } catch (error) {
    await show_manual_result(error.response?.data)
    return false
  } finally {
    manual_installing.value = false
  }
}

async function request_manual_update({ file, onProgress, onFinish, onError }) {
  const ok = await upload_manual_file(file.file, onProgress)
  if (ok) {
    onFinish()
  } else {
    onError()
  }
}

function drop_manual_update(event) {
  // 直接读取标准 FileList，兼容未实现 webkitGetAsEntry 的浏览器与桌面 WebView。
  const file = getDroppedFile(event)
  if (file) {
    void upload_manual_file(file)
  }
}

function set_auto_check(checked) {
  resource_update_enable.value = checked
  if (!checked) {
    resource_update_auto_update.value = false
  }
}

function set_auto_update(checked) {
  resource_update_auto_update.value = checked
  if (checked) {
    resource_update_enable.value = true
  }
}
</script>

<template>
  <n-card title="资源更新" class="update-card">
    <div class="update-overview">
      <div class="update-installed">
        <span class="update-caption" data-settings-label="当前版本">当前版本</span>
        <strong class="update-version">{{ info.current_display || '未安装' }}</strong>
        <span v-if="info.current_version" class="update-caption update-version-value">{{
          info.current_version
        }}</span>
      </div>
      <div class="update-actions">
        <n-button
          :loading="loading"
          :disabled="installing || manual_installing"
          @click="loadResourceVersion(true)"
          >检查更新</n-button
        >
        <n-button
          v-if="info.update_available === true"
          type="primary"
          :loading="installing"
          :disabled="!canInstall || manual_installing"
          @click="install_resource"
          >下载并安装</n-button
        >
      </div>
    </div>
    <div class="update-status" role="status" data-settings-label="最新版本">
      <template v-if="loading">正在检查最新资源版本…</template>
      <template v-else-if="info.update_available != null">
        <n-tag v-if="info.update_available" size="small" :bordered="false" type="warning"
          >可更新</n-tag
        >
        <n-tag v-else size="small" :bordered="false" type="success">已是最新</n-tag>
        <span v-if="info.remote_display">最新版本 {{ info.remote_display }}</span>
        <span v-if="info.remote_version" class="update-caption update-version-value">{{
          info.remote_version
        }}</span>
      </template>
      <span v-else class="update-caption">检查更新以获取最新资源包。</span>
    </div>
    <n-alert v-if="info.error" type="error" title="资源检查未完成" role="alert">{{
      info.error
    }}</n-alert>

    <div v-if="showProgress" class="update-progress" aria-live="polite">
      <n-progress
        type="line"
        :percentage="job.progress ?? 100"
        :show-indicator="job.progress != null"
        :processing="installing"
        :status="
          job.status === 'error' ? 'error' : job.status === 'success' ? 'success' : 'default'
        "
      />
      <p>{{ job.message || install_message }}</p>
      <p v-if="job.current" class="update-caption">
        已下载 {{ (job.current / 1048576).toFixed(1) }} MiB<span v-if="job.total">
          / {{ (job.total / 1048576).toFixed(1) }} MiB</span
        >
      </p>
      <p v-if="progress_error">{{ progress_error }}</p>
    </div>

    <n-form class="update-preferences" :show-feedback="false" label-placement="left">
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>自动检查更新</span>
            <span class="settings-row-description">打开 Mower 时自动检查资源包</span>
          </span>
        </template>
        <n-switch
          :value="resource_update_enable"
          aria-label="自动检查更新"
          @update:value="set_auto_check"
        />
      </n-form-item>
      <n-form-item>
        <template #label>
          <span class="settings-row-copy">
            <span>自动更新</span>
            <span class="settings-row-description">发现新资源包后自动安装</span>
          </span>
        </template>
        <n-switch
          :value="resource_update_auto_update"
          aria-label="自动更新"
          @update:value="set_auto_update"
        />
      </n-form-item>
    </n-form>
    <p class="update-footnote">
      优先下载 OTA 增量包，不可用时自动下载整包。同一套 Mower
      的全部实例共用资源包，空闲时自动加载，无需重启 Mower。
    </p>
    <n-collapse class="update-details">
      <n-collapse-item
        title="从本地资源包更新"
        name="manual"
        data-settings-label="从本地资源包更新"
      >
        <div class="update-manual">
          <n-upload
            accept=".zip"
            :custom-request="request_manual_update"
            :disabled="manual_installing || installing"
            :show-file-list="false"
          >
            <n-upload-dragger @dragover.prevent @drop.capture.stop.prevent="drop_manual_update">
              <div>点击或拖入资源更新包</div>
              <p class="update-caption">
                支持资源整包和对应当前版本的 OTA 包，用于网络不稳时手动更新
              </p>
            </n-upload-dragger>
          </n-upload>
        </div>
      </n-collapse-item>
    </n-collapse>
    <p v-if="manual_result" class="update-result" role="status">{{ manual_result }}</p>
  </n-card>
</template>
