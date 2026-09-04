<script setup>
import axios from 'axios'
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import { getDroppedFile, postManualUpdate } from '@/utils/manualUpdate'

const manual_url = `${import.meta.env.VITE_HTTP_URL}/hot-update/manual`

const config_store = useConfigStore()
const { hot_update_enable, hot_update_auto_update } = storeToRefs(config_store)
const { load_item, load_shop } = config_store

const plan_store = usePlanStore()
const { load_operators } = plan_store

const resource_store = useResourceVersionStore()
const { canInstall, info, loading, installing, install_message } = storeToRefs(resource_store)
const { loadResourceVersion, loadResourceVersionLocal, installResource } = resource_store

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
  // 当前版本常驻显示；开启「启动时检查更新」时才顺带拉远端最新版本。
  if (hot_update_enable.value) {
    loadResourceVersion()
  } else {
    loadResourceVersionLocal()
  }
})

async function show_manual_result(data) {
  manual_result.value = data && typeof data.message === 'string' ? data.message : '更新包应用失败'
  if (data?.ok && data.kind === 'resource') {
    await refresh_resource_options()
    if (hot_update_enable.value) {
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
  if (!file || manual_installing.value) return false
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
  hot_update_enable.value = checked
  if (!checked) {
    hot_update_auto_update.value = false
  }
}

function set_auto_update(checked) {
  hot_update_auto_update.value = checked
  if (checked) {
    hot_update_enable.value = true
  }
}
</script>

<template>
  <n-card title="资源更新">
    <n-form :show-feedback="false" label-placement="left" label-width="72">
      <n-form-item :show-label="false">
        <n-checkbox :checked="hot_update_enable" @update:checked="set_auto_check">
          自动检查更新
        </n-checkbox>
        <span class="hint">打开 mower 时自动检查热更新和资源包</span>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-checkbox :checked="hot_update_auto_update" @update:checked="set_auto_update">
          自动更新
        </n-checkbox>
        <span class="hint">发现更新后自动应用热更新和资源包</span>
      </n-form-item>
      <n-form-item label="当前版本">
        <span>{{ info.current_display || '未安装' }}</span>
        <span v-if="info.current_version" class="hint">（{{ info.current_version }}）</span>
      </n-form-item>
      <n-form-item label="最新版本">
        <span>{{ info.remote_display || '—' }}</span>
        <span v-if="info.remote_version" class="hint">（{{ info.remote_version }}）</span>
        <n-tag v-if="info.update_available === true" type="warning">可更新</n-tag>
        <n-tag v-else-if="info.update_available === false" type="success">已是最新</n-tag>
        <n-tag v-else-if="info.error" type="error">{{ info.error }}</n-tag>
      </n-form-item>
      <n-form-item :show-label="false">
        <n-space>
          <n-button size="small" :loading="loading" @click="loadResourceVersion(true)">
            检查更新
          </n-button>
          <n-button
            size="small"
            type="primary"
            :loading="installing"
            :disabled="!canInstall"
            @click="install_resource"
          >
            下载并安装
          </n-button>
        </n-space>
      </n-form-item>
      <n-form-item v-if="install_message" :show-label="false">
        <span>{{ install_message }}</span>
      </n-form-item>
      <n-form-item :show-label="false">
        <span class="hint">
          同一套 mower 的所有实例共用资源包，空闲实例会自动加载新资源；仅软件版本更新需要重启 Mower
        </span>
      </n-form-item>
      <n-form-item label="手动应用">
        <n-upload
          style="width: 100%"
          accept=".zip"
          :custom-request="request_manual_update"
          :disabled="manual_installing"
          :show-file-list="false"
        >
          <n-upload-dragger @dragover.prevent @drop.capture.stop.prevent="drop_manual_update">
            <div>点击或拖入更新包</div>
            <div class="hint">自动识别热更包 / 资源包，用于直连 GitHub 不稳时的兜底</div>
          </n-upload-dragger>
        </n-upload>
      </n-form-item>
      <n-form-item v-if="manual_result" :show-label="false">
        <span>{{ manual_result }}</span>
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
</style>
