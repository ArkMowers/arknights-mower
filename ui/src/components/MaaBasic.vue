<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
const axios = inject('axios')

defineProps({
  showTitle: { type: Boolean, default: true }
})

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const managerOwned = computed(() => manager_owned_device.value === true)
const {
  manager_owned_device,
  runtime_platform,
  maa_path,
  maa_restore_theme_enable,
  maa_restore_theme,
  maa_conn_preset,
  maa_touch_option
} = storeToRefs(store)

import { folder_dialog } from '@/utils/dialog'
import { getMaaThemeOptions } from '@/utils/maa_theme_options'

const maa_theme_options = computed(() => getMaaThemeOptions(maa_restore_theme.value))

async function select_maa_dir() {
  if (managerOwned.value) return
  const folder_path = await folder_dialog()
  if (folder_path && !managerOwned.value) {
    maa_path.value = folder_path
  }
}

const maa_msg = ref('')
const maa_testing = ref(false)

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function test_maa() {
  if (managerOwned.value || maa_testing.value) return
  maa_testing.value = true
  maa_msg.value = '正在测试……'
  try {
    let response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa`)
    let data = response.data
    if (typeof data === 'string') {
      maa_msg.value = data
      return
    }
    while (!managerOwned.value && data.status === 'running') {
      maa_msg.value = data.message || '正在测试……'
      await sleep(1000)
      if (managerOwned.value) return
      response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa/status`)
      data = response.data
      if (typeof data === 'string') {
        maa_msg.value = data
        return
      }
    }
    maa_msg.value = data.message || '测试失败，请检查MAA日志！'
  } catch (error) {
    maa_msg.value = `测试失败：${error.message}`
  } finally {
    maa_testing.value = false
  }
}

const maa_conn_presets = ref([])

async function get_maa_conn_presets() {
  if (managerOwned.value || disposed) return
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-conn-preset`)
    if (managerOwned.value || disposed) return
    if (Array.isArray(response.data)) {
      maa_conn_presets.value = response.data.map((x) => ({ label: x, value: x }))
    } else {
      maa_conn_presets.value = []
      maa_msg.value = response.data.message || '读取 MAA 连接配置失败'
    }
  } catch (error) {
    maa_msg.value = `读取连接配置失败：${error.message}`
  }
}

const maa_touch_options = ['maatouch', 'minitouch', 'adb'].map((x) => {
  return { label: x, value: x }
})

let disposed = false
let maa_path_refresh_timer = null

watch(maa_path, (value, previous_value) => {
  if (managerOwned.value || value === previous_value) return
  if (maa_path_refresh_timer) window.clearTimeout(maa_path_refresh_timer)
  maa_path_refresh_timer = window.setTimeout(get_maa_conn_presets, 400)
})

onMounted(get_maa_conn_presets)

onUnmounted(() => {
  disposed = true
  if (maa_path_refresh_timer) window.clearTimeout(maa_path_refresh_timer)
})
</script>

<template>
  <n-card class="maa-basic" content-class="maa-basic-content">
    <template v-if="showTitle" #header
      >MAA 核心<help-text>{{
        managerOwned ? '游戏主题恢复' : '连接、触控和游戏主题恢复'
      }}</help-text></template
    >
    <n-form
      class="maa-basic-form"
      label-placement="left"
      :show-feedback="false"
      label-width="128"
      label-align="left"
    >
      <n-alert v-if="!managerOwned && runtime_platform === 'android'" :show-icon="false"
        >设备连接与 MAA 路径由 Android 应用管理。</n-alert
      >
      <div v-if="!managerOwned && runtime_platform === 'android'" style="margin-bottom: 16px">
        <SessionLink to="/mowersettings#software-update"
          >导入官方 Android MAA 核心 / 兼容 Python 接口包</SessionLink
        >
      </div>
      <template v-else-if="!managerOwned">
        <n-form-item label="MAA目录">
          <template #label>
            MAA目录
            <help-text
              >@app/MAA 表示全局 Mower 数据目录下的 MAA，所有实例共用，更新 Mower
              时保留。也可以选择自定义目录。</help-text
            >
          </template>
          <div class="maa-field-with-action">
            <n-input v-model:value="maa_path" :input-props="{ 'aria-label': 'MAA目录' }" />
            <n-button @click="select_maa_dir">浏览</n-button>
          </div>
        </n-form-item>
        <n-form-item label="连接配置">
          <div class="maa-field-with-action">
            <n-select :options="maa_conn_presets" v-model:value="maa_conn_preset" />
            <n-button @click="get_maa_conn_presets">刷新</n-button>
          </div>
        </n-form-item>
        <n-form-item label="触控模式">
          <n-select v-model:value="maa_touch_option" :options="maa_touch_options" />
        </n-form-item>
      </template>
      <n-form-item label="恢复主题">
        <template #label>
          恢复主题
          <help-text label="恢复主题说明" :max-width="480">
            恢复主题需要 MAA v6.17.3 或更高版本。在本轮 MAA
            日常及大型任务结束后、休息前，恢复到指定主题。
            下拉列表包含国服游戏主题，请选择账号已解锁的主题；清空选择后不恢复。
            手动停止、异常退出或调度时间不足时跳过。
          </help-text>
        </template>
        <n-checkbox v-model:checked="maa_restore_theme_enable">任务结束后恢复主题</n-checkbox>
      </n-form-item>
      <n-form-item v-if="maa_restore_theme_enable" label="目标主题">
        <n-select
          :value="maa_restore_theme || null"
          :options="maa_theme_options"
          filterable
          clearable
          placeholder="请选择要恢复的主题"
          @update:value="maa_restore_theme = $event ?? ''"
        />
      </n-form-item>
    </n-form>
    <n-divider v-if="!managerOwned" />
    <div v-if="!managerOwned" class="maa-connection-test">
      <n-button :loading="maa_testing" :disabled="maa_testing" @click="test_maa">
        测试连接
      </n-button>
      <p v-if="maa_msg" class="maa-connection-result" role="status">{{ maa_msg }}</p>
    </div>
  </n-card>
</template>

<style scoped>
.maa-basic {
  min-width: 0;
  container: maa-basic / inline-size;
}

.maa-basic :deep(> .maa-basic-content) {
  min-width: 0;
  max-width: 760px;
}

.maa-basic .maa-basic-form :deep(> .n-form-item) {
  margin: 0;
  padding: 12px 0;
  grid-template-columns: 128px minmax(0, 480px);
  grid-template-areas: 'label blank' 'label feedback';
  grid-template-rows: auto auto;
  gap: 0 16px;
  align-items: center;
}

.maa-basic .maa-basic-form :deep(> .n-form-item:first-child) {
  padding-top: 0;
}

.maa-basic .maa-basic-form :deep(> .n-form-item:last-child) {
  padding-bottom: 0;
}

.maa-basic .maa-basic-form :deep(> .n-form-item > .n-form-item-label) {
  min-width: 0;
  min-height: 0;
  width: auto;
  padding: 0;
  justify-content: flex-start;
}

.maa-basic .maa-basic-form :deep(> .n-form-item > .n-form-item-blank) {
  width: 100%;
  max-width: none;
  min-width: 0;
  justify-content: flex-start;
}

.maa-basic .maa-basic-form :deep(.n-form-item-blank > .n-select) {
  max-width: none;
}

.maa-field-with-action {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.maa-field-with-action :deep(> .n-input),
.maa-field-with-action :deep(> .n-select) {
  flex: 1;
  min-width: 0;
}

.maa-field-with-action :deep(> .n-button) {
  flex: none;
}

.maa-connection-test {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.maa-connection-result {
  flex-basis: 100%;
  margin: 0;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@container maa-basic (max-width: 480px) {
  .maa-basic .maa-basic-form :deep(> .n-form-item) {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'label' 'blank' 'feedback';
    gap: 8px 0;
  }
}
</style>
