<script setup>
import { inject, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { useResourceVersionStore } from '@/stores/resourceVersion'

const token = inject('token')
const manual_url = `${import.meta.env.VITE_HTTP_URL}/hot-update/manual`

const config_store = useConfigStore()
const { hot_update_enable } = storeToRefs(config_store)

const resource_store = useResourceVersionStore()
const { info, loading, installing, install_message } = storeToRefs(resource_store)
const { loadResourceVersion, installResource } = resource_store

const manual_result = ref('')

onMounted(() => {
  if (hot_update_enable.value) loadResourceVersion()
})

function on_manual_finish({ event }) {
  let text = '更新包应用失败'
  try {
    const data = JSON.parse(event.target.response)
    if (data && typeof data.message === 'string') {
      text = data.message
    }
  } catch (e) {
    // keep default failure text
  }
  manual_result.value = text
}
</script>

<template>
  <n-card title="资源更新">
    <n-form :show-feedback="false" label-placement="left" label-width="72">
      <n-form-item :show-label="false">
        <n-checkbox v-model:checked="hot_update_enable">启动时检查更新</n-checkbox>
        <span class="hint">打开 mower 时自动检查热更新和资源包</span>
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
            v-if="info.update_available === true"
            size="small"
            type="primary"
            :loading="installing"
            @click="installResource"
          >
            下载并安装
          </n-button>
        </n-space>
      </n-form-item>
      <n-form-item v-if="install_message" :show-label="false">
        <span>{{ install_message }}</span>
      </n-form-item>
      <n-form-item label="手动应用">
        <n-upload
          style="width: 100%"
          :action="manual_url"
          :headers="{ token: token }"
          name="update"
          :show-file-list="false"
          @finish="on_manual_finish"
        >
          <n-upload-dragger>
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
